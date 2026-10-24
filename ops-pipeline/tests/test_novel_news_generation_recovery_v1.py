"""Native REC-01 protocol protection; disposable sources, no paid transport."""
import json
import sqlite3
import threading
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import novel_news_v1 as owner
import novel_news_generation_recovery_v1 as recovery
import profile_compatibility_decisions_v1_1 as persistence
from test_novel_news_v1 import fixture
from news_export_support import context


@pytest.fixture
def flow(tmp_path):
    root, rid, beats = fixture(tmp_path)
    auth = context(root)
    with sqlite3.connect(auth['authorization']['database_path']) as db:
        db.execute('CREATE TABLE tasks(operation_identity TEXT,status TEXT,lease_expires_at TEXT)')
    attempt = owner.prepare_novel_news_generation(pipeline_root=root, request_id=rid, authorization_context=auth)
    def run(attempt=attempt, transport=None):
        return owner.generate_novel_news_plan(pipeline_root=root, request_id=rid,
            operation_id=attempt['operation_id'], intent_sha256=attempt['sha256'], authorization_context=auth,
            transport=transport or (lambda prompt: {'payload': {'beats': beats}}))
    return root, rid, beats, auth, attempt, run


def test_intent_before_dispatch_can_resume_once(flow, monkeypatch):
    root, rid, _, _, attempt, run = flow
    persist = recovery.record
    def stop(*args, **kwargs):
        if args[3] == 'dispatch':
            raise InterruptedError('before dispatch')
        return persist(*args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(recovery, 'record', stop)
        with pytest.raises(InterruptedError): run()
    assert owner.novel_generation_state(root, rid)['recovery_state'] == 'not_dispatched'
    plan = run()
    assert run(transport=lambda p: pytest.fail('Replay must not call model')) == plan
    assert owner.novel_generation_state(root, rid)['ready_for_human_review']


def test_response_replayed_without_transport_after_plan_write_failure(flow, monkeypatch):
    root, rid, _, _, attempt, run = flow
    persist = persistence.write_once
    def stop(path, value, **kwargs):
        if Path(path).name == 'novel_news_beat_plan_v1.json':
            raise InterruptedError('before plan')
        return persist(path, value, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(persistence, 'write_once', stop)
        with pytest.raises(InterruptedError): run()
    response = recovery.directory(root, rid, attempt['operation_id']) / 'response.json'
    original = response.read_bytes()
    assert owner.novel_generation_state(root, rid)['recovery_state'] == 'validated_result_unpublished'
    run(transport=lambda p: pytest.fail('Prepared response must be reused'))
    assert response.read_bytes() == original


def test_unknown_never_dispatches_and_new_attempt_fences_late_worker(flow):
    root, rid, beats, auth, original, run = flow
    entered, release = threading.Event(), threading.Event()
    def slow(prompt):
        entered.set()
        assert release.wait(15)
        return {'payload': {'beats': beats}}
    with ThreadPoolExecutor(1) as executor:
        old = executor.submit(run, transport=slow)
        assert entered.wait(10)
        try:
            assert owner.novel_generation_state(root, rid)['recovery_state'] == 'dispatched_outcome_unknown'
            new = owner.prepare_novel_news_generation(pipeline_root=root, request_id=rid,
                authorization_context=auth, expected_parent=original['sha256'])
            assert new['intent']['parent']['sha256'] == original['sha256']
            assert owner.prepare_novel_news_generation(pipeline_root=root, request_id=rid,
                authorization_context=auth, expected_parent=original['sha256']) == new
            plan = run(attempt=new)
            before = owner._paths(root, rid)['plan'].read_bytes()
        finally:
            release.set()
        with pytest.raises(recovery.GenerationError) as error: old.result(10)
        assert error.value.code == 'NEWS_GENERATION_SUPERSEDED'
    assert owner._paths(root, rid)['plan'].read_bytes() == before
    assert plan['generation_attempt']['operation_id'] == new['operation_id']
    assert recovery.evidence(root, rid, original, 'response') is not None


@pytest.mark.parametrize('change', ['source', 'memory', 'actor', 'revoke', 'parameters'])
def test_current_input_and_authorization_changes_fail_closed(flow, change, monkeypatch):
    root, rid, _, auth, _, run = flow
    if change == 'source':
        path = owner._paths(root, rid)['source_plan']
        path.write_text(path.read_text('utf-8') + '\n', encoding='utf-8')
    elif change == 'memory':
        path = root / 'data/content_ledgers/business/content_ledger_v1.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"entries": []}', encoding='utf-8')
    elif change == 'actor':
        auth['actor'] = {**auth['actor'], 'user_id': 2}
    elif change == 'revoke':
        with sqlite3.connect(auth['authorization']['database_path']) as db:
            db.execute("UPDATE users SET status='disabled' WHERE id=1")
    else:
        monkeypatch.setenv('DEEPSEEK_MODEL', 'changed-model')
    with pytest.raises(recovery.GenerationError):
        run(transport=lambda p: pytest.fail('Changed input cannot reach model'))
    assert not owner._paths(root, rid)['plan'].exists()


def test_invalid_saved_response_is_confirmed_failure_not_ready(flow):
    root, rid, _, _, _, run = flow
    with pytest.raises(owner.NovelNewsError): run(transport=lambda p: {'payload': {'beats': []}})
    state = owner.novel_generation_state(root, rid)
    assert state['recovery_state'] == 'confirmed_failure' and not state['ready_for_human_review']
    with pytest.raises(owner.NovelNewsError):
        run(transport=lambda p: pytest.fail('Invalid saved response is not redispatched'))


def test_same_operation_cannot_dispatch_again_after_unknown(flow):
    root, rid, _, _, attempt, run = flow
    def lost(prompt): raise TimeoutError('external outcome unknown')
    with pytest.raises(TimeoutError): run(transport=lost)
    assert recovery.evidence(root, rid, attempt, 'dispatch')
    with pytest.raises(recovery.GenerationError) as error:
        run(transport=lambda p: pytest.fail('Unknown cannot redispatch'))
    assert error.value.code == 'NEWS_GENERATION_OUTCOME_UNKNOWN'


def test_schema_exports_are_exact_and_unknown_fields_fail_closed(flow):
    root, rid, _, _, attempt, _ = flow
    schemas = Path(owner.__file__).resolve().parents[1] / 'schemas'
    assert json.loads((schemas / 'novel-news-generation-intent-v1.schema.json').read_text('utf-8')) == {
        '$schema': 'https://json-schema.org/draft/2020-12/schema', **recovery.SCHEMAS['intent']}
    with pytest.raises(recovery.GenerationError): recovery.validate({**attempt['intent'], 'force': True}, 'intent')
    with pytest.raises(recovery.GenerationError): recovery.validate({**attempt['intent'], 'schema_version': 'unknown'}, 'intent')


def test_partial_plan_or_wrong_result_never_projects_ready(flow):
    root, rid, _, _, attempt, run = flow
    run()
    path = owner._paths(root, rid)['plan']
    plan = json.loads(path.read_text('utf-8'))
    plan['micro_information_beats'][0]['text'] = '未经批准的价格1元'
    path.write_text(json.dumps(plan, ensure_ascii=False), encoding='utf-8')
    with pytest.raises((owner.NovelNewsError, recovery.GenerationError)):
        owner.novel_generation_state(root, rid)


def test_unbound_legacy_open_plan_cannot_create_new_human_approval(tmp_path):
    root, rid, beats = fixture(tmp_path)
    paths = owner._paths(root, rid)
    ctx = owner._source_context(root, rid)
    # Negative legacy input fixture, never an Approved Artifact.
    plan = {'schema_version': owner.SCHEMA, 'request_id': rid, 'created_at': owner._now(),
        'status': 'review_required', 'generated_by': 'legacy-fixture',
        'request_sha256': recovery.file_sha(paths['request']),
        'source_plan_sha256': recovery.file_sha(paths['source_plan']),
        'selected_concept_id': ctx['selected']['concept_id'], 'selected_pattern_id': ctx['pattern_id'],
        'micro_information_beats': owner._normalize_beats(beats, ctx)}
    owner._write_new(paths['plan'], plan)
    original = paths['plan'].read_bytes()
    with pytest.raises(recovery.GenerationError) as error:
        owner.review_novel_news_plan(pipeline_root=root, request_id=rid,
            reviewer='not an authority bypass', decisions=[{'beat_id': b['beat_id'], 'decision': 'approved'}
                                                        for b in plan['micro_information_beats']])
    assert error.value.code == 'NEWS_GENERATION_LEGACY_UNBOUND_PLAN'
    assert not paths['approved'].exists() and not paths['review'].exists()
    assert paths['plan'].read_bytes() == original
