"""Review counterexamples use actual Native attempts and authenticated End."""
import json
import concurrent.futures
import subprocess
from unittest.mock import patch
from test_creation_batch_orchestration_v1 import external_boundaries
import time
from pathlib import Path
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from test_creative_style_native_v1 import style_runtime
from test_news_novel_runtime_v1_2 import native_news_runtime
from test_creation_batch_native_v1 import config
from test_news_generation_recovery_v1 import worker
from app.main import build_app
from app.database import connect
from app.creation_batch_gateway import advance, state
from app.background_task_service import BackgroundTaskRunner
from app.task_service import get_task, recover_expired_tasks
from publish_copy_native_support import post
from human_review_operations_v1 import read
import native_batch_v1 as native
import content_intent_reservations_v1 as quality
import novel_news_generation_recovery_v1 as recovery
PROJECT = Path(__file__).resolve().parents[2]


def confirmed(client, headers, business, kind, operation):
    body = {**{k: business[k] for k in ('business_id', 'speaker_id')},
        'configuration': config(**{kind: 1}), 'operation_id': operation}
    preview = post(client, '/api/create/batches/preview', headers, body)['preview']
    return post(client, '/api/create/batches/confirm', headers,
        {**body, 'preflight_sha256': preview['source_configuration_sha256']})['result']['batch_id']


def test_ended_unissued_novel_retry_keeps_issued_unknown_ancestor_reserved(node):
    runtime, business, _, _, _ = native_news_runtime(node)
    root = runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login = post(client, '/api/auth/login', {}, {'phone': '13900000001', 'password': 'SyntheticCase2026!'})
        headers = {'X-CSRF-Token': login['csrf_token']}
        bid = confirmed(client, headers, business, 'novel', 'end_unknown_ancestor')
        task = advance(runtime, bid)['task']['task_id']
        rid = get_task(runtime.database_path, task)['subject_ref']
        result = worker(runtime, task, 'sent_without_response')
        assert result.returncode == 92, result.stdout + result.stderr
        runner = BackgroundTaskRunner(runtime)
        try:
            time.sleep(3)
            recover_expired_tasks(runtime.database_path, task_types=('content_generation',), reconciler=runner._reconcile_business_state)
            parent = recovery.head(root, rid)
            child = post(client, '/api/create/novel-news/' + rid + '/retry-generation', headers,
                {'parent_intent_sha256': parent['sha256'], 'confirmation': 'retry_unknown_generation_with_possible_additional_cost'})
            assert child['task']['task_id'] != task
            assert not (recovery.directory(root, rid, recovery.head(root, rid)['operation_id']) / 'dispatch.json').exists()
            post(client, '/api/create/batches/' + bid + '/control', headers, {'action': 'end', 'operation_id': 'end_unissued_retry'})
            assert quality.events(root, business['business_id'], rid)[-1][1]['event'] == 'reserved'
            assert not (root / 'data/generation_requests' / rid / 'generation_request_resolution_v1.json').exists()
            assert get_task(runtime.database_path, child['task']['task_id'])['status'] == 'queued'
        finally: runner.close()


def test_invalid_end_actor_cannot_write_original_request_cancellation(node):
    runtime, business = style_runtime(node)
    root = runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login = post(client, '/api/auth/login', {}, {'phone': '13900000001', 'password': 'SyntheticCase2026!'})
        headers = {'X-CSRF-Token': login['csrf_token']}
        bid = confirmed(client, headers, business, 'persona', 'tampered_end_before_cancel')
        advance(runtime, bid)
        context = read(native.directory(root, bid) / 'permission.json')
        native.control(root, bid, 'end', context, 'original_authenticated_end')
        path = native.directory(root, bid) / 'controls/000001.json'
        original = path.read_bytes(); value = read(path)
        value['actor_intent']['actor_id'] = 'different_actor'
        try:
            path.write_text(json.dumps(value), encoding='utf-8')
            native.settle(root, bid)
            rid = native.groups(root, bid)[0]['request_id']
            assert not (root / 'data/generation_requests' / rid / 'generation_request_resolution_v1.json').exists()
            assert quality.events(root, business['business_id'], rid)[-1][1]['event'] == 'reserved'
        finally: path.write_bytes(original)


def test_end_during_actual_provider_wait_retains_late_result_without_second_dispatch(node):
    runtime,business=style_runtime(node)
    root=runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login['csrf_token']}
        body={**{k:business[k] for k in ('business_id','speaker_id')},'configuration':config(persona=1),'operation_id':'end_during_rpc'}
        pre=post(client,'/api/create/batches/preview',headers,body)['preview']
        bid=post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':pre['source_configuration_sha256']})['result']['batch_id']
        context=read(native.directory(root,bid)/'permission.json')
        task=advance(runtime,bid)['task']['task_id']
        def boundary(command,*args,**kwargs):
            if len(command)>1 and Path(command[1]).name=='resolve_generation_content_plan_v1.py':
                rid=command[command.index('--request-id')+1]
                command=[command[0],str(PROJECT/'internal-console/tests/batch_slow_transport.py'),str(PROJECT/'ops-pipeline/tests/creative_style_synthetic.py'),'plan',str(root),rid]
            return external_boundaries(command,*args,**kwargs)
        runner=BackgroundTaskRunner(runtime)
        marker=root/'data/metrics/batch_inflight_probe'
        try:
            with patch.object(subprocess,'run',boundary),concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future=executor.submit(runner._run,task)
                deadline=time.monotonic()+30
                while not (marker/'entered').is_file():
                    assert not future.done(),get_task(runtime.database_path,task)
                    assert time.monotonic()<deadline
                    time.sleep(0.05)
                started=time.monotonic()
                post(client,'/api/create/batches/'+bid+'/control',headers,{'action':'end','operation_id':'end_issued_work'})
                assert time.monotonic()-started<5
                (marker/'release').write_text('return-original-synthetic-result',encoding='utf-8')
                future.result(timeout=30)
            assert get_task(runtime.database_path,task)['status']=='completed',get_task(runtime.database_path,task)
            assert advance(runtime,bid)=={'advanced':False,'reason':'paused_or_ended'}
            assert state(runtime,bid,context)['status']=='ended_partial'
            assert len(list(root.glob('data/content_plans/*/content_plan_v1_1_1.json')))==1
            assert not list(root.glob('data/generation_batches/*/generation_batch_v1.json'))
            assert not list(root.glob('data/content_ledgers/*/content_ledger_v1.json'))
            with connect(runtime.database_path) as db:
                assert db.execute("SELECT count(*) FROM tasks WHERE task_type='content_generation'").fetchone()[0]==1
        finally:
            if marker.is_dir(): (marker/'release').write_text('release-test-helper',encoding='utf-8')
            runner.close()


def test_other_completed_group_does_not_block_batch_progress_during_next_native_rpc(node):
    from test_creation_batch_capacity_v2 import EVENTS
    runtime,business=style_runtime(node,'story',story_events=EVENTS);root=runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login['csrf_token']}
        body={**{k:business[k] for k in ('business_id','speaker_id')},'configuration':config(story=5),'operation_id':'multi_group_inflight_projection'}
        pre=post(client,'/api/create/batches/preview',headers,body)['preview']
        bid=post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':pre['source_configuration_sha256']})['result']['batch_id']
        context=read(native.directory(root,bid)/'permission.json');runner=BackgroundTaskRunner(runtime)
        marker=root/'data/metrics/batch_inflight_probe'
        try:
            with patch.object(subprocess,'run',external_boundaries):
                for _ in range(2):
                    tid=advance(runtime,bid)['task']['task_id'];runner._run(tid)
                    assert get_task(runtime.database_path,tid)['status']=='completed'
            tid=advance(runtime,bid)['task']['task_id']
            def boundary(command,*args,**kwargs):
                if len(command)>1 and Path(command[1]).name=='resolve_generation_content_plan_v1.py':
                    rid=command[command.index('--request-id')+1]
                    command=[command[0],str(PROJECT/'internal-console/tests/batch_slow_transport.py'),str(PROJECT/'ops-pipeline/tests/creative_style_synthetic.py'),'plan',str(root),rid]
                return external_boundaries(command,*args,**kwargs)
            with patch.object(subprocess,'run',boundary),concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future=executor.submit(runner._run,tid);deadline=time.monotonic()+30
                while not (marker/'entered').is_file():
                    assert not future.done(),get_task(runtime.database_path,tid)
                    assert time.monotonic()<deadline;time.sleep(.05)
                started=time.monotonic();response=client.get('/api/create/batches/'+bid)
                elapsed=time.monotonic()-started
                assert response.status_code==200,response.text
                projected=response.json()['state']
                assert elapsed<5,elapsed
                assert projected['verification_deferred'] and projected['counts']['unverified']==4,projected
                assert projected['status']=='generating' and not projected['completion_proven']
                (marker/'release').write_text('return-original-synthetic-result',encoding='utf-8');future.result(timeout=30)
            assert get_task(runtime.database_path,tid)['status']=='completed'
            fresh=state(runtime,bid,context)
            assert fresh['counts']['generated']==2 and fresh['counts']['approved']==0,fresh
            assert not fresh['generation_quiescent'] and fresh['status']=='in_progress',fresh
            assert not (root/'data/content_ledgers'/business['business_id']/'content_ledger_v1.json').exists()
        finally:
            if marker.is_dir():(marker/'release').write_text('release-test-helper',encoding='utf-8')
            runner.close()
