"""Independent per-target retry over two genuinely Native approved contents."""
import copy,json
from dataclasses import replace
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from test_news_novel_runtime_v1_2 import native_news_runtime
from test_review_flow_closure_v1 import amend,finish_speaker_review
from test_customer_speaker_revision_v1 import review_current
from review_protocol import post_review
from test_publish_copy_native_v1 import install_templates
from publish_copy_native_support import mix_reviewed,post,current,generation,confirm,worker,calls
from profile_compatibility_decisions_v1_1 import read,file_sha
from app.main import build_app
from app.task_service import get_task

def test_real_mix_independent_target_retry_preserves_other_confirmed_source(node):
    runtime,b,_,_,_=native_news_runtime(node,mixed=True)
    runtime=replace(runtime,publish_copy_enabled=True);root=runtime.pipeline_root;install_templates(root)
    with TestClient(build_app(runtime)) as client:
        login=client.post('/api/auth/login',json={'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login.json()['csrf_token']};csrf=headers['X-CSRF-Token'];bid=b['business_id'];sid=b['speaker_id']
        processes=['先核对忌口，再按单配菜，制作后标记餐盒','顾客到店后先核对订单标识，再核对餐盒标记，最后交付密封餐盒']
        amend(client,bid,csrf,field='process_facts',value=processes);review_current(client,bid,csrf)
        response=post_review(client,'/api/customers/'+bid+'/persona/approve',headers=headers,json={'note':'全虚构下单与领取两种流程，分别人工核对'})
        assert response.status_code==200,response.text
        amend(client,bid,csrf,sid=sid,action='rebase');finish_speaker_review(client,bid,sid,csrf)
        response=post_review(client,'/api/customers/'+bid+'/speakers/'+sid+'/persona/approve',headers=headers,json={'note':'独立核对最新客户来源'})
        assert response.status_code==200,response.text
        rid=mix_reviewed(client,headers,runtime,b,'pc_two_native_target',quantity=2,many=True)
        directory=root/'data/generation_batches'/rid;approved=read(directory/'approved_generation_batch_v1.json')
        assert len(approved['contents'])==2
        protected={str(p):file_sha(p) for p in directory.glob('*.json')}
        targets=[v['content_id'] for v in approved['contents']]
        generated=generation(client,headers,rid,targets=[targets[0]]);assert worker(runtime,generated['task']['task_id']).returncode==0
        assert get_task(runtime.database_path,generated['task']['task_id'])['status']=='completed'
        partial=current(client,rid);payload=copy.deepcopy(partial['draft']['payload'])
        payload['items'][0]['publish_title']='本期介绍'+payload['items'][0]['publish_title']
        post(client,'/api/create/'+rid+'/publish-copy/edit',headers,{'draft_ref':partial['draft']['ref'],'payload':payload})
        assert client.post('/api/create/'+rid+'/publish-copy/confirm',headers=headers,
            json={'draft_ref':current(client,rid)['draft']['ref']}).status_code==409
        remaining=generation(client,headers,rid,retry=True,targets=[targets[1]])
        assert worker(runtime,remaining['task']['task_id']).returncode==0
        assert get_task(runtime.database_path,remaining['task']['task_id'])['status']=='completed'
        first=current(client,rid)['draft'];other=copy.deepcopy(first['payload']['items'][0])
        confirm(client,headers,rid)
        retried=generation(client,headers,rid,retry=True,targets=[targets[1]])
        replay=client.post('/api/create/'+rid+'/publish-copy/generate',headers=headers,json={
            'expected_parent':current(client,rid)['attempt_ref'],'retry_confirmation':'explicit_retry_possible_additional_cost',
            'target_ids':['gen_foreign-C001']})
        assert replay.status_code==409
        assert worker(runtime,retried['task']['task_id']).returncode==0
        assert get_task(runtime.database_path,retried['task']['task_id'])['status']=='completed'
        second=current(client,rid);assert len(second['draft']['payload']['items'])==2
        assert second['draft']['payload']['items'][0]==other
        assert second['confirmed'] is False
        assert len(calls(root,rid))==3 and len({v['operation_id'] for v in calls(root,rid)})==3
        confirm(client,headers,rid)
        etid=post(client,'/api/create/'+rid+'/publish-copy/export',headers)['task']['task_id']
        assert worker(runtime,etid).returncode==0
        assert get_task(runtime.database_path,etid)['status']=='completed',get_task(runtime.database_path,etid)
        assert len(read(root/'data/content_ledgers'/bid/'content_ledger_v1.json')['entries'])==2
        assert all(file_sha(__import__('pathlib').Path(p))==sha for p,sha in protected.items())
        (root/'selected_target_evidence.json').write_text(json.dumps({'request_id':rid,'targets':targets,
            'first_draft_ref':first['ref'],'second_draft_ref':second['draft']['ref'],'unchanged_target':targets[0],
            'call_count':3,'delivery':current(client,rid)['delivery']},ensure_ascii=False,indent=2),encoding='utf-8')
