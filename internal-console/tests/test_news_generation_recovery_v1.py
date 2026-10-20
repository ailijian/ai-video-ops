"""REC-01: real process, HTTP auth, Native authority and expired Task leases."""
import hashlib
import json
import subprocess
import sys
import time
import pytest
from dataclasses import asdict
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from test_news_novel_runtime_v1_2 import native_news_runtime
from app.main import build_app
from app.background_task_service import BackgroundTaskRunner
from app.task_service import get_task, recover_expired_tasks
from novel_news_generation_recovery_v1 import directory, head, read, file_sha

PROJECT = Path(__file__).resolve().parents[2]


def create(client, headers, business, key, *, dispatch_admission=True):
    preview = client.post('/api/create/novel-news/preview', headers=headers, json={
        'business_id': business['business_id'], 'speaker_id': business['speaker_id']})
    assert preview.status_code == 200, preview.text
    response = client.post('/api/create/confirm', headers=headers, json={
        'business_id': business['business_id'], 'speaker_id': business['speaker_id'], 'profile': 'news',
        'requested_quantity': 1, 'confirmed_quantity': 1, 'idempotency_key': key,
        'selected_opportunity_id': preview.json()['projection']['opportunities'][0]['concept_id']})
    assert response.status_code == 200, response.text
    rid = response.json()['result']['request_id']
    response = client.post('/api/create/' + rid + '/resolve-sources', headers=headers)
    assert response.status_code == 200, response.text
    if not dispatch_admission:
        return rid, None
    response = client.post('/api/create/novel-news/' + rid + '/generate', headers=headers)
    assert response.status_code == 200, response.text
    return rid, response.json()['task']['task_id']


def worker(runtime, tid, mode):
    config = runtime.pipeline_root / 'rec01_worker.json'
    value = asdict(runtime)
    value['executing_project'] = str(PROJECT)
    config.write_text(json.dumps(value, default=str), encoding='utf-8')
    return subprocess.run([sys.executable, str(PROJECT / 'internal-console/tests/news_generation_process_worker.py'),
        str(config), tid, mode], capture_output=True, text=True, encoding='utf-8', timeout=65)


def calls(root, rid):
    path = root / 'data/metrics' / rid / 'rec01_calls.jsonl'
    return [json.loads(line) for line in path.read_text('utf-8').splitlines()] if path.exists() else []


@pytest.mark.parametrize('mode', ('dispatch_before_send', 'sent_without_response', 'response_before_save',
                                  'prepared_before_plan', 'plan_before_result', 'result_before_task',
                                  'result_before_task_expired_session'))
def test_rec01_real_process_crash_recovery_and_explicit_retry(node, mode):
    runtime, business, _, _, _ = native_news_runtime(node)
    root = runtime.pipeline_root
    results = []
    with TestClient(build_app(runtime)) as client:
        login = client.post('/api/auth/login', json={'phone': '13900000001', 'password': 'SyntheticCase2026!'})
        assert login.status_code == 200, login.text
        headers = {'X-CSRF-Token': login.json()['csrf_token']}
        runner = BackgroundTaskRunner(runtime)
        try:
            for mode in (mode,):
                rid, tid = create(client, headers, business, 'rec01_' + mode)
                request = root / 'data/generation_requests' / rid / 'generation_request_v1.json'
                request_sha = file_sha(request)
                run = worker(runtime, tid, 'result_before_task' if mode == 'result_before_task_expired_session' else mode)
                assert run.returncode == 92, (mode, run.stdout, run.stderr)
                assert get_task(runtime.database_path, tid)['status'] == 'running'
                before = calls(root, rid)
                if mode == 'result_before_task_expired_session':
                    logout = client.post('/api/auth/logout', headers=headers)
                    assert logout.status_code == 200, logout.text
                time.sleep(3)
                recovered = recover_expired_tasks(runtime.database_path, task_types=('content_generation',),
                    reconciler=runner._reconcile_business_state)
                if mode == 'result_before_task_expired_session':
                    assert get_task(runtime.database_path, tid)['status'] == 'completed'
                    login = client.post('/api/auth/login', json={'phone': '13900000001', 'password': 'SyntheticCase2026!'})
                    assert login.status_code == 200, login.text
                    headers = {'X-CSRF-Token': login.json()['csrf_token']}
                state = client.get('/api/create/novel-news/' + rid + '/state').json()['state']['generation']
                if mode in ('dispatch_before_send', 'sent_without_response', 'response_before_save'):
                    assert get_task(runtime.database_path, tid)['status'] == 'failed'
                    assert state['recovery_state'] == 'dispatched_outcome_unknown'
                    assert rid not in recovered and calls(root, rid) == before
                    replay = client.post('/api/create/novel-news/' + rid + '/generate', headers=headers)
                    assert replay.status_code == 200 and replay.json()['accepted'] is False, replay.text
                    assert calls(root, rid) == before
                    parent = head(root, rid)
                    protected = {p: p.read_bytes() for p in directory(root, rid).rglob('*.json')}
                    retry_payload = {'parent_intent_sha256': parent['sha256'],
                        'confirmation': 'retry_unknown_generation_with_possible_additional_cost'}
                    denied = client.post('/api/create/novel-news/' + rid + '/retry-generation', json=retry_payload)
                    assert denied.status_code == 403, denied.text
                    retry = client.post('/api/create/novel-news/' + rid + '/retry-generation', headers=headers, json=retry_payload)
                    assert retry.status_code == 200, retry.text
                    new_tid = retry.json()['task']['task_id']
                    duplicate = client.post('/api/create/novel-news/' + rid + '/retry-generation', headers=headers, json=retry_payload)
                    assert duplicate.status_code == 200 and duplicate.json()['task']['task_id'] == new_tid, duplicate.text
                    assert new_tid != tid and head(root, rid)['intent']['parent']['sha256'] == parent['sha256']
                    assert all(p.read_bytes() == data for p, data in protected.items())
                    run = worker(runtime, new_tid, 'success')
                    assert run.returncode == 0, (run.stdout, run.stderr)
                    assert get_task(runtime.database_path, new_tid)['status'] == 'completed'
                    assert len(calls(root, rid)) == len(before) + 1
                else:
                    if mode == 'prepared_before_plan':
                        assert tid in recovered
                        run = worker(runtime, tid, 'success')
                        assert run.returncode == 0, (run.stdout, run.stderr)
                    assert get_task(runtime.database_path, tid)['status'] == 'completed'
                    assert calls(root, rid) == before
                assert file_sha(request) == request_sha
                state = client.get('/api/create/novel-news/' + rid + '/state').json()['state']
                assert state['stage'] == 'review' and state['generation']['ready_for_human_review']
                results.append({'mode': mode, 'request_id': rid, 'original_task_id': tid,
                    'calls_before_recovery': len(before), 'calls_after': len(calls(root, rid)),
                    'automatic_additional_calls': 0, 'request_sha256': request_sha})
        finally:
            runner.close()
    (root / 'rec01_process_results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')


def test_real_expired_live_worker_is_fenced_by_explicit_concurrent_retry(node):
    runtime, business, _, _, _ = native_news_runtime(node)
    root = runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login = client.post('/api/auth/login', json={'phone': '13900000001', 'password': 'SyntheticCase2026!'})
        headers = {'X-CSRF-Token': login.json()['csrf_token']}
        rid, tid = create(client, headers, business, 'rec01_live_late_worker')
        config = root / 'rec01_worker.json'
        value = asdict(runtime)
        value['executing_project'] = str(PROJECT)
        config.write_text(json.dumps(value, default=str), encoding='utf-8')
        with (root / 'late-worker.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen([sys.executable, str(PROJECT / 'internal-console/tests/news_generation_process_worker.py'),
                str(config), tid, 'late_response'], stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 60
                while not calls(root, rid) and time.monotonic() < deadline:
                    time.sleep(.1)
                assert len(calls(root, rid)) == 1
                assert process.poll() is None
                # Give the premature-confirmation assertion a deterministic
                # live lease; then inject loss through the original Task API.
                from app.task_service import update_task
                old_task = get_task(runtime.database_path, tid)
                update_task(runtime.database_path, tid, status='running', worker_id=old_task['worker_id'],
                            lease_seconds=30, heartbeat_interval_seconds=0)
                premature = client.post('/api/create/novel-news/' + rid + '/retry-generation', headers=headers,
                    json={'parent_intent_sha256': head(root, rid)['sha256'],
                          'confirmation': 'retry_unknown_generation_with_possible_additional_cost'})
                assert premature.status_code != 200, premature.text
                update_task(runtime.database_path, tid, status='running', worker_id=old_task['worker_id'],
                            lease_seconds=1, heartbeat_interval_seconds=0)
                time.sleep(3)
                runner = BackgroundTaskRunner(runtime)
                try:
                    recover_expired_tasks(runtime.database_path, task_types=('content_generation',),
                                          reconciler=runner._reconcile_business_state)
                finally:
                    runner.close()
                assert get_task(runtime.database_path, tid)['status'] == 'failed'
                parent = head(root, rid)
                payload = {'parent_intent_sha256': parent['sha256'],
                           'confirmation': 'retry_unknown_generation_with_possible_additional_cost'}
                def confirm():
                    return client.post('/api/create/novel-news/' + rid + '/retry-generation', headers=headers, json=payload)
                with ThreadPoolExecutor(2) as threads:
                    responses = list(threads.map(lambda _: confirm(), range(2)))
                assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
                assert responses[0].json()['task']['task_id'] == responses[1].json()['task']['task_id']
                new_tid = responses[0].json()['task']['task_id']
                assert worker(runtime, new_tid, 'success').returncode == 0
                plan_path = root / 'data/generation_batches' / rid / 'novel_news_beat_plan_v1.json'
                plan_bytes = plan_path.read_bytes()
                (root / 'data/metrics' / rid / 'allow_late_response').write_text('release', encoding='utf-8')
                assert process.wait(15) == 0
                assert plan_path.read_bytes() == plan_bytes
                assert get_task(runtime.database_path, tid)['error_code'] == 'NEWS_GENERATION_SUPERSEDED'
                assert len(calls(root, rid)) == 2
                assert len({v['operation_id'] for v in calls(root, rid)}) == 2
                assert get_task(runtime.database_path, new_tid)['status'] == 'completed'
                (root / 'rec01_late_worker_result.json').write_text(json.dumps({
                    'request_id': rid, 'old_task': get_task(runtime.database_path, tid),
                    'new_task': get_task(runtime.database_path, new_tid), 'calls': calls(root, rid),
                    'plan_sha256': file_sha(plan_path), 'late_worker_cannot_replace_plan': True,
                }, ensure_ascii=False, indent=2), encoding='utf-8')
            finally:
                if process.poll() is None:
                    (root / 'data/metrics' / rid / 'allow_late_response').write_text('release', encoding='utf-8')
                    process.wait(15)


@pytest.mark.parametrize('mode', ['before_intent', 'after_intent'])
def test_native_admission_process_exit_cannot_imply_a_model_call(node, mode):
    from app.case_library_access import principal
    from app.database import connect
    from generation_recovery_v1 import authorization
    runtime, business, _, _, _ = native_news_runtime(node)
    root = runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login = client.post('/api/auth/login', json={'phone': '13900000001', 'password': 'SyntheticCase2026!'})
        headers = {'X-CSRF-Token': login.json()['csrf_token']}
        rid, _ = create(client, headers, business, 'rec01_admission_' + mode, dispatch_admission=False)
        with connect(runtime.database_path) as db:
            token = db.execute('SELECT token_hash FROM sessions WHERE user_id=1 ORDER BY rowid DESC LIMIT 1').fetchone()[0]
        actor = principal(runtime, 1)
        auth = {'actor': actor, 'authorization': authorization(runtime.database_path, actor,
            hashlib.sha256(token.encode()).hexdigest())}
        child = subprocess.run([sys.executable, str(PROJECT / 'internal-console/tests/news_generation_process_boundary.py'),
            str(PROJECT), str(root), rid, mode], input=json.dumps({'authorization_context': auth}),
            capture_output=True, text=True, encoding='utf-8', timeout=30)
        assert child.returncode == 91, (child.stdout, child.stderr)
        assert calls(root, rid) == []
        state = client.get('/api/create/novel-news/' + rid + '/state').json()['state']
        assert state['generation']['recovery_state'] == ('not_admitted' if mode == 'before_intent' else 'not_dispatched')
        admitted = client.post('/api/create/novel-news/' + rid + '/generate', headers=headers)
        assert admitted.status_code == 200, admitted.text
        tid = admitted.json()['task']['task_id']
        assert worker(runtime, tid, 'success').returncode == 0
        assert len(calls(root, rid)) == 1
        assert get_task(runtime.database_path, tid)['status'] == 'completed'
