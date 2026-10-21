"""A4: exact snapshots/events/core closure retained across real Native exits."""
import json,subprocess
from pathlib import Path
from unittest.mock import patch
from dataclasses import replace
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from test_news_novel_runtime_v1_2 import native_news_runtime
from news_golden_support_v1_2 import prepare_news_business
from test_publish_copy_native_v1 import install_templates
from publish_copy_native_support import mix_reviewed,post,current,generation,confirm,worker,repurpose_existing
from test_generation_export_anchor_v1 import validate_anchor
from profile_compatibility_decisions_v1_1 import read,file_sha
from app.main import build_app
from app.task_service import get_task
from app.background_task_service import BackgroundTaskRunner

def test_mix_anchor_snapshot_transition_and_closure_crash_recovery(node):
    runtime,_,_,_,_=native_news_runtime(node,mixed=True)
    runtime=replace(runtime,publish_copy_enabled=True);root=runtime.pipeline_root;install_templates(root)
    project=Path(__file__).resolve().parents[2];evidence=[]
    with TestClient(build_app(runtime)) as client:
        login=client.post('/api/auth/login',json={'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login.json()['csrf_token']}
        for window in ['snapshot_saved','transition_prepared','ledger_published','closure_saved','event_sealed','anchor_saved']:
            b=prepare_news_business(node,customer_name='历史锚点中断·'+window+'（全虚构）')
            rid=mix_reviewed(client,headers,runtime,b,'anchor_crash_'+window)
            tid=post(client,'/api/create/'+rid+'/export-mix',headers)['task']['task_id']
            original=subprocess.run;observed=[]
            def fault(command,*args,**kwargs):
                if len(command)>1 and Path(command[1]).name=='close_generation_export_v1.py':
                    auth=read(Path(command[command.index('--authorization-file')+1]))
                    command=[command[0],str(project/'internal-console/tests/ledger_history_process_boundary.py'),str(root),rid,'mix',window]
                    kwargs['input']=json.dumps({'authorization_context':auth})
                    result=original(command,*args,**kwargs);observed.append(result.returncode);return result
                return original(command,*args,**kwargs)
            with patch.object(subprocess,'run',fault):
                runner=BackgroundTaskRunner(runtime)
                try:runner._run(tid)
                finally:runner.close()
            assert observed==[91],(window,observed,get_task(runtime.database_path,tid))
            assert get_task(runtime.database_path,tid)['status']=='failed'
            directory=root/'data/generation_batches'/rid
            retained={str(p):file_sha(p) for p in directory.rglob('*') if p.is_file()}
            history=root/'data/content_ledgers'/b['business_id']/'history_v1'
            retained.update({str(p):file_sha(p) for p in history.rglob('*') if p.is_file()})
            # New supplemental delivery calls the original Native core owner
            # once as needed, then its explicit history verifier. No new Request.
            generated=generation(client,headers,rid);result=worker(runtime,generated['task']['task_id'])
            assert result.returncode==0,(result.stdout,result.stderr)
            assert get_task(runtime.database_path,generated['task']['task_id'])['status']=='completed'
            confirm(client,headers,rid)
            exported=post(client,'/api/create/'+rid+'/publish-copy/export',headers)
            result=worker(runtime,exported['task']['task_id']);assert result.returncode==0,(result.stdout,result.stderr)
            assert get_task(runtime.database_path,exported['task']['task_id'])['status']=='completed',get_task(runtime.database_path,exported['task']['task_id'])
            assert all(file_sha(Path(p))==sha for p,sha in retained.items())
            proof=validate_anchor(root,rid);before=proof['anchor_ref']
            nrid=repurpose_existing(client,headers,runtime,b,'anchor_crash_repurpose_'+window)
            assert validate_anchor(root,rid)['anchor_ref']==before
            assert len(read(root/proof['ledger_ref']['path'])['entries'])==1
            assert post(client,'/api/create/'+rid+'/publish-copy/export',headers)['accepted'] is False
            evidence.append({'window':window,'mix_request':rid,'repurpose_request':nrid,'anchor':proof,
                'retained_file_count':len(retained),'retained_sha_unchanged':True,'delivery':current(client,rid)['delivery']})
        (root/'anchor_crash_evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
