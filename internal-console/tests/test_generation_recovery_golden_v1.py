"""Real isolated human/release/task/review/export chain; only provider transport replaced."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid
import zipfile
import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from compatibility_golden_support import prepare_native_golden, prepare_native_business
from test_profile_compatibility_release_v1_1 import committed_source_snapshot
from profile_compatibility_release_v1_1 import configure_runtime
from app.background_task_service import BackgroundTaskRunner
from app.main import build_app
from app.task_service import get_task
from app.database import connect


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def native_node(node):
    prepare_native_golden(node)
    business = prepare_native_business(node)
    settings, accounts, storage = node
    project = Path(__file__).resolve().parents[2]
    repo, owner = committed_source_snapshot(project, storage / 's')
    root = settings.pipeline_root
    configure_runtime(root, root, purpose='isolated-validation')
    package = owner.build_release(root, storage / 'p', repo, contract_version='1.1', purpose='isolated-validation')
    assert owner.verify_release(package, repo)['approved_cases'] == 3
    staged = owner.stage_release_v1_1(package, root, repo)
    owner.activate_release_v1_1(root, repo, staged, uuid.uuid4().hex)
    owner.preflight(root, repo)
    return replace(settings, pipeline_python_executable=str(project / 'ops-pipeline/.venv/Scripts/python.exe')), business


def login(client):
    response = client.post('/api/auth/login', json={'phone': '13900000001', 'password': 'SyntheticCase2026!'})
    assert response.status_code == 200, response.text
    return {'X-CSRF-Token': response.json()['csrf_token']}


def task_count(settings):
    db = connect(settings.database_path)
    try:
        return db.execute('SELECT count(*) FROM tasks').fetchone()[0]
    finally:
        db.close()


def test_native_failed_request_recovers_and_completed_export_never_enqueues(node):
    settings, business = native_node(node)
    root = settings.pipeline_root
    project = Path(__file__).resolve().parents[2]
    real_run = subprocess.run
    fail = {'enabled': True}
    provider_commands = []
    child_errors = []
    environment = {k:v for k,v in os.environ.items() if not k.startswith(('DEEPSEEK_', 'QYAPI_', 'AIVO_'))}
    environment.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8')

    def boundary(command, *args, **kwargs):
        name = Path(command[1]).name if len(command) > 1 else ''
        mapping = {'resolve_generation_content_plan_v1.py': 'plan',
                   'resolve_generation_batch_v1.py': 'generate-fail' if fail['enabled'] else 'generate'}
        if name in mapping:
            rid = command[command.index('--request-id') + 1]
            operation = mapping[name]
            extra = [command[command.index('--operation-id') + 1], command[command.index('--intent-sha256') + 1]] if '--operation-id' in command else []
            command = [command[0], str(project / 'ops-pipeline/tests/compatibility_creation_synthetic.py'), operation, str(root), rid, *extra]
            provider_commands.append((operation, extra))
            kwargs['env'] = environment
        result = real_run(command, *args, **kwargs)
        if result.returncode:
            child_errors.append((result.stdout, result.stderr))
        return result

    with TestClient(build_app(settings)) as client, patch.object(subprocess, 'run', boundary):
        headers = login(client)
        response = client.post('/api/create/confirm', headers=headers, json={
            'business_id': business['business_id'], 'speaker_id': business['speaker_id'], 'profile':'mix',
            'requested_quantity':1, 'confirmed_quantity':1, 'idempotency_key':'c305_fictional_recovery'})
        assert response.status_code == 200, response.text
        rid = response.json()['result']['request_id']
        prefix = f'/api/create/{rid}'
        assert client.post(prefix+'/resolve-sources', headers=headers).status_code == 200
        runner = BackgroundTaskRunner(settings)

        def execute(endpoint, body=None):
            response = client.post(prefix+endpoint, headers=headers, json=body) if body is not None else client.post(prefix+endpoint, headers=headers)
            assert response.status_code == 200, response.text
            task = response.json()['task']
            runner._run(task['task_id'])
            return get_task(settings.database_path, task['task_id'])

        try:
            assert execute('/resolve-content-plan')['status'] == 'completed'
            failed = execute('/generate-scripts')
            assert failed['status'] == 'failed', failed
            directory = root / 'data/generation_batches' / rid
            old_batch = directory / 'generation_batch_v1.json'
            old_bytes = old_batch.read_bytes()
            batch = json.loads(old_bytes)
            assert batch['status'] == 'generation_incomplete' and batch['contents'] == []
            assert len(batch['rejected_generations']) == 3
            state = client.get(prefix+'/delivery').json()['state']
            assert state['next_action'] == 'RECOVER_GENERATION', state
            assert state['generation']['artifact_present'] and not state['generation']['ready_for_human_review']
            assert state['generation']['can_retry'] is True
            assert runner._reconcile_business_state(failed['task_id']) is None
            before_calls = len(provider_commands)
            assert execute('/generate-scripts')['status'] == 'failed'
            assert len(provider_commands) == before_calls
            op = uuid.uuid4().hex
            preview = client.post(prefix+'/generation-recovery/preview', headers=headers, json={'operation_id':op})
            assert preview.status_code == 200, preview.text
            body = {'operation_id':op, 'preview_sha256':preview.json()['preview_sha256']}
            fail['enabled'] = False
            recovered = execute('/generation-recovery/confirm', body)
            assert recovered['status'] == 'completed', (recovered, child_errors)
            replay = client.post(prefix+'/generation-recovery/confirm', headers=headers, json=body)
            assert replay.status_code == 200 and replay.json()['task']['task_id'] == recovered['task_id'], replay.text
            assert old_batch.read_bytes() == old_bytes
            state = client.get(prefix+'/delivery').json()['state']
            assert state['next_action'] == 'HUMAN_REVIEW', state
            source_ref = state['generation']['batch_ref']
            assert '/recovery/'+op+'/' in source_ref['path']
            source = root/source_ref['path']
            assert sha(source) == source_ref['sha256']
            item = state['generation']['contents'][0]
            # A copied valid Batch cannot obtain a second Human bundle.
            from review_generation_batch_v2 import review_generation_batch_v2, GenerationReviewV2Error
            copied_source=root/'data/disposable_copied_generation.json'
            copied_source.write_bytes(source.read_bytes())
            review_input=root/'data/disposable_review_input.json'
            review_input.write_text(json.dumps({'schema_version':'generation-batch-review-input-v2.0',
                'reviewer':'13900000001','note':'Explicit negative source-path test',
                'items':[{'content_id':item['content_id'],'decision':'approved','note':'Source path must still match'}]}),encoding='utf-8')
            with pytest.raises(GenerationReviewV2Error) as wrong_source:
                review_generation_batch_v2(batch_path=copied_source,review_input_path=review_input)
            assert wrong_source.value.code=='GENERATION_BATCH_NOT_REVIEWABLE'
            assert not (directory/'generation_human_review_v2.json').exists()
            reviewed = client.post(prefix+'/review', headers=headers, json={'items':[{
                'content_id':item['content_id'],'decision':'revised','revised_title':'先把忌口核对清楚',
                'revised_narration':item['narration'],'note':'Explicit fictional Human revision'}], 'note':'No new facts or media rights'})
            assert reviewed.status_code == 200, reviewed.text
            receipt = json.loads((directory/'generation_batch_approval_receipt.json').read_text(encoding='utf-8'))
            assert receipt['source_batch']['sha256'] == sha(source)
            assert (directory/'generation_human_review_v2.json').is_file()
            assert not (source.parent/'generation_human_review_v2.json').exists()
            template = root/'output/素材混剪&数字人口播混剪文案导入模板.xlsx'
            template.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(project/'ops-pipeline/output'/template.name,template)
            copied_approved=root/'data/disposable_copied_approved.json'
            copied_approved.write_bytes((directory/'approved_generation_batch_v1.json').read_bytes())
            denied_export=subprocess.run([settings.pipeline_python_executable,str(root/'scripts/export_mix_excel_v1.py'),
                '--batch',str(copied_approved),'--template',str(template),'--output',str(root/'output/disallowed_copied_export.xlsx')],
                capture_output=True,text=True,encoding='utf-8',env=environment)
            assert denied_export.returncode!=0 and 'canonical Request-root' in denied_export.stderr,denied_export.stderr
            assert not (root/'output/disallowed_copied_export.xlsx').exists()
            exported = execute('/export-mix')
            assert exported['status'] == 'completed', exported
            closure_path = directory/'generation_export_closure_v1.json'
            closure_bytes = closure_path.read_bytes()
            closure = json.loads(closure_bytes)
            ledger = Path(closure['content_ledger']['path'])
            ledger_bytes = ledger.read_bytes()
            assert len(json.loads(ledger_bytes)['entries']) == 1
            excel = Path(closure['excel_export']['path'])
            with zipfile.ZipFile(excel) as z:
                assert z.testzip() is None
                assert '先把忌口核对清楚'.encode() in z.read('xl/worksheets/sheet1.xml')
            count = task_count(settings)
            for _ in range(3):
                result = client.post(prefix+'/export-mix', headers=headers)
                assert result.status_code == 200, result.text
                assert result.json()['recovered'] and result.json()['canonical_result']['recovered']
                assert result.json()['task']['task_id'] == exported['task_id']
                assert task_count(settings) == count
            client.post('/api/auth/logout', headers=headers)
            headers = login(client)
            assert client.post(prefix+'/export-mix', headers=headers).json()['recovered']
            assert task_count(settings) == count
            assert closure_path.read_bytes() == closure_bytes and ledger.read_bytes() == ledger_bytes
            assert old_batch.read_bytes() == old_bytes
            # A historical canonical closure may have no local Task projection.
            # Use a NEW isolated SQLite rather than deleting historical Tasks.
            historical=replace(settings,database_path=settings.database_path.parent/'historical-projection.sqlite3',session_cookie_name='c305_historical_projection')
            from app.auth_service import provision_user
            from test_content_delivery_console_v1 import login as login_fresh
            with TestClient(build_app(historical)) as old_client:
                provision_user(historical.database_path,'13800000000')
                old_headers={'X-CSRF-Token':login_fresh(old_client)}
                assert task_count(historical)==0
                result=old_client.post(prefix+'/export-mix',headers=old_headers)
                assert result.status_code==200,result.text
                assert result.json()['task'] is None and result.json()['recovered']
                assert task_count(historical)==0
            # Deliberate corruption of a disposable fixture must not enqueue a
            # replacement export or masquerade as completed canonical history.
            excel_bytes=excel.read_bytes()
            try:
                excel.write_bytes(excel_bytes+b'\0')
                denied=client.post(prefix+'/export-mix',headers=headers)
                assert denied.status_code in {409,503},denied.text
                assert task_count(settings)==count
            finally:
                excel.write_bytes(excel_bytes)
            assert closure_path.read_bytes()==closure_bytes and ledger.read_bytes()==ledger_bytes
        finally:
            runner.close()


def test_real_task_crash_windows_resume_same_operation_without_model_replay(node):
    settings,business=native_node(node)
    project=Path(__file__).resolve().parents[2]
    root=settings.pipeline_root
    mode={'value':'generate-fail'}
    actual_run=subprocess.run
    env={k:v for k,v in os.environ.items() if not k.startswith(('DEEPSEEK_','QYAPI_','AIVO_'))}
    env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8')

    def boundary(command,*args,**kwargs):
        name=Path(command[1]).name if len(command)>1 else ''
        if name in {'resolve_generation_content_plan_v1.py','resolve_generation_batch_v1.py'}:
            rid=command[command.index('--request-id')+1]
            operation='plan' if name=='resolve_generation_content_plan_v1.py' else mode['value']
            extra=[command[command.index('--operation-id')+1],command[command.index('--intent-sha256')+1]] if '--operation-id' in command else []
            command=[command[0],str(project/'ops-pipeline/tests/compatibility_creation_synthetic.py'),operation,str(root),rid,*extra]
            kwargs['env']=env
        return actual_run(command,*args,**kwargs)

    with TestClient(build_app(settings)) as client,patch.object(subprocess,'run',boundary):
        headers=login(client)
        runner=BackgroundTaskRunner(settings)
        traces=[]
        try:
            for point in ['intent','dispatch','response','candidate','batch','pack','result','session']:
                mode['value']='generate-fail'
                from generation_request_handoff_v1 import request_id_for
                from privacy_projection_v1 import detect_sensitive_spans
                # Test-only opaque identities, never edited Request/Case IDs.
                # Keep a synthetic key from resembling a contact number, just
                # like this fixture's existing phone-safe UUID generator.
                key=next('c305_crash_'+point+'_'+str(n) for n in range(128)
                    if not detect_sensitive_spans(request_id_for(business['business_id'],'c305_crash_'+point+'_'+str(n))))
                response=client.post('/api/create/confirm',headers=headers,json={
                    'business_id':business['business_id'],'speaker_id':business['speaker_id'],'profile':'mix',
                    'requested_quantity':1,'confirmed_quantity':1,'idempotency_key':key})
                assert response.status_code==200,response.text
                rid=response.json()['result']['request_id']
                prefix='/api/create/'+rid
                assert client.post(prefix+'/resolve-sources',headers=headers).status_code==200

                def run(endpoint,body=None):
                    response=client.post(prefix+endpoint,headers=headers,json=body) if body else client.post(prefix+endpoint,headers=headers)
                    assert response.status_code==200,response.text
                    task=response.json()['task']
                    runner._run(task['task_id'])
                    return get_task(settings.database_path,task['task_id'])

                assert run('/resolve-content-plan')['status']=='completed'
                assert run('/generate-scripts')['status']=='failed'
                directory=root/'data/generation_batches'/rid
                anchor=(directory/'generation_batch_v1.json').read_bytes()
                op=uuid.uuid4().hex
                preview=client.post(prefix+'/generation-recovery/preview',headers=headers,json={'operation_id':op})
                assert preview.status_code==200,preview.text
                body={'operation_id':op,'preview_sha256':preview.json()['preview_sha256']}
                def close_disposable_draft():
                    # A REAL all-rejected Human review closes this experiment
                    # through the original lifecycle owner, with no Ledger.
                    # This permits another independent fault scenario without
                    # cloning or rewriting a Request or creating new Truth.
                    state=client.get(prefix+'/delivery').json()['state']
                    response=client.post(prefix+'/review',headers=headers,json={'items':[
                        {'content_id':item['content_id'],'decision':'rejected','note':'Discard this explicitly fictional fault-test draft'}
                        for item in state['generation']['contents']], 'note':'Native Human terminal rejection; no export or exposure'})
                    assert response.status_code==200,response.text
                    from generation_request_effective_lifecycle_v1 import request_is_effectively_in_flight
                    assert not request_is_effectively_in_flight(pipeline_root=root,
                        request_path=root/'data/generation_requests'/rid/'generation_request_v1.json')
                if point=='intent':
                    before=task_count(settings)
                    with patch('app.generation_recovery_gateway.create_background_task',side_effect=RuntimeError('Injected enqueue interruption')):
                        with pytest.raises(RuntimeError,match='enqueue interruption'):
                            client.post(prefix+'/generation-recovery/confirm',headers=headers,json=body)
                    assert task_count(settings)==before
                    assert (directory/'recovery'/op/'intent.json').is_file()
                    mode['value']='generate'
                    recovered=run('/generation-recovery/confirm',body)
                    assert recovered['status']=='completed',recovered
                    traces.append({'point':point,'request_id':rid,'task_id':recovered['task_id'],'status':'recovered'})
                    close_disposable_draft()
                    continue
                if point=='session':
                    queued=client.post(prefix+'/generation-recovery/confirm',headers=headers,json=body)
                    assert queued.status_code==200,queued.text
                    old_task=queued.json()['task']['task_id']
                    calls=root/'data/metrics/generation_requests'/rid/'synthetic_transport_calls.jsonl'
                    before_calls=calls.read_bytes()
                    client.post('/api/auth/logout',headers=headers)
                    headers=login(client)
                    mode['value']='generate'
                    runner._run(old_task)
                    assert get_task(settings.database_path,old_task)['status']=='failed'
                    assert calls.read_bytes()==before_calls
                    before_count=task_count(settings)
                    replay=client.post(prefix+'/generation-recovery/confirm',headers=headers,json=body)
                    assert replay.status_code==200,replay.text
                    assert replay.json()['task']['task_id']==old_task
                    assert task_count(settings)==before_count and calls.read_bytes()==before_calls
                    next_op=uuid.uuid4().hex
                    new_preview=client.post(prefix+'/generation-recovery/preview',headers=headers,json={'operation_id':next_op})
                    assert new_preview.status_code==200,new_preview.text
                    success=run('/generation-recovery/confirm',{'operation_id':next_op,'preview_sha256':new_preview.json()['preview_sha256']})
                    assert success['status']=='completed',success
                    assert get_task(settings.database_path,old_task)['status']=='failed'
                    traces.append({'point':'revoked_session_and_relogin','request_id':rid,'old_task':old_task,
                        'new_explicit_task':success['task_id'],'no_implicit_model_replay':True})
                    close_disposable_draft()
                    continue
                mode['value']='generate-crash-'+point
                interrupted=run('/generation-recovery/confirm',body)
                assert interrupted['status']=='failed',interrupted
                calls=root/'data/metrics/generation_requests'/rid/'synthetic_transport_calls.jsonl'
                calls_before=len(calls.read_text().splitlines())
                mode['value']='generate'
                before_tasks=task_count(settings)
                resumed=run('/generation-recovery/confirm',body)
                assert resumed['task_id']==interrupted['task_id']
                assert task_count(settings)==before_tasks
                assert len(calls.read_text().splitlines())==calls_before
                if point in {'dispatch','response'}:
                    assert resumed['status']=='failed'
                    state=client.get(prefix+'/delivery').json()['state']
                    assert state['generation']['recovery_state']=='outcome_unknown',state
                    assert state['generation']['ready_for_human_review'] is False
                    # A NEW explicit operation is necessary after an unknown outcome.
                    next_op=uuid.uuid4().hex
                    next_preview=client.post(prefix+'/generation-recovery/preview',headers=headers,json={'operation_id':next_op})
                    assert next_preview.status_code==200,next_preview.text
                    success=run('/generation-recovery/confirm',{'operation_id':next_op,'preview_sha256':next_preview.json()['preview_sha256']})
                    assert success['status']=='completed',success
                    assert len(calls.read_text().splitlines())==calls_before+1
                else:
                    assert resumed['status']=='completed',resumed
                assert (directory/'generation_batch_v1.json').read_bytes()==anchor
                traces.append({'point':point,'request_id':rid,'task_id':resumed['task_id'],
                    'same_task':True,'transport_calls_before_replay':calls_before,'no_replay_transport':True})
                close_disposable_draft()
            (root.parent/'c305-crash-traces.json').write_text(json.dumps(traces,indent=2),encoding='utf-8')
        finally:
            runner.close()


def test_formal_retry_rejects_source_drift_borrowed_preview_and_withdrawal(node):
    settings,business=native_node(node)
    project=Path(__file__).resolve().parents[2]
    root=settings.pipeline_root
    actual_run=subprocess.run
    env={k:v for k,v in os.environ.items() if not k.startswith(('DEEPSEEK_','QYAPI_','AIVO_'))}
    env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
    def boundary(command,*args,**kwargs):
        name=Path(command[1]).name if len(command)>1 else ''
        if name in {'resolve_generation_content_plan_v1.py','resolve_generation_batch_v1.py'}:
            rid=command[command.index('--request-id')+1]
            operation='plan' if name=='resolve_generation_content_plan_v1.py' else 'generate-fail'
            extra=[command[command.index('--operation-id')+1],command[command.index('--intent-sha256')+1]] if '--operation-id' in command else []
            command=[command[0],str(project/'ops-pipeline/tests/compatibility_creation_synthetic.py'),operation,str(root),rid,*extra]
            kwargs['env']=env
        return actual_run(command,*args,**kwargs)
    with TestClient(build_app(settings)) as client,patch.object(subprocess,'run',boundary):
        headers=login(client)
        response=client.post('/api/create/confirm',headers=headers,json={
            'business_id':business['business_id'],'speaker_id':business['speaker_id'],'profile':'mix',
            'requested_quantity':1,'confirmed_quantity':1,'idempotency_key':'c305_negative_sources'})
        assert response.status_code==200,response.text
        rid=response.json()['result']['request_id'];prefix='/api/create/'+rid
        assert client.post(prefix+'/resolve-sources',headers=headers).status_code==200
        runner=BackgroundTaskRunner(settings)
        try:
            for endpoint in ['/resolve-content-plan','/generate-scripts']:
                response=client.post(prefix+endpoint,headers=headers)
                runner._run(response.json()['task']['task_id'])
            from resolve_generation_batch_v1 import generation_inputs
            context=generation_inputs(root,rid)
            paths=[context['request_path'],context['source_plan_path'],context['final_plan_path']]
            paths += [Path(context['context']['paths'][name]) for name in ('persona','speaker_persona','pattern') if context['context']['paths'].get(name)]
            paths += list((root/'data/fingerprints').glob('*/case_fingerprint_v1.json'))
            paths += list((root/'data/cases').glob('*/case_v1.json'))
            outcomes=[]
            for path in paths:
                op=uuid.uuid4().hex
                preview=client.post(prefix+'/generation-recovery/preview',headers=headers,json={'operation_id':op})
                assert preview.status_code==200,preview.text
                body={'operation_id':op,'preview_sha256':preview.json()['preview_sha256']}
                old=path.read_bytes();count=task_count(settings)
                try:
                    # Deliberate byte corruption of THIS isolated fixture only.
                    # Never a successful approval or a production mutation.
                    path.write_bytes(old+b'\n ')
                    denied=client.post(prefix+'/generation-recovery/confirm',headers=headers,json=body)
                    assert denied.status_code in {409,503},(path,denied.text)
                    assert denied.json()['detail']['code'] in {'GENERATION_RECOVERY_SOURCE_CHANGED','PROFILE_COMPATIBILITY_BLOCKED'},denied.text
                    assert task_count(settings)==count
                    assert not (root/'data/generation_batches'/rid/'recovery'/op/'intent.json').exists()
                    outcomes.append({'source':str(path.relative_to(root)),'http':denied.status_code,'code':denied.json()['detail']['code']})
                finally:
                    path.write_bytes(old)
            # Exact saved preview cannot be borrowed by a different principal.
            memory_op=uuid.uuid4().hex
            memory_preview=client.post(prefix+'/generation-recovery/preview',headers=headers,json={'operation_id':memory_op})
            assert memory_preview.status_code==200,memory_preview.text
            ledger=root/'data/content_ledgers'/business['business_id']/'content_ledger_v1.json'
            assert not ledger.exists()
            from close_generation_export_v1 import _empty_ledger
            ledger.parent.mkdir(parents=True,exist_ok=True)
            # Negative fixture input: no approved content or exposure is added.
            ledger.write_text(json.dumps(_empty_ledger(business_id=business['business_id'],created_at='2026-10-19T00:00:00Z')),encoding='utf-8')
            try:
                memory_denied=client.post(prefix+'/generation-recovery/confirm',headers=headers,json={
                    'operation_id':memory_op,'preview_sha256':memory_preview.json()['preview_sha256']})
                assert memory_denied.status_code in {409,503},memory_denied.text
            finally:
                ledger.unlink()
            op=uuid.uuid4().hex
            preview=client.post(prefix+'/generation-recovery/preview',headers=headers,json={'operation_id':op})
            assert preview.status_code==200,preview.text
            body={'operation_id':op,'preview_sha256':preview.json()['preview_sha256']}
            other,other_headers,_=node[1]['B']
            assert other.post(prefix+'/generation-recovery/confirm',headers=other_headers,json=body).status_code==409
            assert client.post(prefix+'/generation-recovery/confirm',headers=headers,json={**body,'preview_sha256':'0'*64}).status_code==409
            confirmed=client.post(prefix+'/generation-recovery/confirm',headers=headers,json=body)
            assert confirmed.status_code==200,confirmed.text
            pending_id=confirmed.json()['task']['task_id']
            # Formal independent Human withdrawal, no hand-written approval flags.
            from profile_compatibility_decisions_v1_1 import decision_graph,read
            from test_profile_compatibility_v1_1 import request as decision_request
            graph=decision_graph(root)
            first=next(p for p in (root/'data/production_profiles/compatibility_v1_1/decisions').glob('*.json'))
            target=read(first)['decisions'][0]['target']
            reviewer,review_headers,_=node[1]['C']
            withdrawal_op=uuid.uuid4().hex
            preview=reviewer.post('/api/profile-compatibility/preview',headers=review_headers,json={
                'operation_id':withdrawal_op,'decisions':[decision_request(target,graph,'withdraw')]})
            assert preview.status_code==200,preview.text
            withdrawal=reviewer.post('/api/profile-compatibility/confirm',headers=review_headers,json={
                'operation_id':withdrawal_op,'preview_sha256':preview.json()['preview_ref']['sha256']})
            assert withdrawal.status_code==200,withdrawal.text
            calls=root/'data/metrics/generation_requests'/rid/'synthetic_transport_calls.jsonl'
            before_calls=calls.read_bytes()
            runner._run(pending_id)
            assert get_task(settings.database_path,pending_id)['status']=='failed'
            assert calls.read_bytes()==before_calls
            assert not (root/'data/generation_batches'/rid/'recovery'/op/'generation_batch_v1.json').exists()
            (root.parent/'c305-source-negative-traces.json').write_text(json.dumps(outcomes,indent=2),encoding='utf-8')
        finally:
            runner.close()
