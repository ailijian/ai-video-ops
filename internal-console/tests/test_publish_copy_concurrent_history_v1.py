"""One Business: Native Presentation append races supplemental publication."""
import json
from dataclasses import replace
from pathlib import Path
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from test_news_novel_runtime_v1_2 import native_news_runtime
from test_publish_copy_native_v1 import install_templates
from publish_copy_native_support import mix_flow,repurpose_reviewed,post,current,generation,confirm,worker
from test_generation_export_anchor_v1 import validate_anchor
from profile_compatibility_decisions_v1_1 import read,file_sha
from app.main import build_app
from app.task_service import get_task

def test_concurrent_native_presentation_and_supplement_keep_one_exact_history(node):
    runtime,b,_,_,_=native_news_runtime(node,mixed=True)
    runtime=replace(runtime,publish_copy_enabled=True);root=runtime.pipeline_root;install_templates(root)
    with TestClient(build_app(runtime)) as client:
        login=client.post('/api/auth/login',json={'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login.json()['csrf_token']}
        rid=mix_flow(client,headers,runtime,b,'concurrent_pc_history')
        directory=root/'data/generation_batches'/rid
        protected={str(p):file_sha(p) for p in directory.glob('*.json')}
        initial=validate_anchor(root,rid)
        tid=generation(client,headers,rid)['task']['task_id'];assert worker(runtime,tid).returncode==0
        assert get_task(runtime.database_path,tid)['status']=='completed';confirm(client,headers,rid)
        nrid=repurpose_reviewed(client,headers,runtime,b,'concurrent_native_presentation')
        operations=[('/api/create/'+rid+'/publish-copy/export',None),('/api/create/news/'+nrid+'/export',None)]
        operations=[(url,post(client,url,headers)['task']['task_id']) for url,_ in operations]
        processes=[worker(runtime,tid,wait=False) for _,tid in operations]
        for process in processes:
            stdout,stderr=process.communicate(timeout=90);assert process.returncode==0,(stdout,stderr)
        observed=[]
        for url,tid in operations:
            before=get_task(runtime.database_path,tid)
            if before['status']!='completed':
                assert before['status']=='failed',before
                resumed=post(client,url,headers);assert resumed['task']['task_id']==tid,resumed
                if resumed['accepted']:
                    result=worker(runtime,tid);assert result.returncode==0,(result.stdout,result.stderr)
            observed.append({'endpoint':url,'task_id':tid,'initial_status':before['status'],
                             'final_status':get_task(runtime.database_path,tid)['status']})
        assert all(get_task(runtime.database_path,tid)['status']=='completed' for _,tid in operations)
        proof=validate_anchor(root,rid);assert proof['anchor_ref']==initial['anchor_ref']
        ledger=read(root/proof['ledger_ref']['path'])
        assert len(ledger['entries'])==1
        assert len(ledger['extensions']['presentation_history_v1']['entries'])==1
        assert current(client,rid)['delivery']['state']=='completed'
        for url,tid in operations:
            replay=post(client,url,headers);assert replay['accepted'] is False and replay['task']['task_id']==tid
        assert all(file_sha(Path(p))==sha for p,sha in protected.items())
        (root/'concurrent_history_acceptance.json').write_text(json.dumps({'mix_request':rid,'news_request':nrid,
            'operations':observed,'anchor':proof,'semantic_count':1,'presentation_count':1,
            'original_sha_unchanged':True},ensure_ascii=False,indent=2),encoding='utf-8')
