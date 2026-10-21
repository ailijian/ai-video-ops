"""HTTP and Native fences on an actual isolated approved News production."""
import copy,json,uuid
from pathlib import Path
from dataclasses import replace
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from test_news_novel_runtime_v1_2 import native_news_runtime
from test_news_qualification_complete_v1_2 import novel_flow
from test_publish_copy_native_v1 import install_templates
from publish_copy_native_support import post,current,generation,confirm,worker,calls
from profile_compatibility_decisions_v1_1 import read,file_sha,preview,decide,decision_graph,target_id
from profile_compatibility_release_v1_1 import effective_runtime
from app.main import build_app
from app.database import connect
from app.task_service import get_task

def test_http_confirm_relogin_cross_source_and_current_authority_fences(node):
    runtime,b,news,repo,owner=native_news_runtime(node)
    runtime=replace(runtime,publish_copy_enabled=True);root=runtime.pipeline_root;install_templates(root)
    with TestClient(build_app(runtime)) as client:
        logged=client.post('/api/auth/login',json={'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':logged.json()['csrf_token']}
        rid,_=novel_flow(client,headers,runtime,b);url='/api/create/'+rid+'/publish-copy'
        tid=generation(client,headers,rid)['task']['task_id'];assert worker(runtime,tid).returncode==0
        assert get_task(runtime.database_path,tid)['status']=='completed'
        state=current(client,rid);draft=state['draft'];before_calls=len(calls(root,rid))
        for body in [{'path':'C:/foreign.xlsx'},{'force':True},{'skip_stage':True},{'approved':True}]:
            response=client.post(url+'/generate',headers=headers,json=body);assert response.status_code==422
        assert client.post(url+'/export',headers=headers).status_code==409  # AI draft is not Human confirmation
        for mutation in ['foreign_target','foreign_sha','changed_price','lost_condition','invented_topic','unknown_metadata']:
            changed=copy.deepcopy(draft['payload']);item=changed['items'][0]
            if mutation=='foreign_target':item['target_id']='gen_other-N001'
            elif mutation=='foreign_sha':item['source_version_sha256']='f'*64
            elif mutation=='changed_price':item['production_headlines'][0]['text']=item['production_headlines'][0]['text'].replace('29','19')
            elif mutation=='lost_condition':item['production_headlines'][0]['text']='午餐套餐29元'
            elif mutation=='invented_topic':item['topics']=['全国冠军']
            else:item['approved']=True
            response=client.post(url+'/edit',headers=headers,json={'draft_ref':draft['ref'],'payload':changed})
            assert response.status_code==409,response.text
            assert current(client,rid)['draft']['ref']==draft['ref']
        # Re-login restores a saved draft, never implicitly confirms or resends.
        assert client.post('/api/auth/logout',headers=headers).status_code==200
        assert client.get(url).status_code==401
        logged=client.post('/api/auth/login',json={'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':logged.json()['csrf_token']}
        assert current(client,rid)['draft']['ref']==draft['ref']
        assert len(calls(root,rid))==before_calls
        confirmation=confirm(client,headers,rid)
        with TestClient(build_app(runtime)) as other:
            logged=other.post('/api/auth/login',json={'phone':'13900000002','password':'SyntheticCase2026!'})
            denied=other.post(url+'/confirm',headers={'X-CSRF-Token':logged.json()['csrf_token']},json={'draft_ref':draft['ref']})
            assert denied.status_code!=200  # another principal cannot adopt the original decision
        etid=post(client,url+'/export',headers)['task']['task_id'];assert worker(runtime,etid).returncode==0
        assert get_task(runtime.database_path,etid)['status']=='completed'
        delivery=current(client,rid)['delivery'];native=root/'data/generation_batches'/rid
        protected={str(p):file_sha(p) for p in native.rglob('*') if p.is_file()}
        ledger=root/'data/content_ledgers'/b['business_id']/'content_ledger_v1.json';ledger_sha=file_sha(ledger)
        with connect(runtime.database_path) as db:count=db.execute('SELECT count(*) FROM tasks').fetchone()[0]
        for _ in range(2):
            replay=post(client,url+'/export',headers);assert replay['accepted'] is False and replay['task']['task_id']==etid
            assert client.get(url+'/excel/'+delivery['delivery_id']).status_code==200
        with connect(runtime.database_path) as db:assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==count
        # Use the real independent Compatibility reviewer and decision chain.
        target=news['targets'][0];key=target_id(target);parent_release=effective_runtime(root)['binding']['release_ref']
        def decision(action):
            head=decision_graph(root)['heads'][key];operation=uuid.uuid4().hex
            proposed=preview(root,runtime.database_path,news['actor'],operation,[{'target_id':key,'target':target,
                'action':action,'parent':head['head'],'withdraws':head['effective'] if action=='withdraw' else None,
                'reason':'全虚构发布文案当前权限回归'}])
            decide(root,runtime.database_path,news['actor'],operation,proposed['preview_ref']['sha256'])
        observed=[]
        for phase in ['withdrawn','reapproved_not_activated','new_activation_old_request']:
            if phase=='withdrawn':decision('withdraw')
            elif phase=='reapproved_not_activated':decision('approve')
            else:
                package=owner.build_release(root,root.parent.parent/'pc-fence-release',repo,contract_version='1.2',
                    purpose='isolated-validation',parent_release=parent_release)
                staged=owner.stage_release_v1_1(package,root,repo);owner.activate_release_v1_1(root,repo,staged,uuid.uuid4().hex)
            for action,body in [('generate',{}),('edit',{'draft_ref':draft['ref'],'payload':draft['payload']}),
                                ('confirm',{'draft_ref':draft['ref']}),('export',None)]:
                denied=client.post(url+'/'+action,headers=headers,**({'json':body} if body is not None else {}))
                assert denied.status_code!=200,(phase,action,denied.text)
                observed.append({'phase':phase,'action':action,'status':denied.status_code})
            assert all(file_sha(Path(p))==sha for p,sha in protected.items())
            assert file_sha(ledger)==ledger_sha and len(calls(root,rid))==before_calls
        (root/'publish_copy_http_fences.json').write_text(json.dumps({'request_id':rid,'confirmation':confirmation,
            'delivery':delivery,'fences':observed,'no_new_tasks_on_completed_replay':True,
            'historical_artifacts_unchanged':True},ensure_ascii=False,indent=2),encoding='utf-8')
