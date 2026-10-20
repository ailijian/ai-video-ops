"""Additional real v1.2 open-export fences; all sources and accounts fictional."""
import json,subprocess,sys,uuid
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from test_news_novel_runtime_v1_2 import native_news_runtime
from test_news_qualification_complete_v1_2 import novel_flow,repurpose_flow
from news_golden_support_v1_2 import prepare_news_business
from app.main import build_app
from app.database import connect
from app.task_service import get_task
from profile_compatibility_decisions_v1_1 import read,preview,decide,decision_graph,target_id
from profile_compatibility_release_v1_1 import effective_runtime
from profile_compatibility_contract_v1_1 import CompatibilityError

PROJECT=Path(__file__).resolve().parents[2]

def test_real_news_both_partial_exports_withdraw_reapprove_and_activation_fence(node):
    runtime,business,news,repo,owner=native_news_runtime(node,mixed=True)
    root=runtime.pipeline_root
    proofs=[]
    # Native Pattern permission is independent of Case and Mix grants.
    from news_pattern_authority_v1_1 import approve_pattern
    denied_actor=dict(news['actor']);denied_actor['user_id']=1
    with pytest.raises(CompatibilityError):
        approve_pattern(root,runtime.database_path,denied_actor,uuid.uuid4().hex,news['candidate_ref'],
            **{k:news[k] for k in ('profile_ref','rules_ref')})
    target=news['targets'][0];key=target_id(target)
    decisions=[{'target_id':key,'target':target,'action':'approve','parent':None,'withdraws':None,'reason':'Unauthorized Native CLI probe'}]
    proposal=root/'metrics-news-permission-probe.json';proposal.write_text(json.dumps(decisions),'utf-8')
    denied=subprocess.run([sys.executable,str(root/'scripts/approve_production_profile_compatibility_v1.py'),
        'v1.1','preview','--root',str(root),'--database',str(runtime.database_path),
        '--namespace',denied_actor['namespace'],'--user-id','1','--operation-id',uuid.uuid4().hex,
        '--decisions-json',str(proposal)],capture_output=True,text=True)
    assert denied.returncode != 0
    with TestClient(build_app(runtime)) as client:
        login=client.post('/api/auth/login',json={'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login.json()['csrf_token']}
        assert client.post('/api/profile-compatibility/preview',json={
            'operation_id':uuid.uuid4().hex,'decisions':decisions}).status_code==403
        second=prepare_news_business(node,customer_name='Final negative News source (fictional)')
        original=subprocess.run
        def interrupted(command,*args,**kwargs):
            name=Path(str(command[1])).name if len(command)>1 else ''
            if name in {'novel_news_v1.py','news_delivery_v1.py'} and 'export' in command:
                kind='novel' if name=='novel_news_v1.py' else 'repurpose'
                rid=command[command.index('--request-id')+1]
                command=[command[0],str(PROJECT/'internal-console/tests/news_export_process_fault.py'),
                    str(root),rid,kind,'published' if kind=='novel' else 'receipt']
            return original(command,*args,**kwargs)
        with patch.object(subprocess,'run',side_effect=interrupted):
            with pytest.raises(AssertionError):novel_flow(client,headers,runtime,business)
            with pytest.raises(AssertionError):repurpose_flow(client,headers,runtime,second,key='native_final_fence')
        with connect(runtime.database_path) as db:
            tasks=[get_task(runtime.database_path,r['task_id']) for r in db.execute("select task_id from tasks where task_type='excel_export' and status='failed'")]
        assert len(tasks)==2 and all(t['error_code']=='NEWS_EXPORT_INTERRUPTED' for t in tasks)
        protected={p:p.read_bytes() for parent in ('data/generation_batches','data/news_deliveries','output')
            for p in (root/parent).rglob('*') if p.is_file() and p.suffix in {'.json','.xlsx'}}
        parent=effective_runtime(root)['binding']['release_ref']
        def decision(action):
            h=decision_graph(root)['heads'][key];op=uuid.uuid4().hex
            p=preview(root,runtime.database_path,news['actor'],op,[{
                'target_id':key,'target':target,'action':action,'parent':h['head'],
                'withdraws':h['effective'] if action=='withdraw' else None,'reason':'Explicit isolated final export fence'}])
            decide(root,runtime.database_path,news['actor'],op,p['preview_ref']['sha256'])
        def no_writes(phase):
            for task in tasks:
                rid=task['subject_ref'];novel=task['payload']['operation']=='novel_news_export'
                url=('/api/create/novel-news/' if novel else '/api/create/news/')+rid
                response=client.post(url+'/export',headers=headers)
                assert response.status_code!=200 or response.json().get('accepted') is False,response.text
                auth=task['payload']['export_context']['authorization_context']
                from novel_news_v1 import export_novel_news
                from news_delivery_v1 import export_news_delivery
                with pytest.raises(RuntimeError):
                    (export_novel_news if novel else export_news_delivery)(pipeline_root=root,request_id=rid,export_context=auth)
                proofs.append({'phase':phase,'kind':'novel' if novel else 'repurpose','request_id':rid,
                    'http_status':response.status_code,'native_direct_denied':True})
            assert all(p.read_bytes()==data for p,data in protected.items())
        decision('withdraw');no_writes('withdrawn')
        decision('approve');no_writes('reapproved_not_activated')
        package=owner.build_release(root,root.parent.parent/'new-fence-release',repo,contract_version='1.2',
            purpose='isolated-validation',parent_release=parent)
        staged=owner.stage_release_v1_1(package,root,repo)
        owner.activate_release_v1_1(root,repo,staged,uuid.uuid4().hex)
        no_writes('new_activation_old_request')
        with connect(runtime.database_path) as db:
            assert db.execute("select count(*) from tasks where task_type='excel_export' and status='failed'").fetchone()[0]==2
        (root/'final-news-export-fence-proof.json').write_text(json.dumps(proofs,indent=2),'utf-8')
