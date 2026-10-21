"""Ready requires the complete immutable response/result/draft identity chain."""
import json,os,subprocess
from pathlib import Path
from dataclasses import replace
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from test_news_novel_runtime_v1_2 import native_news_runtime
from test_news_qualification_complete_v1_2 import novel_flow
from test_publish_copy_native_v1 import install_templates
from publish_copy_native_support import generation,worker,current
from test_generation_export_anchor_v1 import hostile_copy
from profile_compatibility_decisions_v1_1 import read,ref,file_sha
from app.main import build_app
from app.task_service import get_task

def native_state(runtime,root,rid):
    result=subprocess.run([runtime.pipeline_python_executable,str(root/'scripts/publish_copy_v1.py'),'state',
        '--pipeline-root',str(root),'--request-id',rid],capture_output=True,text=True,encoding='utf-8',
        env={**os.environ,'PYTHONIOENCODING':'utf-8'},timeout=60)
    return result.returncode,json.loads(result.stdout.splitlines()[-1])

def test_native_readiness_refuses_forged_or_missing_generation_evidence(node):
    runtime,b,_,_,_=native_news_runtime(node);runtime=replace(runtime,publish_copy_enabled=True)
    root=runtime.pipeline_root;install_templates(root);observed=[]
    with TestClient(build_app(runtime)) as client:
        logged=client.post('/api/auth/login',json={'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':logged.json()['csrf_token']};rid,_=novel_flow(client,headers,runtime,b)
        tid=generation(client,headers,rid)['task']['task_id'];assert worker(runtime,tid).returncode==0
        assert get_task(runtime.database_path,tid)['status']=='completed'
        state=current(client,rid);intent_ref=state['attempt_ref'];directory=root/intent_ref['path']
        protected={str(p.relative_to(root)):file_sha(p) for p in (root/'data').rglob('*') if p.is_file()}
        for number,attack in enumerate(['result_response_sha','result_draft_sha','result_operation','missing_response',
            'changed_response','forged_response_ref','foreign_draft_request','changed_draft_payload','safe_projection_injection']):
            with hostile_copy(root,number+200) as clone:
                assert native_state(runtime,clone,rid)[0]==0
                base=clone/intent_ref['path'];rp=base.with_name('result.json');result=read(rp)
                response=base.with_name('response.json');draft=clone/result['draft_ref']['path']
                if attack=='result_response_sha':result['response_ref']['sha256']='f'*64
                elif attack=='result_draft_sha':result['draft_ref']['sha256']='f'*64
                elif attack=='result_operation':result['operation_id']='f'*32
                elif attack=='missing_response':response.rename(response.with_suffix('.retained'))
                elif attack in {'changed_response','forged_response_ref'}:
                    value=read(response);value['payload']['items'][0]['publish_title']='虚构额外奖项'
                    response.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
                    if attack=='forged_response_ref':result['response_ref']=ref(clone,response)
                else:
                    value=read(draft)
                    if attack=='foreign_draft_request':value['request_id']='gen_foreign'
                    elif attack=='changed_draft_payload':value['payload']['items'][0]['publish_title']='虚构额外奖项'
                    else:
                        snapshot=clone/value['source_snapshot_ref']['path'];source=read(snapshot)
                        safe=clone/source['safe_projection_ref']['path'];data=read(safe);data['safe_business']['raw_private_input']='not allowed'
                        safe.write_text(json.dumps(data),encoding='utf-8');source['safe_projection_ref']=ref(clone,safe)
                        snapshot.write_text(json.dumps(source),encoding='utf-8');value['source_snapshot_ref']=ref(clone,snapshot)
                    draft.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8');result['draft_ref']=ref(clone,draft)
                rp.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
                code,denied=native_state(runtime,clone,rid)
                assert code!=0 and denied['ok'] is False,(attack,denied)
                observed.append({'attack':attack,'code':denied['code']})
        assert all(file_sha(root/name)==sha for name,sha in protected.items())
        assert native_state(runtime,root,rid)[0]==0
        (root/'publish_copy_integrity_evidence.json').write_text(json.dumps({'request_id':rid,'negatives':observed,
            'positive_control':True,'original_sha_unchanged':True},ensure_ascii=False,indent=2),encoding='utf-8')
