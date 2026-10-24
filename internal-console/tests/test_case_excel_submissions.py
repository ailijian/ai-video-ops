"""Owned import projections must not become Native Case, Task or review authority."""
import json
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app import case_excel_import as imports
from app.auth_service import provision_user, resolve_session
from app.database import connect
from app.main import build_app
from conftest import login_and_change_password
from test_case_excel_import import payload, post, prepared, protected


@pytest.fixture
def ordinary(settings):
    # An ordinary submitter: deliberately no Reviewer grant.
    with TestClient(build_app(settings)) as client:
        provision_user(settings.database_path, '13800000000')
        yield client, login_and_change_password(client)


def mine(client, **query):
    response = client.get('/api/cases', params={'view': 'mine', **query})
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'private, no-store, max-age=0'
    return response.json()


def save(client, csrf, data=None):
    request, context = prepared(client, data or payload(), csrf)
    response = post(client, 'save', request, csrf)
    assert response.status_code == 200, response.text
    return request, context, response.json()


def test_owned_cards_have_exact_row_links_but_no_case_or_task_or_type_authority(ordinary, settings):
    client, csrf = ordinary
    _, context, saved = save(client, csrf)
    before = protected(settings)
    cards = mine(client)
    assert cards['total'] == 2
    assert cards['capabilities']['case_library_reviewer'] is False
    assert cards['status_counts'] == {'import_source_pending': 2}
    for card in cards['cases']:
        ref = card['import_ref']
        assert ref['batch_id'] == saved['batch_id']
        assert ref['operation_id'] == context['intent']['operation_id']
        assert ref['intent_sha256'] == context['intent_sha256']
        assert {k: ref[k] for k in ('row_id', 'row_sha256')} in context['intent']['selected_rows']
        assert card['submission_id'] == f"excel:{saved['batch_id']}:{ref['row_id']}"
        query = parse_qs(urlsplit(card['href']).query)
        assert query == {'operation': [ref['operation_id']], 'view': ['cases'], 'row': [ref['row_id']]}
        assert card['case_id'] is card['task_id'] is card['video_type'] is None
        assert card['submitted_at'] is card['updated_at'] is None  # R2 has no trusted timestamp.
        assert card['authority'] == {'can_dispatch': False, 'can_approve': False, 'can_share': False}
        assert 'raw_case' not in card and 'raw_segments' not in card and 'raw_rights' not in card
    assert mine(client)['cases'] == cards['cases']
    assert protected(settings) == before
    assert client.get('/api/cases?view=review').status_code in {403, 404}
    assert not any(c.get('source_kind') == 'excel_import' for c in client.get('/api/cases?view=shared').json()['cases'])
    assert mine(client, status='import_source_pending', page_size=1)['total'] == 2
    assert len(mine(client, page_size=1, page=2)['cases']) == 1
    assert mine(client, video_type='故事型')['total'] == 0  # Hint cannot pass formal type filtering.


def test_foreign_principal_cannot_read_cards_rows_or_source_relationships(ordinary, settings):
    client, csrf = ordinary
    _, _, result = save(client, csrf)
    with TestClient(build_app(settings)) as other:
        provision_user(settings.database_path, '13900000881')
        login = other.post('/api/auth/login', json={'phone': '13900000881', 'password': '123456'}).json()
        changed = other.post('/api/auth/change-password', json={'current_password': '123456',
            'new_password': 'FictionalSecond2026!', 'confirm_password': 'FictionalSecond2026!'},
            headers={'X-CSRF-Token': login['csrf_token']})
        assert changed.status_code == 200
        assert mine(other)['total'] == 0
        assert other.get('/api/case-excel/imports/' + result['batch_id']).status_code == 404
        _, _, own = save(other, changed.json()['csrf_token'])
        assert own['batch_id'] != result['batch_id']
        assert result['batch_id'] not in json.dumps(mine(other))
    assert mine(client)['total'] == 2


def test_latest_operation_uses_parent_chain_not_lexicographic_operation_id(ordinary, settings):
    client, csrf = ordinary
    first = payload(op='zz_first'); first['selected_rows'] = [5]
    save(client, csrf, first)
    second = {**first, 'operation_id': 'aa_latest'}
    save(client, csrf, second)
    cards = mine(client)['cases']
    assert len(cards) == 1
    assert cards[0]['import_ref']['operation_id'] == 'aa_latest'
    assert len(list((settings.pipeline_root/'data/case_intake_imports').glob('*/import_*/rows/*.json'))) == 1


def test_partial_and_cancelled_operations_show_only_persisted_rows_without_false_completion(ordinary, settings, monkeypatch):
    client, csrf = ordinary
    request, _ = prepared(client, payload(), csrf)
    def interrupt(point):
        if point == 'row':
            raise OSError('row exists but no final receipt')
    monkeypatch.setattr(imports, '_checkpoint', interrupt)
    first = post(client, 'save', request, csrf).json()
    cards = mine(client)['cases']
    assert len(cards) == 1 and cards[0]['status'] == 'import_save_unconfirmed'
    monkeypatch.setattr(imports, '_checkpoint', lambda _: None)
    response = post(client, first['batch_id'] + '/cancel',
                    {'operation_id': 'aa_cancel', 'expected_head_sha256': first['head_sha256']}, csrf)
    assert response.status_code == 200, response.text
    cards = mine(client)['cases']
    assert len(cards) == 1 and cards[0]['import_ref']['operation_id'] == 'aa_cancel'
    assert cards[0]['status'] == 'import_source_pending'
    assert protected(settings)[1:] == ([], [])


@pytest.mark.parametrize('field,value', [('schema_version', 'unknown'), ('raw_case', {'source_title': 'tampered'})])
def test_corrupt_candidate_fails_closed_instead_of_silently_disappearing(ordinary, settings, field, value):
    client, csrf = ordinary
    _, _, saved = save(client, csrf)
    directory = settings.pipeline_root/'data/case_intake_imports/1'/saved['batch_id']
    path = next((directory/'rows').glob('*.json'))
    data = json.loads(path.read_text('utf8')); data[field] = value
    path.write_text(json.dumps(data), encoding='utf8')
    response = client.get('/api/cases?view=mine')
    assert response.status_code == 409
    assert response.json()['detail']['code'] == 'IMPORT_HISTORY_INVALID'
    assert 'tampered' not in response.text


@pytest.mark.parametrize('mode', ['revoke', 'expire'])
def test_permission_revocation_during_projection_prevents_private_response(ordinary, settings, monkeypatch, mode):
    client, csrf = ordinary
    save(client, csrf)
    original = imports.detail
    def revoke(*args):
        result = original(*args)
        with connect(settings.database_path) as db:
            if mode == 'revoke':
                db.execute("UPDATE users SET status='disabled' WHERE id=1")
            else:
                db.execute("UPDATE sessions SET expires_at='2000-01-01T00:00:00+00:00' WHERE user_id=1")
        return result
    monkeypatch.setattr(imports, 'detail', revoke)
    response = client.get('/api/cases?view=mine')
    assert response.status_code == 403
    assert response.json()['detail']['code'] == 'IMPORT_ACCESS_CHANGED'
    assert 'cases' not in response.json()


def test_current_upload_expiry_changes_projection_without_rewriting_saved_record(ordinary, settings, monkeypatch):
    from app import case_uploads
    client, csrf = ordinary
    monkeypatch.setattr(case_uploads, 'probe_upload', lambda *a: {'duration_seconds': 2, 'width': 64, 'height': 64, 'audio_present': True})
    uploaded = client.post('/api/cases/source-files', params={'url': 'https://www.douyin.com/video/7999999999999999700',
        'suffix': '.mp4', 'rights_confirmed': True, 'source_match_confirmed': True},
        content=b'fictional-boundary-media', headers={'X-CSRF-Token': csrf})
    assert uploaded.status_code == 200, uploaded.text
    data = payload(1); data['source_uploads'] = [{'source_row': 5, 'upload_id': uploaded.json()['upload_id']}]
    save(client, csrf, data)
    assert mine(client)['cases'][0]['status'] == 'import_saved_unverified'
    paths = list((settings.pipeline_root/'data/case_intake_imports').rglob('*.json'))
    before = {p: p.read_bytes() for p in paths}
    class Future(datetime):
        @classmethod
        def now(cls, tz=None): return datetime.now(tz) + timedelta(days=2)
    monkeypatch.setattr(case_uploads, 'datetime', Future)
    assert mine(client)['cases'][0]['status'] == 'import_source_pending'
    assert {p: p.read_bytes() for p in paths} == before


def test_direct_projection_cannot_substitute_another_user_for_the_session(ordinary, settings):
    from app.case_list_projection import my_submissions
    client, _ = ordinary
    session = resolve_session(settings.database_path, client.cookies.get(settings.session_cookie_name))
    with pytest.raises(imports.ImportError, match='IMPORT_ACCESS_CHANGED'):
        my_submissions(settings, session.user['id'] + 1, session=session)
