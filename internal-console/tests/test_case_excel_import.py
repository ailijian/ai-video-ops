"""Exact private-candidate contract: isolated persistence, no Case or Task."""
import base64
import copy
import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import case_excel_import as imports
from app.auth_service import provision_user, resolve_session
from app.database import connect
from app.main import build_app
from conftest import login_and_change_password
from test_case_excel_preview_v03 import VECTORS, workbook


def payload(rows=2, op='op_save_1'):
    cases = []
    for n in range(rows):
        row = copy.deepcopy(VECTORS[0]['case_row'])
        row.update(external_case_key=f'FICTIONAL-{n}', source_url=f'https://www.douyin.com/video/{7999999999999999700+n}')
        cases.append(row)
    return {'file_base64': base64.b64encode(workbook(cases)).decode(), 'operation_id': op,
            'selected_rows': list(range(5, 5 + rows)), 'source_uploads': []}


def post(client, path, data, csrf):
    return client.post('/api/case-excel/imports/' + path, json=data, headers={'X-CSRF-Token': csrf})


def prepared(client, data, csrf):
    response = post(client, 'prepare', data, csrf)
    assert response.status_code == 200, response.text
    context = response.json()
    return {**data, 'batch_sha256': context['batch_sha256'], 'intent_sha256': context['intent_sha256'],
            'expected_head_sha256': context['intent']['expected_head_sha256']}, context


def protected(settings):
    files = {str(p.relative_to(settings.pipeline_root)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in settings.pipeline_root.rglob('*') if p.is_file()
             and 'case_intake_imports' not in p.parts and '.locks' not in p.parts and '__pycache__' not in p.parts}
    with connect(settings.database_path) as db:
        tasks = [tuple(row) for row in db.execute('SELECT * FROM tasks')]
        groups = [tuple(row) for row in db.execute('SELECT * FROM case_intake_groups')]
    return files, tasks, groups


def test_prepare_has_no_writes_then_exact_replay_and_owner_projection(client, settings):
    csrf = login_and_change_password(client)
    before = protected(settings)
    data = payload()
    request, context = prepared(client, data, csrf)
    store = settings.pipeline_root / 'data/case_intake_imports'
    assert not store.exists()
    assert context['intent']['dispatch_model'] is False
    response = post(client, 'save', request, csrf)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['result']['state'] == 'saved'
    assert [r['state'] for r in result['result']['row_results']] == ['pending_source', 'pending_source']
    assert result == post(client, 'save', request, csrf).json()
    assert 'private, no-store' in response.headers['cache-control']
    detail = client.get('/api/case-excel/imports/' + result['batch_id'])
    assert detail.status_code == 200, detail.text
    assert len(detail.json()['rows']) == 2
    assert all(r['formal_video_type'] is None and not r['approval_granted'] for r in detail.json()['rows'])
    assert protected(settings) == before
    assert len(list(store.glob('*/import_*/rows/*.json'))) == 2
    from app.canonical_gateway import list_cases
    assert not {'7999999999999999700', '7999999999999999701'} & {r['case_id'] for r in list_cases(settings)}


def test_concurrent_double_submit_and_all_sixteen_vectors(client, settings):
    csrf = login_and_change_password(client)
    data = payload(1)
    data['file_base64'] = base64.b64encode(workbook([copy.deepcopy(v['case_row']) for v in VECTORS])).decode()
    data['selected_rows'] = list(range(5, 21))
    request, context = prepared(client, data, csrf)
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: post(client, 'save', request, csrf), range(2)))
    assert all(r.status_code in {200,409} for r in responses)
    final = post(client, 'save', request, csrf)
    assert final.status_code == 200, final.text
    result = final.json()['result']
    assert len(result['row_results']) == 16
    for preview, row in zip(context['preview']['rows'], result['row_results']):
        assert (row['state'] == 'invalid') == (preview['status'] == 'invalid')
    detail = client.get('/api/case-excel/imports/' + final.json()['batch_id']).json()
    assert all(r['approval_granted'] is False and r['evidence_promoted'] is False and r['formal_video_type'] is None for r in detail['rows'])
    with connect(settings.database_path) as db:
        assert db.execute('SELECT count(*) FROM tasks').fetchone()[0] == 0


@pytest.mark.parametrize('point', ['operation_ref', 'workbook', 'batch', 'intent', 'row', 'source_index', 'row_result', 'row_committed', 'result'])
def test_each_atomic_boundary_recovers_same_intent_without_duplicate(client, settings, monkeypatch, point):
    csrf = login_and_change_password(client)
    request, _ = prepared(client, payload(), csrf)
    fired = False
    def interrupt(here):
        nonlocal fired
        if here == point and not fired:
            fired = True
            raise OSError('simulated interrupted publication')
    monkeypatch.setattr(imports, '_checkpoint', interrupt)
    first = post(client, 'save', request, csrf)
    assert fired
    assert first.status_code == 503 or first.json().get('result', {}).get('state') == 'recovery_required'
    second = post(client, 'save', request, csrf)
    assert second.status_code == 200, second.text
    assert second.json()['result']['state'] == 'saved'
    assert second.json() == post(client, 'save', request, csrf).json()
    assert len(list((settings.pipeline_root / 'data/case_intake_imports').glob('*/import_*/rows/*.json'))) == 2
    with connect(settings.database_path) as db:
        assert db.execute('SELECT count(*) FROM tasks').fetchone()[0] == 0


def test_changed_operation_or_stale_head_is_rejected(client):
    csrf = login_and_change_password(client)
    request, _ = prepared(client, payload(), csrf)
    stale, _ = prepared(client, payload(op='op_other'), csrf)
    assert post(client, 'save', request, csrf).status_code == 200
    assert post(client, 'save', {**request, 'selected_rows': [5]}, csrf).status_code == 409
    assert post(client, 'save', stale, csrf).json()['detail']['code'] == 'IMPORT_HEAD_CHANGED'
    changed, _ = prepared(client, payload(1, op='op_save_1'), csrf)
    assert post(client, 'save', changed, csrf).json()['detail']['code'] == 'IMPORT_INTENT_CONFLICT'


def test_same_source_new_excel_key_retains_notes_links_private_candidate(client, settings):
    csrf = login_and_change_password(client)
    first, _ = prepared(client, payload(1), csrf)
    assert post(client, 'save', first, csrf).status_code == 200
    second = payload(1, op='op_second_file')
    row = copy.deepcopy(VECTORS[0]['case_row'])
    row.update(external_case_key='DIFFERENT-KEY', source_url='https://www.douyin.com/video/7999999999999999700', structure_summary='新的未核笔记')
    second['file_base64'] = base64.b64encode(workbook([row])).decode()
    request, _ = prepared(client, second, csrf)
    result = post(client, 'save', request, csrf)
    assert result.status_code == 200, result.text
    assert result.json()['result']['row_results'][0]['state'] == 'already_recorded_private'
    assert len(list((settings.pipeline_root / 'data/case_intake_imports').glob('*/sources/*.json'))) == 1
    assert len(list((settings.pipeline_root / 'data/case_intake_imports').glob('*/import_*/rows/*.json'))) == 2


def test_cancel_remaining_after_partial_publication_preserves_saved_row(client, settings, monkeypatch):
    csrf = login_and_change_password(client)
    request, context = prepared(client, payload(), csrf)
    def interrupt(here):
        if here == 'source_index':
            raise OSError('interrupt after first saved row before its result')
    monkeypatch.setattr(imports, '_checkpoint', interrupt)
    assert post(client, 'save', request, csrf).json()['result']['state'] == 'recovery_required'
    monkeypatch.setattr(imports, '_checkpoint', lambda _: None)
    cancel = {**payload(op='op_cancel_1'), 'action': 'cancel_uncommitted_rows'}
    cancelled, _ = prepared(client, cancel, csrf)
    result = post(client, 'save', cancelled, csrf)
    assert result.status_code == 200, result.text
    assert [r['state'] for r in result.json()['result']['row_results']] == ['already_recorded_private', 'cancelled']
    resumed = post(client, 'save', request, csrf)
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()['result']['state'] == 'cancelled_remaining'
    assert [r['state'] for r in resumed.json()['result']['row_results']] == ['pending_source', 'cancelled']
    assert len(list((settings.pipeline_root / 'data/case_intake_imports').glob('*/import_*/rows/*.json'))) == 1
    new_request, _ = prepared(client, payload(op='op_new_after_cancel'), csrf)
    new_result = post(client, 'save', new_request, csrf)
    assert new_result.status_code == 200, new_result.text
    assert new_result.json()['result']['row_results'][1]['state'] == 'pending_source'
    assert post(client, 'save', request, csrf).json()['result']['state'] == 'cancelled_remaining'


@pytest.mark.parametrize('point', ['operation_ref', 'workbook', 'batch', 'intent', 'row', 'source_index', 'row_result', 'row_committed', 'result'])
def test_actual_process_exit_releases_locks_and_recovers(client, settings, tmp_path, point):
    csrf = login_and_change_password(client)
    request, _ = prepared(client, payload(), csrf)
    session = resolve_session(settings.database_path, client.cookies.get(settings.session_cookie_name))
    data = {'settings': {k: str(getattr(settings, k)) for k in ['repo_root', 'console_root', 'pipeline_root', 'database_path']},
            'session': {'token_hash': session.token_hash, 'csrf_token': session.csrf_token, 'user': session.user},
            'request': request, 'point': point}
    context = tmp_path / 'child-context.json'
    context.write_text(json.dumps(data), encoding='utf8')
    source = """
import json,sys,os
from pathlib import Path
data=json.loads(Path(sys.argv[1]).read_text('utf8'))
sys.path[:0]=[data['settings']['console_root'],str(Path(data['settings']['repo_root'])/'ops-pipeline/scripts')]
from app.config import Settings
from app.auth_service import SessionContext
from app import case_intake_service
from app import case_excel_import as imp
settings=Settings(**{k:Path(v) for k,v in data['settings'].items()},python_executable=sys.executable)
def crash(here):
 if here==data['point']:os._exit(73)
imp._checkpoint=crash
case_intake_service.save_excel_import(settings,SessionContext(**data['session']),imp.SaveInput.model_validate(data['request']))
"""
    completed = subprocess.run([sys.executable, '-c', source, str(context)], cwd=settings.console_root,
                               capture_output=True, text=True, timeout=30)
    assert completed.returncode == 73, completed.stderr
    response = post(client, 'save', request, csrf)
    assert response.status_code == 200, response.text
    assert response.json()['result']['state'] == 'saved'
    assert len(list((settings.pipeline_root / 'data/case_intake_imports').glob('*/import_*/rows/*.json'))) == 2


def test_recover_from_persisted_record_after_refresh(client, settings, monkeypatch):
    csrf = login_and_change_password(client)
    request, context = prepared(client, payload(), csrf)
    def interrupt(here):
        if here == 'row_result': raise OSError('lost connection')
    monkeypatch.setattr(imports, '_checkpoint', interrupt)
    response = post(client, 'save', request, csrf)
    assert response.json()['result']['state'] == 'recovery_required'
    batch_id = response.json()['batch_id']
    monkeypatch.setattr(imports, '_checkpoint', lambda _: None)
    record = client.get('/api/case-excel/imports/' + batch_id).json()
    assert record['operations'][0]['result'] is None
    recovered = post(client, batch_id + '/recover', {'operation_id': request['operation_id'], 'intent_sha256': request['intent_sha256']}, csrf)
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()['result']['state'] == 'saved'


def test_real_upload_binding_expiry_projection_and_completed_replay(client, settings, monkeypatch):
    from app import case_uploads
    csrf = login_and_change_password(client)
    monkeypatch.setattr(case_uploads, 'probe_upload', lambda *a: {'duration_seconds': 2, 'width': 64, 'height': 64, 'audio_present': True})
    url = 'https://www.douyin.com/video/7999999999999999700'
    uploaded = client.post('/api/cases/source-files', params={'url': url, 'suffix': '.mp4', 'rights_confirmed': True, 'source_match_confirmed': True},
        content=b'fictional-media-provider-boundary', headers={'X-CSRF-Token': csrf})
    assert uploaded.status_code == 200, uploaded.text
    upload_id = uploaded.json()['upload_id']
    data = payload(1)
    data['source_uploads'] = [{'source_row': 5, 'upload_id': upload_id}]
    request, context = prepared(client, data, csrf)
    binding = context['intent']['row_source_bindings'][0]
    assert binding['native_upload_ref']['upload_id'] == upload_id
    assert binding['media_sha256'] == hashlib.sha256(b'fictional-media-provider-boundary').hexdigest()
    response = post(client, 'save', request, csrf)
    assert response.status_code == 200, response.text
    assert response.json()['result']['row_results'][0]['state'] == 'saved_unverified'
    batch_id = response.json()['batch_id']
    before = protected(settings)
    class Future(datetime):
        @classmethod
        def now(cls, tz=None): return datetime.now(tz) + timedelta(days=2)
    monkeypatch.setattr(case_uploads, 'datetime', Future)
    record = client.get('/api/case-excel/imports/' + batch_id)
    assert record.status_code == 200, record.text
    assert record.json()['operations'][0]['current_bindings'][0]['current_media_state'] == 'pending_source'
    assert post(client, 'save', request, csrf).json() == response.json()
    assert post(client, 'prepare', {**data, 'operation_id': 'op_expired_new'}, csrf).status_code == 422
    assert protected(settings) == before


def test_unbound_filename_and_foreign_or_wrong_source_upload_fail_closed(client, settings, monkeypatch):
    from app import case_uploads
    csrf = login_and_change_password(client)
    monkeypatch.setattr(case_uploads, 'probe_upload', lambda *a: {'duration_seconds': 2, 'width': 64, 'height': 64, 'audio_present': True})
    uploaded = client.post('/api/cases/source-files', params={'url': 'https://www.douyin.com/video/7999999999999999800', 'suffix': '.mp4', 'rights_confirmed': True, 'source_match_confirmed': True},
        content=b'fictional-upload', headers={'X-CSRF-Token': csrf}).json()
    data = payload(1)
    data['source_uploads'] = [{'source_row': 5, 'upload_id': uploaded['upload_id']}]
    assert post(client, 'prepare', data, csrf).json()['detail']['code'] == 'IMPORT_UPLOAD_REBIND_REQUIRED'
    row = copy.deepcopy(VECTORS[0]['case_row']); row.update(source_url='', media_filename='fictional-video.mp4')
    data['file_base64'] = base64.b64encode(workbook([row])).decode()
    assert post(client, 'prepare', data, csrf).json()['detail']['code'] == 'IMPORT_UPLOAD_SOURCE_REQUIRED'
    data['source_uploads'] = []
    request, context = prepared(client, data, csrf)
    assert context['intent']['row_source_bindings'][0]['native_upload_ref'] is None
    assert post(client, 'save', request, csrf).json()['result']['row_results'][0]['state'] == 'pending_source'


def test_unknown_history_schema_and_corrupt_workbook_are_rejected(client, settings):
    csrf = login_and_change_password(client)
    request, _ = prepared(client, payload(1), csrf)
    response = post(client, 'save', request, csrf).json()
    store = settings.pipeline_root / 'data/case_intake_imports/1' / response['batch_id']
    batch = json.loads((store / 'batch.json').read_text('utf8')); batch['schema_version'] = 'unknown'
    (store / 'batch.json').write_text(json.dumps(batch), encoding='utf8')
    assert client.get('/api/case-excel/imports/' + response['batch_id']).status_code == 409
    bad = {**payload(1, op='op_bad_file'), 'file_base64': base64.b64encode(b'bad').decode()}
    assert post(client, 'prepare', bad, csrf).status_code == 422


def test_invalid_row_does_not_claim_whole_file_success(client, settings):
    csrf = login_and_change_password(client)
    data = payload()
    rows = [copy.deepcopy(VECTORS[0]['case_row']), copy.deepcopy(VECTORS[0]['case_row'])]
    rows[1].update(external_case_key='INVALID-ROW', video_content_type_hint='其它', other_type_note='')
    data['file_base64'] = base64.b64encode(workbook(rows)).decode()
    request, _ = prepared(client, data, csrf)
    result = post(client, 'save', request, csrf)
    assert result.status_code == 200, result.text
    assert result.json()['result']['state'] == 'partially_saved'
    assert result.json()['result']['row_results'][1]['state'] == 'invalid'


def test_cross_user_has_no_private_projection_or_foreign_duplicate_details(client, settings, monkeypatch):
    from app import case_uploads
    csrf = login_and_change_password(client)
    request, _ = prepared(client, payload(1), csrf)
    first = post(client, 'save', request, csrf).json()
    monkeypatch.setattr(case_uploads, 'probe_upload', lambda *a: {'duration_seconds': 2, 'width': 64, 'height': 64, 'audio_present': True})
    uploaded = client.post('/api/cases/source-files', params={'url': 'https://www.douyin.com/video/7999999999999999700',
        'suffix': '.mp4', 'rights_confirmed': True, 'source_match_confirmed': True}, content=b'fictional-private-media', headers={'X-CSRF-Token': csrf})
    assert uploaded.status_code == 200, uploaded.text
    provision_user(settings.database_path, '13900000881')
    with TestClient(build_app(settings)) as other:
        login = other.post('/api/auth/login', json={'phone': '13900000881', 'password': '123456'}).json()
        changed = other.post('/api/auth/change-password', json={'current_password': '123456',
            'new_password': 'FictionalSecond2026!', 'confirm_password': 'FictionalSecond2026!'}, headers={'X-CSRF-Token': login['csrf_token']})
        assert changed.status_code == 200, changed.text
        other_csrf = changed.json()['csrf_token']
        assert other.get('/api/case-excel/imports/' + first['batch_id']).status_code == 404
        assert other.get('/api/case-excel/imports').json() == {'batches': []}
        own, _ = prepared(other, payload(1), other_csrf)
        result = post(other, 'save', own, other_csrf)
        assert result.status_code == 200, result.text
        assert result.json()['batch_id'] != first['batch_id']
        assert first['batch_id'] not in result.text
        assert result.json()['result']['row_results'][0]['state'] == 'pending_source'
        foreign_upload = {**payload(1, op='op_foreign_upload'), 'source_uploads': [{'source_row': 5, 'upload_id': uploaded.json()['upload_id']}]}
        rejected = post(other, 'prepare', foreign_upload, other_csrf)
        assert rejected.status_code == 422 and rejected.json()['detail']['code'] == 'IMPORT_UPLOAD_REBIND_REQUIRED'
        assert '13800000000' not in rejected.text and first['batch_id'] not in rejected.text


def test_auth_csrf_strict_input_and_revocation_after_parse(client, settings, monkeypatch):
    assert post(client, 'prepare', payload(1), 'x').status_code == 401
    csrf = login_and_change_password(client)
    assert post(client, 'prepare', payload(1), 'x').status_code == 403
    for change in [{'owner_user_id': 2}, {'dispatch_model': True}, {'selected_rows': [True]}, {'selected_rows': [5, 5]}, {'source_uploads': [{'source_row': 5, 'upload_id': 'a'*32, 'receipt_sha256': 'b'*64}]}]:
        assert post(client, 'prepare', {**payload(1), **change}, csrf).status_code == 422
    original = imports.parser.preview_workbook
    def revoke(data):
        result = original(data)
        with connect(settings.database_path) as db:
            db.execute("UPDATE users SET status='disabled' WHERE id=1")
        return result
    monkeypatch.setattr(imports.parser, 'preview_workbook', revoke)
    result = post(client, 'prepare', payload(1), csrf)
    assert result.status_code == 403
    assert not (settings.pipeline_root / 'data/case_intake_imports').exists()


def test_permission_loss_between_committed_rows_stops_without_erasing_first(client, settings, monkeypatch):
    csrf = login_and_change_password(client)
    request, _ = prepared(client, payload(), csrf)
    def revoke(here):
        if here == 'row_committed':
            with connect(settings.database_path) as db:
                db.execute("UPDATE users SET status='disabled' WHERE id=1")
    monkeypatch.setattr(imports, '_checkpoint', revoke)
    response = post(client, 'save', request, csrf)
    assert response.status_code == 403
    assert len(list((settings.pipeline_root / 'data/case_intake_imports').glob('*/import_*/rows/*.json'))) == 1
    assert len(list((settings.pipeline_root / 'data/case_intake_imports').glob('*/import_*/operations/*/result.json'))) == 0


@pytest.mark.parametrize('point', ['intent', 'row_result', 'result'])
def test_durable_cancel_intent_stops_old_save_even_before_row_markers(client, settings, monkeypatch, point):
    csrf = login_and_change_password(client)
    request, context = prepared(client, payload(), csrf)
    def interrupt_save(here):
        if here == 'row_committed': raise OSError('first row committed, remaining save interrupted')
    monkeypatch.setattr(imports, '_checkpoint', interrupt_save)
    first = post(client, 'save', request, csrf).json()
    assert first['result']['state'] == 'recovery_required'
    fired = False
    def interrupt_cancel(here):
        nonlocal fired
        if here == point and not fired:
            fired = True
            raise OSError('cancel interrupted after durable publication')
    monkeypatch.setattr(imports, '_checkpoint', interrupt_cancel)
    result = post(client, first['batch_id'] + '/cancel', {'operation_id': 'op_cancel_crash', 'expected_head_sha256': first['head_sha256']}, csrf)
    assert fired
    assert result.status_code == 503 or result.json().get('result', {}).get('state') == 'recovery_required'
    monkeypatch.setattr(imports, '_checkpoint', lambda _: None)
    old = post(client, 'save', request, csrf)
    assert old.status_code == 200, old.text
    assert old.json()['result']['row_results'][1]['state'] == 'cancelled'
    assert len(list((settings.pipeline_root / 'data/case_intake_imports').glob('*/import_*/rows/*.json'))) == 1


def test_import_http_rejects_duplicate_keys_and_oversized_json_before_writes(client, settings):
    csrf = login_and_change_password(client)
    route = '/api/case-excel/imports/prepare'
    headers = {'X-CSRF-Token': csrf, 'Content-Type': 'application/json'}
    assert client.post(route, content=b'{}', headers={**headers, 'Content-Type': 'application/octet-stream'}).status_code == 415
    assert client.post(route, content=b'{"operation_id":"one","operation_id":"two"}', headers=headers).status_code == 422
    assert client.post(route, content=b'{}', headers={**headers, 'Content-Length': '9'*5000}).status_code == 413
    assert client.post(route, content=iter([b'x'*(8*1024*1024), b'y']), headers=headers).status_code == 413
    assert not (settings.pipeline_root / 'data/case_intake_imports').exists()


def test_accepted_cancel_does_not_require_expired_media_for_unsaved_row(client, settings, monkeypatch):
    from app import case_uploads
    csrf = login_and_change_password(client)
    monkeypatch.setattr(case_uploads, 'probe_upload', lambda *a: {'duration_seconds': 2, 'width': 64, 'height': 64, 'audio_present': True})
    uploaded = client.post('/api/cases/source-files', params={'url': 'https://www.douyin.com/video/7999999999999999701',
        'suffix': '.mp4', 'rights_confirmed': True, 'source_match_confirmed': True}, content=b'fictional-private-media', headers={'X-CSRF-Token': csrf})
    assert uploaded.status_code == 200
    data = {**payload(), 'source_uploads': [{'source_row': 6, 'upload_id': uploaded.json()['upload_id']}]}
    request, _ = prepared(client, data, csrf)
    def interrupt(here):
        if here == 'row_committed': raise OSError('after first unbound row')
    monkeypatch.setattr(imports, '_checkpoint', interrupt)
    first = post(client, 'save', request, csrf).json()
    def cancel_interrupted(here):
        if here == 'intent': raise OSError('accepted cancel before per-row markers')
    monkeypatch.setattr(imports, '_checkpoint', cancel_interrupted)
    assert post(client, first['batch_id'] + '/cancel', {'operation_id': 'op_cancel_expiring', 'expected_head_sha256': first['head_sha256']}, csrf).status_code == 503
    monkeypatch.setattr(imports, '_checkpoint', lambda _: None)
    class Future(datetime):
        @classmethod
        def now(cls, tz=None): return datetime.now(tz) + timedelta(days=2)
    monkeypatch.setattr(case_uploads, 'datetime', Future)
    result = post(client, 'save', request, csrf)
    assert result.status_code == 200, result.text
    assert result.json()['result']['row_results'][1]['state'] == 'cancelled'
    assert len(list((settings.pipeline_root / 'data/case_intake_imports').glob('*/import_*/rows/*.json'))) == 1
