"""Current authority/source/permission fences over real Native Requests."""
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from test_news_novel_runtime_v1_2 import native_news_runtime
from test_news_generation_recovery_v1 import create, worker, calls
from test_profile_compatibility_golden_v1_1 import exercise_creation_tasks
from app.main import build_app
from app.auth_service import provision_user
from app.task_service import get_task
from profile_compatibility_decisions_v1_1 import decision_graph, target_id, preview, decide, read
from profile_compatibility_release_v1_1 import effective_runtime
from novel_news_generation_recovery_v1 import head, directory, file_sha


@pytest.mark.parametrize('change', ['withdraw_reapprove_activate', 'price_revision', 'account_revoke_regrant', 'memory'])
def test_no_external_dispatch_after_current_source_or_authorization_changes(node, change):
    runtime, business, news, repo, owner = native_news_runtime(node, mixed=change == 'memory')
    root = runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login = client.post('/api/auth/login', json={'phone': '13900000001', 'password': 'SyntheticCase2026!'})
        headers = {'X-CSRF-Token': login.json()['csrf_token']}
        rid, tid = create(client, headers, business, 'news_fence_' + change)
        attempt = head(root, rid)
        protected = {p: p.read_bytes() for p in directory(root, rid).rglob('*.json')}
        if change == 'withdraw_reapprove_activate':
            target = news['targets'][0]
            key = target_id(target)
            def decision(action):
                current = decision_graph(root)['heads'][key]
                operation = uuid.uuid4().hex
                p = preview(root, runtime.database_path, news['actor'], operation, [{
                    'target_id': key, 'target': target, 'action': action, 'parent': current['head'],
                    'withdraws': current['effective'] if action == 'withdraw' else None,
                    'reason': 'Explicit isolated current-authority fence validation'}])
                return decide(root, runtime.database_path, news['actor'], operation, p['preview_ref']['sha256'])
            parent = effective_runtime(root)['binding']['release_ref']
            decision('withdraw')
            assert worker(runtime, tid, 'success').returncode == 0
            assert get_task(runtime.database_path, tid)['status'] == 'failed'
            assert calls(root, rid) == []
            decision('approve')
            package = owner.build_release(root, root.parent.parent / 'reapproved-pack', repo,
                contract_version='1.2', purpose='isolated-validation', parent_release=parent)
            staged = owner.stage_release_v1_1(package, root, repo)
            owner.activate_release_v1_1(root, repo, staged, uuid.uuid4().hex)
        elif change == 'price_revision':
            from test_customer_speaker_revision_v1 import review_current
            from review_protocol import post_review
            url = '/api/customers/' + business['business_id']
            detail = client.get(url).json()
            response = client.post(url + '/review-amendments', headers=headers, json={
                'review_context': detail['approval_context']['token'], 'action': 'correct',
                'reason': '全虚构客户明确更正价格，需要新一次独立审核。',
                'changes': [{'field': 'pricing_facts', 'value': ['午餐套餐31元，仅限到店自取，不含配送'],
                             'evidence': '虚构客户明确提供新价格：午餐套餐31元，仅限到店自取，不含配送。'}]})
            assert response.status_code == 200, response.text
            review_current(client, business['business_id'], headers['X-CSRF-Token'])
            response = post_review(client, url + '/persona/approve', headers=headers,
                                   json={'note': 'Explicit Human approval of revised fictional price'})
            assert response.status_code == 200, response.text
        elif change == 'account_revoke_regrant':
            provision_user(runtime.database_path, '13900000001', initial_password='NewFictionalSession2026!', reset_existing=True)
            assert worker(runtime, tid, 'success').returncode == 0
            assert get_task(runtime.database_path, tid)['status'] == 'failed'
            assert calls(root, rid) == []
            login = client.post('/api/auth/login', json={'phone': '13900000001', 'password': 'NewFictionalSession2026!'})
            response = client.post('/api/auth/change-password', headers={'X-CSRF-Token': login.json()['csrf_token']}, json={
                'current_password': 'NewFictionalSession2026!', 'new_password': 'NewFictionalSession2026!!',
                'confirm_password': 'NewFictionalSession2026!!'})
            assert response.status_code == 200, response.text
            headers = {'X-CSRF-Token': response.json()['csrf_token']}
        else:
            created = client.post('/api/create/confirm', headers=headers, json={
                'business_id': business['business_id'], 'speaker_id': business['speaker_id'], 'profile': 'mix',
                'requested_quantity': 1, 'confirmed_quantity': 1, 'idempotency_key': 'native_memory_advance'})
            assert created.status_code == 200, created.text
            other = created.json()['result']['request_id']
            assert client.post('/api/create/' + other + '/resolve-sources', headers=headers).status_code == 200
            exercise_creation_tasks(client, headers, runtime, other, Path(__file__).resolve().parents[2],
                transport_operations={'resolve_generation_content_plan_v1.py': 'plan-news-history',
                                      'resolve_generation_batch_v1.py': 'generate-news-history'})
        if get_task(runtime.database_path, tid)['status'] == 'queued':
            assert worker(runtime, tid, 'success').returncode == 0
        assert get_task(runtime.database_path, tid)['status'] == 'failed'
        assert calls(root, rid) == []
        response = client.post('/api/create/novel-news/' + rid + '/generate', headers=headers)
        assert response.status_code != 200 or response.json().get('accepted') is False, response.text
        assert calls(root, rid) == []
        assert all(p.read_bytes() == data for p, data in protected.items())
        assert head(root, rid)['sha256'] == attempt['sha256']
        assert not (root / 'data/generation_batches' / rid / 'novel_news_beat_plan_v1.json').exists()
