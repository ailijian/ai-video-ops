"""PC-R/E: real process deaths, durable Native evidence and real Task leases."""
import copy
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
import json
import time
from dataclasses import replace
from pathlib import Path
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from test_news_novel_runtime_v1_2 import native_news_runtime
from test_news_qualification_complete_v1_2 import novel_flow
from test_publish_copy_native_v1 import install_templates
from publish_copy_native_support import post,current,generation,confirm,worker,calls
from profile_compatibility_decisions_v1_1 import read,file_sha
from app.main import build_app
from app.task_service import get_task,recover_expired_tasks
from app.background_task_service import BackgroundTaskRunner

def reconcile(runtime,tid):
    time.sleep(2.2)
    runner=BackgroundTaskRunner(runtime)
    try:recover_expired_tasks(runtime.database_path,task_types=('content_generation','excel_export'),
                              reconciler=runner._reconcile_business_state)
    finally:runner.close()
    return get_task(runtime.database_path,tid)

def success(runtime,tid):
    result=worker(runtime,tid)
    assert result.returncode==0,(result.stdout,result.stderr)
    assert get_task(runtime.database_path,tid)['status']=='completed',get_task(runtime.database_path,tid)

def test_process_generation_and_supplemental_publication_windows(node):
    runtime,business,_,_,_=native_news_runtime(node)
    runtime=replace(runtime,publish_copy_enabled=True,task_lease_seconds=2,task_heartbeat_seconds=1)
    root=runtime.pipeline_root;install_templates(root);observed=[]
    with TestClient(build_app(runtime)) as client:
        login=client.post('/api/auth/login',json={'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login.json()['csrf_token']}
        rid,_=novel_flow(client,headers,runtime,business)
        directory=root/'data/generation_batches'/rid
        protected={str(p):file_sha(p) for p in directory.glob('*.json')}
        ledger=root/'data/content_ledgers'/business['business_id']/'content_ledger_v1.json';ledger_sha=file_sha(ledger)
        windows=['dispatch_before_send','sent_without_response','response_before_save',
                 'prepared_before_draft','draft_before_result','result_before_task']
        for index,window in enumerate(windows):
            operation=generation(client,headers,rid,retry=index>0)
            tid=operation['task']['task_id'];before=len(calls(root,rid))
            replay=generation(client,headers,rid)
            assert replay['task']['task_id']==tid
            stopped=worker(runtime,tid,window)
            assert stopped.returncode==92,(window,stopped.stdout,stopped.stderr)
            after=len(calls(root,rid))
            assert after-before==(0 if window=='dispatch_before_send' else 1)
            task=reconcile(runtime,tid)
            if window in windows[:3]:
                assert task['status']=='failed',task
                assert current(client,rid)['state']=='dispatched_outcome_unknown'
                refused=client.post('/api/create/'+rid+'/publish-copy/generate',headers=headers,json={})
                assert refused.status_code==409,refused.text
            elif task['status']!='completed':
                assert task['status']=='queued',task
                success(runtime,tid)
            assert len(calls(root,rid))==after  # refresh/lease/local replay never resends
            observed.append({'window':window,'calls_before':before,'calls_after':after,
                             'task_id':tid,'task_status':get_task(runtime.database_path,tid)['status']})
        assert current(client,rid)['state']=='draft_ready'
        assert client.post('/api/create/'+rid+'/publish-copy/confirm',json={'draft_ref':current(client,rid)['draft']['ref']}).status_code==403
        # Each independent export has a real new Human-confirmed expression,
        # and all versions continue to bind the same unchanged production.
        export_windows=['intent_before_stage','stage_before_prepared','prepared_before_output',
                        'output_before_receipt','receipt_before_completion','completion_before_selection',
                        'selection_before_response']
        deliveries=[]
        for index,window in enumerate(export_windows):
            state=current(client,rid);payload=copy.deepcopy(state['draft']['payload'])
            units=state['production'][0]['units'];payload['items'][0]['publish_title']=units[index%len(units)]['text']
            payload['items'][0]['publish_body']=('\n' if index<len(units) else '；').join(u['text'] for u in units)
            post(client,'/api/create/'+rid+'/publish-copy/edit',headers,{'draft_ref':state['draft']['ref'],'payload':payload})
            confirm(client,headers,rid)
            task=post(client,'/api/create/'+rid+'/publish-copy/export',headers)['task'];tid=task['task_id']
            assert tid not in [v['task_id'] for v in deliveries]
            stopped=worker(runtime,tid,window)
            assert stopped.returncode==92,(window,stopped.stdout,stopped.stderr)
            retained={str(p):file_sha(p) for p in (directory/'deliveries').rglob('*') if p.is_file()}
            task=reconcile(runtime,tid)
            if task['status']!='completed':
                assert task['status']=='queued',task
                success(runtime,tid)
            assert all(file_sha(Path(p))==sha for p,sha in retained.items())
            selected=current(client,rid)['delivery'];assert selected['state']=='completed'
            output=Path(selected['output_path']);sha=file_sha(output)
            for _ in range(2):
                replay=post(client,'/api/create/'+rid+'/publish-copy/export',headers)
                assert replay['accepted'] is False and replay['task']['task_id']==tid
                response=client.get('/api/create/'+rid+'/publish-copy/excel/'+selected['delivery_id'])
                assert response.status_code==200 and response.content==output.read_bytes()
            deliveries.append({'window':window,'task_id':tid,'delivery':selected,'output_sha256':sha})
        assert len({v['delivery']['delivery_id'] for v in deliveries})==len(export_windows)
        for version in deliveries:
            response=client.get('/api/create/'+rid+'/publish-copy/excel/'+version['delivery']['delivery_id'])
            assert response.status_code==200  # explicit immutable historical download
        assert len(calls(root,rid))==len(windows)-1
        # Expired old worker still lives. Only the new explicit operation can
        # publish; the old response is retained without changing its new head.
        admitted=generation(client,headers,rid,retry=True);old_tid=admitted['task']['task_id']
        before=len(calls(root,rid));late=worker(runtime,old_tid,'late_response',wait=False)
        try:
            deadline=time.monotonic()+30
            while len(calls(root,rid))==before and time.monotonic()<deadline:time.sleep(.1)
            assert len(calls(root,rid))==before+1 and late.poll() is None
            assert reconcile(runtime,old_tid)['status']=='failed'
            parent=current(client,rid)['attempt_ref']
            body={'expected_parent':parent,'retry_confirmation':'explicit_retry_possible_additional_cost'}
            def retry():return client.post('/api/create/'+rid+'/publish-copy/generate',headers=headers,json=body)
            with ThreadPoolExecutor(2) as threads:responses=list(threads.map(lambda _:retry(),range(2)))
            assert all(r.status_code==200 for r in responses),[r.text for r in responses]
            assert responses[0].json()['task']['task_id']==responses[1].json()['task']['task_id']
            new_tid=responses[0].json()['task']['task_id'];success(runtime,new_tid)
            new_draft=current(client,rid)['draft']['ref']
            (root/'data/metrics'/rid/'allow_publish_late_response').write_text('release',encoding='utf-8')
            stdout,stderr=late.communicate(timeout=20);assert late.returncode==0,(stdout,stderr)
            assert current(client,rid)['draft']['ref']==new_draft
            assert len(calls(root,rid))==before+2
            assert get_task(runtime.database_path,old_tid)['status']=='failed'
            observed.append({'window':'late_worker_concurrent_explicit_retry','old_task':old_tid,'new_task':new_tid,
                             'calls_before':before,'calls_after':len(calls(root,rid)),'new_head_unchanged':True})
        finally:
            if late.poll() is None:
                (root/'data/metrics'/rid/'allow_publish_late_response').write_text('release',encoding='utf-8')
                late.communicate(timeout=20)
        # Admission exits cannot imply a model dispatch. Reuse the same real
        # authorization context; only the external/crash boundary is replaced.
        execution=get_task(runtime.database_path,new_tid)['payload']['publish_copy']
        project=Path(__file__).resolve().parents[2]
        for mode in ['before_intent','after_intent']:
            parent=current(client,rid)['attempt_ref'];before=len(calls(root,rid))
            stopped=subprocess.run([runtime.pipeline_python_executable,str(project/'internal-console/tests/publish_copy_process_boundary.py'),
                str(project),str(root),rid,'prepare',mode],input=json.dumps({'authorization_context':execution['authorization_context'],'expected_parent':parent}),
                capture_output=True,text=True,encoding='utf-8',env={**os.environ,'PYTHONIOENCODING':'utf-8'},timeout=30)
            assert stopped.returncode==91,(stopped.stdout,stopped.stderr)
            assert len(calls(root,rid))==before
            if mode=='before_intent':assert current(client,rid)['attempt_ref']==parent
            else:assert current(client,rid)['state']=='not_dispatched'
            admitted=generation(client,headers,rid,retry=mode=='before_intent')
            success(runtime,admitted['task']['task_id']);assert len(calls(root,rid))==before+1
            observed.append({'window':mode,'calls_before':before,'calls_after':len(calls(root,rid))})
        assert file_sha(ledger)==ledger_sha and all(file_sha(Path(p))==v for p,v in protected.items())
        (root/'publish_copy_process_evidence.json').write_text(json.dumps({'request_id':rid,'generation':observed,
            'exports':deliveries,'ledger_unchanged':True,'native_core_unchanged':True},ensure_ascii=False,indent=2),encoding='utf-8')
