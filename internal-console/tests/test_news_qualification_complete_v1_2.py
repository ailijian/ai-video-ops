"""Both real Native outcomes, then original versioned Founder qualification."""
import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from test_news_novel_runtime_v1_2 import native_news_runtime
from test_news_generation_recovery_v1 import create, worker
from test_profile_compatibility_golden_v1_1 import exercise_creation_tasks
from news_golden_support_v1_2 import prepare_news_business
from app.main import build_app
from app.background_task_service import BackgroundTaskRunner
from app.task_service import get_task
from profile_compatibility_decisions_v1_1 import read, file_sha
from profile_compatibility_contract_v1_1 import CompatibilityError
from profile_compatibility_contract_v1_2 import FOUNDER
from profile_compatibility_release_v1_1 import effective_runtime
from news_qualification_v1_2 import create_evidence, validate_evidence


def native_task(runtime, response):
    assert response.status_code == 200, response.text
    tid = response.json()['task']['task_id']
    runner = BackgroundTaskRunner(runtime)
    try:
        runner._run(tid)
        assert get_task(runtime.database_path, tid)['status'] == 'completed', get_task(runtime.database_path, tid)
    finally:
        runner.close()
    return tid


def novel_flow(client, headers, runtime, business):
    root = runtime.pipeline_root
    rid, tid = create(client, headers, business, 'complete_native_novel_qualification')
    assert worker(runtime, tid, 'success').returncode == 0
    assert get_task(runtime.database_path, tid)['status'] == 'completed'
    with pytest.raises((RuntimeError, OSError)):
        create_evidence(root, rid, 'novel_content')
    url = '/api/create/novel-news/' + rid
    assert client.get(url + '/excel').status_code != 200
    plan = read(root / 'data/generation_batches' / rid / 'novel_news_beat_plan_v1.json')
    decisions = [{'beat_id': b['beat_id'], 'decision': 'approved'} for b in plan['micro_information_beats']]
    text = plan['micro_information_beats'][-1]['text']
    decisions[-1].update(decision='revised', revised_text=text[:2] + ' ' + text[2:])
    response = client.post(url + '/review', headers=headers, json={'decisions': decisions})
    assert response.status_code == 200, response.text
    tid = native_task(runtime, client.post(url + '/export', headers=headers))
    result = client.get(url + '/excel')
    assert result.status_code == 200 and result.content[:2] == b'PK'
    receipt = read(root / 'data/generation_batches' / rid / 'novel_news_export_receipt_v1.json')
    assert Path(receipt['output_path']).read_bytes() == result.content
    navigation = client.get('/api/create/request-context', params={
        'request_id': rid, 'mode': 'novel', 'business_id': business['business_id']})
    assert navigation.status_code == 200 and navigation.json()['status'] == 'exported', navigation.text
    before = file_sha(Path(receipt['output_path']))
    for _ in range(2):
        replay = client.post(url + '/export', headers=headers)
        assert replay.status_code == 200 and replay.json()['accepted'] is False, replay.text
        assert replay.json()['task']['task_id'] == tid
        assert file_sha(Path(receipt['output_path'])) == before
    proof = create_evidence(root, rid, 'novel_content')
    assert validate_evidence(root, proof)['reuse_intent'] == 'novel_content'
    return rid, proof


def repurpose_flow(client, headers, runtime, business, *, key='complete_repurpose',record_isolated_evidence=True):
    root = runtime.pipeline_root
    created = client.post('/api/create/confirm', headers=headers, json={
        'business_id': business['business_id'], 'speaker_id': business['speaker_id'], 'profile': 'mix',
        'requested_quantity': 1, 'confirmed_quantity': 1, 'idempotency_key': key + '_mix_source'})
    assert created.status_code == 200, created.text
    rid = created.json()['result']['request_id']
    assert client.post('/api/create/' + rid + '/resolve-sources', headers=headers).status_code == 200
    exercise_creation_tasks(client, headers, runtime, rid, Path(__file__).resolve().parents[2],
        transport_operations={'resolve_generation_content_plan_v1.py': 'plan-news-history',
                              'resolve_generation_batch_v1.py': 'generate-news-history'})
    ledger_path = root / 'data/content_ledgers' / business['business_id'] / 'content_ledger_v1.json'
    before = read(ledger_path)['entries']
    response = client.post('/api/create/news/preview', headers=headers, json={
        'business_id': business['business_id'], 'speaker_id': business['speaker_id']})
    assert response.status_code == 200 and response.json()['preview']['available'], response.text
    source = response.json()['preview']['eligible_sources'][0]['source_content_id']
    response = client.post('/api/create/news/request', headers=headers, json={
        'business_id': business['business_id'], 'speaker_id': business['speaker_id'],
        'source_content_id': source, 'idempotency_key': key})
    assert response.status_code == 200, response.text
    nrid = response.json()['result']['request']['request_id']
    navigation = client.get('/api/create/request-context', params={
        'request_id': nrid, 'mode': 'repurpose', 'business_id': business['business_id']})
    assert navigation.status_code == 200 and navigation.json()['mode'] == 'repurpose', navigation.text
    url = '/api/create/news/' + nrid
    native_task(runtime, client.post(url + '/resolve-plan', headers=headers))
    slots = client.get(url + '/delivery').json()['state']['plan']['slots']
    response = client.post(url + '/review', headers=headers, json={
        'items': [{'slot_id': s['slot_id'], 'decision': 'approved'} for s in slots]})
    assert response.status_code == 200, response.text
    tid = native_task(runtime, client.post(url + '/export', headers=headers))
    result = client.get(url + '/excel')
    assert result.status_code == 200 and result.content[:2] == b'PK'
    assert read(ledger_path)['entries'] == before
    for _ in range(2):
        replay = client.post(url + '/export', headers=headers)
        assert replay.status_code == 200 and replay.json()['accepted'] is False, replay.text
        assert replay.json()['task']['task_id'] == tid
    proof = create_evidence(root, nrid, 'cross_profile_repurpose') if record_isolated_evidence else None
    if record_isolated_evidence:
        assert validate_evidence(root, proof)['reuse_intent'] == 'cross_profile_repurpose'
    return nrid, proof


def test_both_native_outcomes_required_then_real_founder_release(node):
    runtime, business, _, repo, owner = native_news_runtime(node, mixed=True)
    root = runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login = client.post('/api/auth/login', json={'phone': '13900000001', 'password': 'SyntheticCase2026!'})
        headers = {'X-CSRF-Token': login.json()['csrf_token']}
        novel, nref = novel_flow(client, headers, runtime, business)
        from profile_compatibility_release_v1_2 import eligibility
        with pytest.raises(CompatibilityError): eligibility(root, [nref], FOUNDER)
        second = prepare_news_business(node, customer_name='明禾新闻历史来源（全虚构）')
        repurpose, rref = repurpose_flow(client, headers, runtime, second)
        protected = {p: p.read_bytes() for parent in (
            root / 'data/generation_batches' / novel, root / 'data/news_deliveries' / repurpose)
            for p in parent.glob('*') if p.is_file()}
        parent = effective_runtime(root)['binding']['release_ref']
        package = owner.build_release(root, root.parent.parent / 'founder-pack', repo, contract_version='1.2',
            purpose='isolated-validation', parent_release=parent, eligibility_stage=FOUNDER,
            validation_refs=[nref, rref])
        owner.verify_release(package, repo)
        staged = owner.stage_release_v1_1(package, root, repo)
        owner.activate_release_v1_1(root, repo, staged, uuid.uuid4().hex)
        current = owner.preflight(root, repo)
        assert current['manifest']['eligibility']['stage'] == FOUNDER
        assert current['manifest']['purpose'] == 'isolated-validation'
        assert all(p.read_bytes() == data for p, data in protected.items())
        assert validate_evidence(root, nref)['request_ref']
        assert validate_evidence(root, rref)['request_ref']
        (root / 'news_complete_qualification.json').write_text(json.dumps({
            'novel_request': novel, 'repurpose_request': repurpose, 'validation_refs': [nref, rref],
            'founder_release': current['binding'], 'production_eligible': False,
        }, ensure_ascii=False, indent=2), encoding='utf-8')
