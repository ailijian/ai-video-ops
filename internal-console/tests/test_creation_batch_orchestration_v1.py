"""Actual original background queue and Native owners; external models synthetic."""
from dataclasses import replace
from pathlib import Path
import subprocess
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from test_creation_batch_native_v1 import EVENTS, config
from test_creative_style_native_v1 import style_runtime
from test_news_novel_runtime_v1_2 import native_news_runtime
from publish_copy_native_support import post
from human_review_operations_v1 import read
from app.main import build_app
from app.background_task_service import BackgroundTaskRunner
from app.creation_batch_gateway import advance, state
from app.canonical_gateway import CanonicalOperationError
from app.database import connect
from app.task_service import get_task
import native_batch_v1 as native

PROJECT = Path(__file__).resolve().parents[2]


def external_boundaries(command, *args, **kwargs):
    command = list(command)
    name = Path(command[1]).name if len(command) > 1 else ''
    if name in {'resolve_generation_content_plan_v1.py', 'resolve_generation_batch_v1.py'}:
        root = command[command.index('--pipeline-root')+1]
        rid = command[command.index('--request-id')+1]
        operation = 'plan' if name == 'resolve_generation_content_plan_v1.py' else 'generate'
        extra = [command[command.index('--operation-id')+1],command[command.index('--intent-sha256')+1]] if '--operation-id' in command else []
        command = [command[0], str(PROJECT/'ops-pipeline/tests/creative_style_synthetic.py'), operation, root, rid, *extra]
    elif name == 'novel_news_v1.py' and len(command) > 2 and command[2] == 'generate':
        command[1] = str(PROJECT/'internal-console/tests/batch_novel_synthetic.py')
    elif name == 'publish_copy_v1.py' and len(command) > 2 and command[2] == 'run':
        root=command[command.index('--pipeline-root')+1]
        rid=command[command.index('--request-id')+1]
        command=[command[0],str(PROJECT/'internal-console/tests/publish_copy_process_boundary.py'),
                 str(PROJECT),root,rid,'run','success']
    return REAL_RUN(command, *args, **kwargs)


REAL_RUN = subprocess.run


def test_queued_native_operation_waits_without_repeated_scans_or_duplicate_dispatch(node):
    runtime, business = style_runtime(node, 'story', story_events=EVENTS)
    with TestClient(build_app(runtime)) as client:
        login = post(client, '/api/auth/login', {}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers = {'X-CSRF-Token':login['csrf_token']}
        body = {**{k:business[k] for k in ('business_id','speaker_id')},
            'configuration':config(story=2), 'operation_id':'queued_native_wait'}
        checked = post(client, '/api/create/batches/preview', headers, body)['preview']
        bid = post(client, '/api/create/batches/confirm', headers,
            {**body, 'preflight_sha256':checked['source_configuration_sha256']})['result']['batch_id']
        task = advance(runtime, bid)['task']
        with patch.object(native, 'settle', side_effect=AssertionError('No settlement scan beside active work')):
            result = advance(runtime, bid)
        assert not result['advanced'] and result['reason'] == 'native_task_already_exists'
        assert result['task']['task_id'] == task['task_id']
        assert get_task(runtime.database_path, task['task_id'])['status'] == 'queued'
        with connect(runtime.database_path) as db:
            assert db.execute("SELECT count(*) FROM tasks WHERE task_type='content_generation'").fetchone()[0] == 1
        import app.creation_batch_gateway as gateway
        context = native.current_context(runtime.pipeline_root, bid)
        with patch.object(gateway, 'state', side_effect=AssertionError('No publishing scan before Human approval')):
            assert gateway._advance_publishing(runtime, bid, context) == {
                'advanced':False, 'reason':'native_human_review_required'}


def test_completion_between_task_snapshots_is_verification_in_progress_not_a_failure(node):
    runtime,business=style_runtime(node,'story',story_events=EVENTS);root=runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login['csrf_token']}
        body={**{k:business[k] for k in ('business_id','speaker_id')},'configuration':config(story=2),'operation_id':'task_snapshot_transition'}
        preview=post(client,'/api/create/batches/preview',headers,body)['preview']
        bid=post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':preview['source_configuration_sha256']})['result']['batch_id']
        runner=BackgroundTaskRunner(runtime)
        try:
            with patch.object(subprocess,'run',external_boundaries):
                runner._run(advance(runtime,bid)['task']['task_id'])
                task=advance(runtime,bid)['task'];context=native.current_context(root,bid)
                import app.creation_batch_gateway as gateway
                original=gateway.task_for;captured=[]
                def finish_between_snapshots(settings,rid,operation):
                    value=original(settings,rid,operation)
                    if operation=='script_generation' and not captured:
                        assert value['task_id']==task['task_id'] and value['status']=='queued'
                        captured.append(value)
                        runner._run(value['task_id'])
                        assert get_task(runtime.database_path,value['task_id'])['status']=='completed'
                    return value
                with patch.object(gateway,'task_for',finish_between_snapshots):
                    observed=state(runtime,bid,context)
                assert observed['verification_deferred'] and observed['status']=='generating',observed
                assert not observed['completion_proven'] and not observed['execution_needs_attention']
                final=state(runtime,bid,context)
                assert final['counts']['generated']==2 and final['status']=='awaiting_review',final
                assert final['counts']['approved']==final['counts']['delivered']==0
                assert not (root/'data/content_ledgers'/business['business_id']/'content_ledger_v1.json').exists()
        finally:runner.close()


@pytest.mark.parametrize('profile', ['story', 'novel'])
def test_original_worker_discovers_confirmed_batch_and_replays_without_new_tasks(node, profile):
    if profile == 'story':
        runtime, business = style_runtime(node, 'story', story_events=EVENTS)
    else:
        runtime, business, _, _, _ = native_news_runtime(node, pricing_facts=[
            '午餐套餐29元，仅限工作日到店自取，不含配送',
            '儿童小份餐15元，仅限周末店内点单，不参与工作日午餐套餐'])
    root = runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login = post(client, '/api/auth/login', {}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers = {'X-CSRF-Token':login['csrf_token']}
        body = {**{k:business[k] for k in ('business_id','speaker_id')},
                'configuration':config(**{profile:2}), 'operation_id':'automatic_finite_batch'}
        checked = post(client, '/api/create/batches/preview', headers, body)['preview']
        bid = post(client, '/api/create/batches/confirm', headers,
            {**body, 'preflight_sha256':checked['source_configuration_sha256']})['result']['batch_id']
        context = read(native.directory(root, bid)/'permission.json')
        # Worker was unavailable at confirmation: persisted Intent is sufficient
        # for the original runner's startup recovery, without a second confirm.
        assert not list(root.glob('data/generation_requests/*/generation_request_v1.json'))
        running = replace(runtime, background_worker_enabled=True, task_heartbeat_seconds=0.25)
        runner = BackgroundTaskRunner(running)
        with patch.object(subprocess, 'run', external_boundaries):
            try:
                runner.start()
                deadline = time.monotonic()+65
                actual = None
                while time.monotonic() < deadline:
                    actual = state(runtime, bid, context)
                    if actual['counts']['generated'] == 2 and actual['status'] == 'awaiting_review':
                        break
                    if actual['status'] in {'needs_attention', 'needs_recovery'}:
                        pytest.fail(str(actual))
                    time.sleep(0.1)
                assert actual['counts']['generated'] == 2, actual
                assert actual['counts']['approved'] == actual['counts']['delivered'] == 0
                assert not actual['completion_proven']
                for _ in range(3):
                    advance(runtime, bid)
                with connect(runtime.database_path) as db:
                    before = [tuple(row) for row in db.execute("SELECT task_id,operation_identity,status FROM tasks WHERE task_type='content_generation' ORDER BY rowid")]
                assert len(before) == 2 and all(row[2] == 'completed' for row in before), before
            finally:
                runner.close()
            restarted = BackgroundTaskRunner(running)
            try:
                restarted.start()
                with connect(runtime.database_path) as db:
                    after = [tuple(row) for row in db.execute("SELECT task_id,operation_identity,status FROM tasks WHERE task_type='content_generation' ORDER BY rowid")]
                assert after == before
            finally:
                restarted.close()
        assert not (root/'data/content_ledgers'/business['business_id']/'content_ledger_v1.json').exists()


def test_pause_before_dispatch_resumes_original_task_once_and_end_stays_partial(node):
    runtime, business = style_runtime(node, 'story', story_events=EVENTS)
    root = runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login = post(client, '/api/auth/login', {}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers = {'X-CSRF-Token':login['csrf_token']}
        body = {**{k:business[k] for k in ('business_id','speaker_id')},
                'configuration':config(story=2), 'operation_id':'pause_finite_batch'}
        checked = post(client, '/api/create/batches/preview', headers, body)['preview']
        bid = post(client, '/api/create/batches/confirm', headers,
            {**body, 'preflight_sha256':checked['source_configuration_sha256']})['result']['batch_id']
        context = read(native.directory(root, bid)/'permission.json')
        task = advance(runtime, bid)['task']['task_id']
        control_url = '/api/create/batches/'+bid+'/control'
        post(client, control_url, headers, {'action':'pause', 'operation_id':'pause_before_rpc'})
        runner = BackgroundTaskRunner(runtime)
        try:
            with patch.object(subprocess, 'run', external_boundaries):
                runner._run(task)
                assert get_task(runtime.database_path, task)['status'] == 'failed'
                assert not list(root.glob('data/metrics/generation_requests/*/style_synthetic_planning_calls.jsonl'))
                resumed = post(client, control_url, headers, {'action':'resume', 'operation_id':'resume_local_once'})
                assert resumed['result']['local_continuations'][0]['task']['task_id'] == task
                post(client, control_url, headers, {'action':'resume', 'operation_id':'resume_local_once'})
                runner._run(task)
                assert get_task(runtime.database_path, task)['status'] == 'completed', get_task(runtime.database_path, task)
                generated = advance(runtime, bid)['task']['task_id']
                runner._run(generated)
                assert get_task(runtime.database_path, generated)['status'] == 'completed'
            post(client, control_url, headers, {'action':'end', 'operation_id':'end_with_generated'})
            old = post(client, control_url, headers, {'action':'resume', 'operation_id':'resume_local_once'})
            assert old['result']['local_continuations'] == []
            actual = state(runtime, bid, context)
            assert actual['status'] == 'ended_partial' and actual['counts']['generated'] == 2
            assert actual['counts']['approved'] == 0 and not actual['completion_proven']
            assert advance(runtime, bid) == {'advanced':False, 'reason':'paused_or_ended'}
            calls = list(root.glob('data/metrics/generation_requests/*/style_synthetic_planning_calls.jsonl'))
            assert len(calls) == 1 and len(calls[0].read_text().splitlines()) == 1
            with connect(runtime.database_path) as db:
                assert db.execute("SELECT count(*) FROM tasks WHERE task_type='content_generation'").fetchone()[0] == 2
        finally:
            runner.close()


def test_received_rejected_persona_does_not_block_distinct_story_or_refill(node):
    runtime, business = style_runtime(node, 'story', story_events=EVENTS)
    root = runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login = post(client, '/api/auth/login', {}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers = {'X-CSRF-Token':login['csrf_token']}
        body = {**{k:business[k] for k in ('business_id','speaker_id')},
                'configuration':config(persona=1, story=2), 'operation_id':'one_rejected_two_good'}
        checked = post(client, '/api/create/batches/preview', headers, body)['preview']
        bid = post(client, '/api/create/batches/confirm', headers,
            {**body, 'preflight_sha256':checked['source_configuration_sha256']})['result']['batch_id']
        context = read(native.directory(root, bid)/'permission.json')
        def reject_persona(command, *args, **kwargs):
            command = list(command)
            if len(command)>1 and Path(command[1]).name == 'resolve_generation_batch_v1.py':
                rid = command[command.index('--request-id')+1]
                request = read(root/'data/generation_requests'/rid/'generation_request_v1.json')
                if request['creative_style']['style_id'] == 'persona':
                    command = [command[0], str(PROJECT/'ops-pipeline/tests/creative_style_synthetic.py'),
                               'generate-invalid-persona', str(root), rid]
            return external_boundaries(command, *args, **kwargs)
        runner = BackgroundTaskRunner(runtime)
        try:
            with patch.object(subprocess, 'run', reject_persona):
                for _ in range(4):
                    next_step = advance(runtime, bid)
                    assert next_step.get('task'), next_step
                    runner._run(next_step['task']['task_id'])
                final = advance(runtime, bid)
                assert final['reason'] == 'native_human_review_required', final
            actual = state(runtime, bid, context)
            assert actual['counts']['target'] == 3 and actual['counts']['generated'] == 2
            assert actual['counts']['failed'] == 1 and actual['counts']['missing_generation'] == 1
            assert actual['counts']['approved'] == 0 and not actual['completion_proven']
            assert len(list(root.glob('data/generation_requests/*/generation_request_v1.json'))) == 2
            for group in native.groups(root, bid):
                for stage in ('planning', 'provider'):
                    path = root/'data/metrics/generation_requests'/group['request_id']/('style_synthetic_'+stage+'_calls.jsonl')
                    assert len(path.read_text().splitlines()) == 1
            for _ in range(3):
                advance(runtime, bid)
            with connect(runtime.database_path) as db:
                assert db.execute("SELECT count(*) FROM tasks WHERE task_type='content_generation'").fetchone()[0] == 4
        finally:
            runner.close()


def test_native_partial_generation_preserves_second_slot_and_human_reviews_actual_item(node):
    runtime, business = style_runtime(node, 'story', story_events=EVENTS)
    root = runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login = post(client, '/api/auth/login', {}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers = {'X-CSRF-Token':login['csrf_token']}
        body = {**{k:business[k] for k in ('business_id','speaker_id')},
                'configuration':config(story=2), 'operation_id':'partial_second_slot'}
        checked = post(client, '/api/create/batches/preview', headers, body)['preview']
        bid = post(client, '/api/create/batches/confirm', headers,
            {**body, 'preflight_sha256':checked['source_configuration_sha256']})['result']['batch_id']
        context = read(native.directory(root, bid)/'permission.json')
        def partial(command, *args, **kwargs):
            command = list(command)
            if len(command)>1 and Path(command[1]).name == 'resolve_generation_batch_v1.py':
                rid = command[command.index('--request-id')+1]
                command = [command[0], str(PROJECT/'ops-pipeline/tests/creative_style_synthetic.py'),
                           'generate-partial', str(root), rid]
            return external_boundaries(command, *args, **kwargs)
        runner = BackgroundTaskRunner(runtime)
        try:
            with patch.object(subprocess, 'run', partial):
                for _ in range(2):
                    next_step = advance(runtime, bid)
                    runner._run(next_step['task']['task_id'])
                    assert get_task(runtime.database_path, next_step['task']['task_id'])['status'] == 'completed'
            rid = native.groups(root, bid)[0]['request_id']
            batch = read(root/'data/generation_batches'/rid/'generation_batch_v1.json')
            assert batch['validation']['passed'] is False and batch['generated_count'] == 1
            assert batch['contents'][0]['logical_slot_id'] == native.intent(root, bid)[1]['slots'][1]['slot_id']
            from generation_recovery_v1 import ready_for_review, RecoveryError
            assert ready_for_review(batch, batch['script_generation_contract']['selected_concept_ids'])
            import copy
            forged = copy.deepcopy(batch)
            forged['accepted_subset']['logical_slot_ids'] = [native.intent(root,bid)[1]['slots'][0]['slot_id']]
            with pytest.raises(RecoveryError):
                ready_for_review(forged, batch['script_generation_contract']['selected_concept_ids'])
            projected = state(runtime, bid, context)
            assert projected['counts']['generated'] == projected['counts']['missing_generation'] == 1
            assert not projected['completion_proven']
            post(client, '/api/create/'+rid+'/review', headers, {'items':[
                {'content_id':batch['contents'][0]['content_id'], 'decision':'approved'}]})
            approved = read(root/'data/generation_batches'/rid/'approved_generation_batch_v1.json')
            assert len(approved['contents']) == 1
            assert approved['contents'][0]['logical_slot_id'] == batch['contents'][0]['logical_slot_id']
            for _ in range(3):
                advance(runtime, bid)
            with connect(runtime.database_path) as db:
                assert db.execute("SELECT count(*) FROM tasks WHERE json_extract(payload_json,'$.operation') IN ('content_plan','script_generation')").fetchone()[0] == 2
                assert db.execute("SELECT count(*) FROM tasks WHERE json_extract(payload_json,'$.operation')='publish_copy_generate'").fetchone()[0] == 1
            assert not (root/'data/content_ledgers'/business['business_id']/'content_ledger_v1.json').exists()
        finally:
            runner.close()


@pytest.mark.parametrize('continuation', ['native_confirm', 'batch_resume_saved_response', 'partial_result_crash', 'partial_result_human_crash'])
def test_known_invalid_response_requires_explicit_c305_and_uses_a_distinct_provider_attempt(node, continuation):
    partial = continuation.startswith('partial_result_')
    runtime, business = style_runtime(node, 'story', story_events=EVENTS) if partial else style_runtime(node)
    root = runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login = post(client, '/api/auth/login', {}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers = {'X-CSRF-Token':login['csrf_token']}
        body = {**{k:business[k] for k in ('business_id','speaker_id')},
                'configuration':config(**({'story':2} if partial else {'persona':1})), 'operation_id':'known_invalid_response'}
        checked = post(client, '/api/create/batches/preview', headers, body)['preview']
        bid = post(client, '/api/create/batches/confirm', headers,
            {**body, 'preflight_sha256':checked['source_configuration_sha256']})['result']['batch_id']
        context = read(native.directory(root,bid)/'permission.json')
        rid = native.groups(root,bid)[0]['request_id']
        fail = {'enabled':True, 'crash':continuation == 'batch_resume_saved_response',
                'human_cut':continuation == 'partial_result_human_crash'}
        def boundary(command, *args, **kwargs):
            command = list(command)
            if len(command)>1 and Path(command[1]).name == 'resolve_generation_batch_v1.py' and fail['enabled']:
                command = [command[0],str(PROJECT/'ops-pipeline/tests/creative_style_synthetic.py'),
                           'generate-invalid-response',str(root),rid]
            if len(command)>1 and Path(command[1]).name == 'resolve_generation_batch_v1.py' and '--operation-id' in command and fail['crash']:
                extra = [command[command.index('--operation-id')+1], command[command.index('--intent-sha256')+1]]
                command = [command[0],str(PROJECT/'internal-console/tests/batch_provider_fault.py'),
                    'after-response',str(PROJECT/'ops-pipeline/tests/creative_style_synthetic.py'),
                    'generate',str(root),rid,*extra]
                fail['crash'] = False
            if len(command)>1 and Path(command[1]).name == 'review_generation_batch_v2.py' and fail['human_cut']:
                command = [command[0],str(PROJECT/'ops-pipeline/tests/delivery_receipt_crash.py'),'approved',*command[1:]]
                fail['human_cut'] = False
            return external_boundaries(command,*args,**kwargs)
        runner = BackgroundTaskRunner(runtime)
        try:
            with patch.object(subprocess,'run',boundary):
                for _ in range(2):
                    task = advance(runtime,bid)['task']['task_id']
                    runner._run(task)
                assert get_task(runtime.database_path,task)['status'] == 'failed'
                original = root/'data/generation_batches'/rid/'generation_batch_v1.json'
                old_bytes = original.read_bytes()
                from generation_recovery_v1 import transport_failure
                assert transport_failure(read(original))
                calls = root/'data/metrics/generation_requests'/rid/'style_synthetic_provider_calls.jsonl'
                assert len(calls.read_text().splitlines()) == 1
                for _ in range(3):
                    advance(runtime,bid)
                assert len(calls.read_text().splitlines()) == 1
                prefix = '/api/create/'+rid+'/generation-recovery/'
                preview = post(client,prefix+'preview',headers,{'operation_id':'c'*32})
                payload = {'operation_id':'c'*32,'preview_sha256':preview['preview_sha256']}
                task = post(client,prefix+'confirm',headers,payload)['task']['task_id']
                original_payload = get_task(runtime.database_path,task)['payload']
                fail['enabled'] = False
                if partial:
                    from app.task_service import claim_task, recover_expired_tasks
                    from human_review_operations_v1 import file_sha
                    assert claim_task(runtime.database_path, task, worker_id='synthetic-crashed-worker',
                        lease_seconds=1, stage='Native retry', task_type='content_generation')
                    child = REAL_RUN([runtime.pipeline_python_executable,
                        str(PROJECT/'internal-console/tests/batch_provider_fault.py'),'c3-result',
                        str(PROJECT/'ops-pipeline/tests/creative_style_synthetic.py'),
                        'generate-partial',str(root),rid,'c'*32,
                        file_sha(root/'data/generation_batches'/rid/'recovery'/('c'*32)/'intent.json')],
                        capture_output=True,text=True,timeout=90)
                    assert child.returncode == 93, child.stdout+child.stderr
                    from resolve_generation_batch_v1 import generation_snapshot
                    current = generation_snapshot(root,rid)
                    assert current['execution_completed'] and current['ready_for_human_review'] and not current['generation_completed']
                    if continuation == 'partial_result_human_crash':
                        generated = read(root/'data/generation_batches'/rid/'recovery'/('c'*32)/'generation_batch_v1.json')
                        first = client.post('/api/create/'+rid+'/review',headers=headers,json={'items':[
                            {'content_id':generated['contents'][0]['content_id'],'decision':'approved'}]})
                        assert first.status_code != 200
                        assert (root/'data/generation_batches'/rid/'approved_generation_batch_v1.json').is_file()
                        assert not (root/'data/generation_batches'/rid/'generation_batch_approval_receipt.json').is_file()
                        pending = generation_snapshot(root,rid)
                        assert pending['execution_completed'] and not pending['ready_for_human_review'] and not pending['generation_completed']
                    time.sleep(1.1)
                    recover_expired_tasks(runtime.database_path,task_types=('content_generation',),
                        reconciler=runner._reconcile_business_state)
                else:
                    runner._run(task)
                    if continuation == 'batch_resume_saved_response':
                        assert get_task(runtime.database_path,task)['status'] == 'failed'
                        assert len(calls.read_text().splitlines()) == 2
                        resumed = post(client,'/api/create/batches/'+bid+'/control',headers,
                            {'action':'resume','operation_id':'resume_c305_saved_response'})
                        assert resumed['result']['local_continuations'][0]['task']['task_id'] == task
                        assert get_task(runtime.database_path,task)['payload'] == original_payload
                        assert post(client,prefix+'confirm',headers,payload)['task']['task_id'] == task
                        runner._run(task)
                assert get_task(runtime.database_path,task)['status'] == 'completed', get_task(runtime.database_path,task)
                assert post(client,prefix+'confirm',headers,payload)['task']['task_id'] == task
                assert original.read_bytes() == old_bytes
                assert len(calls.read_text().splitlines()) == 2
                projected = state(runtime,bid,context)
                assert projected['counts']['generated'] == 1 and projected['counts']['unknown'] == 0
                assert projected['counts']['missing_generation'] == int(partial)
                assert projected['counts']['approved'] == 0 and not projected['completion_proven']
                assert len(list(native.directory(root,bid).glob('provider_stages/*/script_generation/recovery_*/*/response.json'))) == 1
                source = read(root/'data/generation_batches'/rid/'recovery'/('c'*32)/'generation_batch_v1.json')
                post(client,'/api/create/'+rid+'/review',headers,{'items':[
                    {'content_id':source['contents'][0]['content_id'],'decision':'approved'}]})
        finally:
            runner.close()


def test_initial_partial_execution_survives_incomplete_human_receipt(node):
    runtime, business = style_runtime(node, 'story', story_events=EVENTS)
    root = runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login = post(client, '/api/auth/login', {}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers = {'X-CSRF-Token':login['csrf_token']}
        body = {**{k:business[k] for k in ('business_id','speaker_id')},
                'configuration':config(story=2), 'operation_id':'initial_partial_human_crash'}
        checked = post(client, '/api/create/batches/preview', headers, body)['preview']
        bid = post(client, '/api/create/batches/confirm', headers,
            {**body, 'preflight_sha256':checked['source_configuration_sha256']})['result']['batch_id']
        context = read(native.directory(root,bid)/'permission.json')
        rid = native.groups(root,bid)[0]['request_id']
        runner = BackgroundTaskRunner(runtime)
        try:
            with patch.object(subprocess,'run',external_boundaries):
                planning = advance(runtime,bid)['task']['task_id']; runner._run(planning)
            task = advance(runtime,bid)['task']['task_id']
            from app.task_service import claim_task,recover_expired_tasks
            assert claim_task(runtime.database_path,task,worker_id='synthetic-crashed-worker',
                lease_seconds=1,stage='Native initial generation',task_type='content_generation')
            child = REAL_RUN([runtime.pipeline_python_executable,
                str(PROJECT/'internal-console/tests/batch_provider_fault.py'),'initial-result',
                str(PROJECT/'ops-pipeline/tests/creative_style_synthetic.py'),'generate-partial',str(root),rid],
                capture_output=True,text=True,timeout=90)
            assert child.returncode == 94,child.stdout+child.stderr
            generated = read(root/'data/generation_batches'/rid/'generation_batch_v1.json')
            human = {'items':[{'content_id':generated['contents'][0]['content_id'],'decision':'approved'}]}
            def interrupt_human(command,*args,**kwargs):
                if len(command)>1 and Path(command[1]).name == 'review_generation_batch_v2.py':
                    command = [command[0],str(PROJECT/'ops-pipeline/tests/delivery_receipt_crash.py'),'approved',*command[1:]]
                return REAL_RUN(command,*args,**kwargs)
            with patch.object(subprocess,'run',interrupt_human):
                interrupted = client.post('/api/create/'+rid+'/review',headers=headers,json=human)
                assert interrupted.status_code != 200
            from resolve_generation_batch_v1 import generation_snapshot
            pending = generation_snapshot(root,rid)
            assert pending['execution_completed'] and not pending['generation_completed'] and not pending['ready_for_human_review']
            assert not (root/'data/generation_batches'/rid/'generation_batch_approval_receipt.json').is_file()
            time.sleep(1.1)
            recover_expired_tasks(runtime.database_path,task_types=('content_generation',),reconciler=runner._reconcile_business_state)
            assert get_task(runtime.database_path,task)['status'] == 'completed'
            actual = state(runtime,bid,context)
            assert actual['counts']['generated'] == actual['counts']['missing_generation'] == 1
            assert actual['counts']['approved'] == 0 and not actual['completion_proven']
            post(client,'/api/create/'+rid+'/review',headers,human)
            assert len((root/'data/metrics/generation_requests'/rid/'style_synthetic_provider_calls.jsonl').read_text().splitlines()) == 1
            with connect(runtime.database_path) as db:
                assert db.execute("SELECT count(*) FROM tasks WHERE task_type='content_generation'").fetchone()[0] == 2
            assert not (root/'data/content_ledgers'/business['business_id']/'content_ledger_v1.json').is_file()
        finally:
            runner.close()


def test_novel_rollout_denial_precedes_intent_and_native_admission(node):
    from app.creation_batch_gateway import admit_group
    runtime,business,_,_,_=native_news_runtime(node)
    root=runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login['csrf_token']}
        body={**{k:business[k] for k in ('business_id','speaker_id')},
              'configuration':config(novel=1),'operation_id':'revoked_before_admission'}
        checked=post(client,'/api/create/batches/preview',headers,body)['preview']
        confirmation={**body,'preflight_sha256':checked['source_configuration_sha256']}
        off=replace(runtime,novel_news_rollout='off')
        with TestClient(build_app(off)) as revoked:
            again=post(revoked,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
            revoked_headers={'X-CSRF-Token':again['csrf_token']}
            for action,payload in [('preview',body),('confirm',confirmation)]:
                denied=revoked.post('/api/create/batches/'+action,headers=revoked_headers,json=payload)
                assert denied.status_code != 200 and denied.json()['detail']['code']=='NOVEL_NEWS_NOT_AVAILABLE',denied.text
            assert not list(root.glob('data/creation_batches/*/intent.json'))
            bid=post(client,'/api/create/batches/confirm',headers,confirmation)['result']['batch_id']
            context=read(native.directory(root,bid)/'permission.json')
            group=native.groups(root,bid)[0]
            for operation in (lambda:admit_group(off,bid,group['group_id'],context),lambda:advance(off,bid)):
                with pytest.raises(CanonicalOperationError) as error:operation()
                assert error.value.code=='NOVEL_NEWS_NOT_AVAILABLE'
            assert not list(root.glob('data/generation_requests/*/generation_request_v1.json'))
            assert not list(root.glob('data/creation_batches/*/admissions/*.json'))
            assert not list(root.glob('data/content_intent_reservations/*/*/events/*.json'))
        admitted=admit_group(runtime,bid,group['group_id'],context)
        assert admitted['request_id']==group['request_id']
        assert len(list(root.glob('data/generation_requests/*/generation_request_v1.json')))==1
