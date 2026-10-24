"""PC-E13: seven/eight genuinely approved Native beats, one derived video row."""
import json,os,subprocess
from dataclasses import replace
from pathlib import Path
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from test_news_novel_runtime_v1_2 import native_news_runtime
from news_golden_support_v1_2 import prepare_news_business
from test_news_generation_recovery_v1 import create,worker as news_worker
from test_review_flow_closure_v1 import amend,finish_speaker_review
from test_customer_speaker_revision_v1 import review_current
from review_protocol import post_review
from test_publish_copy_native_v1 import install_templates
from publish_copy_native_support import post,current,generation,confirm,worker
from profile_compatibility_decisions_v1_1 import read,file_sha
from app.main import build_app
from app.task_service import get_task

def test_native_seven_and_eight_beats_combined_derivation_human_confirmation_and_excel(node):
    runtime,_,_,_,_=native_news_runtime(node)
    runtime=replace(runtime,publish_copy_enabled=True);root=runtime.pipeline_root;install_templates(root)
    evidence=[]
    with TestClient(build_app(runtime)) as client:
        login=client.post('/api/auth/login',json={'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login.json()['csrf_token']};csrf=headers['X-CSRF-Token']
        for count,expected in [(7,5),(8,6)]:
            b=prepare_news_business(node,customer_name=f'制作标题{count}段（全虚构）');bid=b['business_id'];sid=b['speaker_id']
            facts=['套餐含一份主食','套餐含两份蔬菜','门店提供密封餐盒','餐盒随套餐提供','服务仅限午餐',
                   '到店领取前核对订单','下单时核对忌口'][:count-1]
            amend(client,bid,csrf,field='included_service_facts',value=facts);review_current(client,bid,csrf)
            response=post_review(client,'/api/customers/'+bid+'/persona/approve',headers=headers,json={'note':'全虚构逐项价格服务人审'})
            assert response.status_code==200,response.text
            amend(client,bid,csrf,sid=sid,action='rebase');finish_speaker_review(client,bid,sid,csrf)
            response=post_review(client,'/api/customers/'+bid+'/speakers/'+sid+'/persona/approve',headers=headers,json={'note':'独立核对客户最新来源'})
            assert response.status_code==200,response.text
            rid,tid=create(client,headers,b,f'publish_many_beats_{count}')
            result=news_worker(runtime,tid,'pc_beats_'+str(count));assert result.returncode==0,(result.stdout,result.stderr)
            assert get_task(runtime.database_path,tid)['status']=='completed',get_task(runtime.database_path,tid)
            directory=root/'data/generation_batches'/rid;plan=read(directory/'novel_news_beat_plan_v1.json')
            assert len(plan['micro_information_beats'])==count
            response=client.post('/api/create/novel-news/'+rid+'/review',headers=headers,json={
                'decisions':[{'beat_id':v['beat_id'],'decision':'approved'} for v in plan['micro_information_beats']]})
            assert response.status_code==200,response.text
            approved=directory/'approved_novel_news_v1.json';approved_sha=file_sha(approved)
            generated=generation(client,headers,rid);result=worker(runtime,generated['task']['task_id'])
            assert result.returncode==0,(result.stdout,result.stderr)
            assert get_task(runtime.database_path,generated['task']['task_id'])['status']=='completed'
            state=current(client,rid);headlines=state['draft']['payload']['items'][0]['production_headlines']
            assert len(headlines)==expected
            assert {u for h in headlines for u in h['source_unit_ids']}=={v['beat_id'] for v in plan['micro_information_beats']}
            confirm(client,headers,rid)
            exported=post(client,'/api/create/'+rid+'/publish-copy/export',headers)
            result=worker(runtime,exported['task']['task_id']);assert result.returncode==0,(result.stdout,result.stderr)
            assert get_task(runtime.database_path,exported['task']['task_id'])['status']=='completed',get_task(runtime.database_path,exported['task']['task_id'])
            delivery=current(client,rid)['delivery'];output=Path(delivery['output_path'])
            opened=subprocess.run([runtime.pipeline_python_executable,'-c',
                'import sys,json;from openpyxl import load_workbook;w=load_workbook(sys.argv[1]);'
                'print(json.dumps({"sheets":w.sheetnames,"rows":w.active.max_row,"columns":w.active.max_column,"value":w.active["A5"].value},ensure_ascii=False))',str(output)],
                capture_output=True,text=True,encoding='utf-8',env={**os.environ,'PYTHONIOENCODING':'utf-8'})
            assert opened.returncode==0,opened.stderr
            workbook=json.loads(opened.stdout)
            assert workbook=={'sheets':['Sheet1'],'rows':5,'columns':4,'value':'\n'.join(h['text'] for h in headlines)}
            assert file_sha(approved)==approved_sha
            assert len(read(root/'data/content_ledgers'/bid/'content_ledger_v1.json')['entries'])==1
            evidence.append({'native_count':count,'delivery_headline_count':expected,'request_id':rid,'delivery':delivery,'workbook':workbook})
        (root/'many_beats_acceptance.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
