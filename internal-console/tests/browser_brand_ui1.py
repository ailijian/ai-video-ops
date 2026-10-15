"""New isolated brand UI node. Only acquisition/model evidence is synthetic.

Real login, CSRF, permissions, classification, Case/Persona approval and shared
publication gateways. No old UAT DB, production media or remote model is used.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uvicorn
from fastapi.testclient import TestClient
from fastapi.responses import HTMLResponse
from app.main import build_app
from app.auth_service import provision_user
from app.case_library_access import manage_reviewer
from app.canonical_gateway import _sha256
from app.task_service import claim_task, get_task, iter_queued_tasks, update_task
from conftest import settings as fixture_settings
from test_production_case_review_acceptance_v1 import provisional_review_fixture, write_json
from test_customer_speaker_e2_golden import boundary,decisions,approve_full_flow
from browser_customer_speaker_intake_v1 import driver as customer_driver

PHONES=('13900000001','13900000002','13900000003','13900000004')
PASSWORD='SyntheticCase2026!'
REPO=Path(__file__).resolve().parents[2]


def call(client,method,url,**kwargs):
    response=getattr(client,method)(url,**kwargs)
    assert response.status_code==200,(url,response.status_code,response.text)
    return response.json()


def sign_in(client,phone):
    login=call(client,'post','/api/auth/login',json={'phone':phone,'password':PASSWORD})
    return {'X-CSRF-Token':login['csrf_token']}


def analysis_fixture(settings,root,task):
    case_id=task['subject_ref']
    _,candidate,evidence=provisional_review_fixture(root,attempt_id=task['task_id'],case_id=case_id,pipeline_root=settings.pipeline_root)
    case=json.loads(candidate.read_text(encoding='utf-8'))
    case['synthetic_fixture']=True
    media=settings.repo_root/'douyin-downloader/Downloaded'/case_id
    media.mkdir(parents=True,exist_ok=True)
    video=media/'source.mp4';cover=media/'cover.png'
    # CPU-generated fictional clip; cover is extracted from its actual first frame.
    code='''import cv2,numpy as np,sys
video,cover,index=sys.argv[1],sys.argv[2],int(sys.argv[3])
image=np.full((480,320,3),(216,228,222),dtype=np.uint8)
cv2.rectangle(image,(25,70),(295,345),(166+index%35,193,181),-1)
cv2.circle(image,(160,205),70,(209,228,218),-1)
cv2.putText(image,'SCENE '+str(index),(55,400),cv2.FONT_HERSHEY_SIMPLEX,.75,(40,91,72),2)
writer=cv2.VideoWriter(video,cv2.VideoWriter_fourcc(*'mp4v'),2,(320,480))
assert writer.isOpened()
for n in range(90): writer.write(image)
writer.release();cap=cv2.VideoCapture(video);ok,frame=cap.read();assert ok;cv2.imwrite(cover,frame);cap.release()
'''
    subprocess.run([settings.pipeline_python_executable,'-c',code,str(video),str(cover),str(int(case_id[-2:]))],check=True,capture_output=True)
    source_sha=_sha256(video)
    case['identity']['duration_seconds']=45.0
    case['source_evidence']['video']={'path':str(video),'sha256':source_sha}
    case['source_evidence']['cover']={'path':str(cover),'sha256':_sha256(cover)}
    metadata=Path(case['source_provenance']['source_metadata_ref']['path'])
    value=json.loads(metadata.read_text(encoding='utf-8'));value['video']={'width':320,'height':480};write_json(metadata,value)
    acquisition=Path(case['source_provenance']['source_acquisition_ref']['path'])
    value=json.loads(acquisition.read_text(encoding='utf-8'));value.update(video=str(video),source_video_sha256=source_sha);write_json(acquisition,value)
    case['source_provenance'].update(recorded_source_media_sha256=source_sha,
        source_metadata_ref={'path':str(metadata),'sha256':_sha256(metadata)},source_acquisition_ref={'path':str(acquisition),'sha256':_sha256(acquisition)})
    write_json(candidate,case);evidence['candidate_sha256']=_sha256(candidate)
    update_task(settings.database_path,task['task_id'],status='awaiting_review',progress=100,stage='等待分类核对')
    return evidence


def classify(client,headers,case_id,industry='餐饮'):
    state=call(client,'get',f'/api/cases/{case_id}/classification')
    return call(client,'post',f'/api/cases/{case_id}/classification',headers=headers,json={
        'industry':industry,'profile':'mix','candidate_sha256':state['candidate_sha256'],
        'expected_confirmation_sha256':state['confirmation_sha256']})


def fixture_notice(application):
    @application.middleware('http')
    async def notice(request,call_next):
        response=await call_next(request)
        if 'text/html' not in response.headers.get('content-type',''):return response
        body=b''.join([part async for part in response.body_iterator])
        marker='<aside class="offline-sample-label" role="note">离线样本</aside>'.encode('utf-8')
        body=body.replace(b'</body>',marker+b'</body>')
        headers=dict(response.headers);headers.pop('content-length',None)
        return HTMLResponse(body,status_code=response.status_code,headers=headers)


def prepare(settings,root):
    with TestClient(build_app(settings)) as setup:
        for phone in PHONES:
            provision_user(settings.database_path,phone)
            login=call(setup,'post','/api/auth/login',json={'phone':phone,'password':'123456'})
            call(setup,'post','/api/auth/change-password',headers={'X-CSRF-Token':login['csrf_token']},
                 json={'current_password':'123456','new_password':PASSWORD,'confirm_password':PASSWORD})
        manage_reviewer(settings,3,action='grant',operator='isolated-fixture-operator',reason='Only synthetic reviewer C')
        a=TestClient(setup.app);c=TestClient(setup.app)
        ha=sign_in(a,PHONES[0]);hc=sign_in(c,PHONES[2])
        case_ids=[]
        titles=['一餐背后的认真','从清晨第一炉开始','一个老顾客的日常','把细节讲清楚的三十秒','这家小店为什么值得再来一次',
                '给忙碌的一天留一顿好饭','先展示过程，再给出承诺','长标题：用真实场景和清楚的节奏，记录一家社区小馆从准备到服务的日常细节']
        for index in range(23):
            case_id=f'79999999999999999{30+index:02d}'
            group=call(a,'post','/api/case-intake/groups',headers=ha,json={
                'client_request_id':f'00000000-0000-0000-0000-{index:012d}','text':f'https://www.douyin.com/video/{case_id}'})
            task=group['items'][0]['task'];evidence=analysis_fixture(settings,root,task)
            classify(a,ha,case_id,'餐饮' if index%2==0 else '烘焙甜品')
            call(c,'post',f'/api/cases/{case_id}/review',headers=hc,json={'decision':'approve','evidence_review':evidence})
            context=call(c,'get',f'/api/cases/{case_id}')['publication_context']
            data={'action':'publish','title':titles[index%len(titles)]+(f' · {index+1:02d}' if index>=len(titles) else ''),
                  'structure_summary':'从一个具体场景开始，交代过程，再用清楚的结尾收束。仅作为结构参考。',
                  'approved_case_sha256':context['approved_case_sha256'],'approval_receipt_sha256':context['approval_receipt_sha256'],
                  'expected_display_receipt_sha256':None}
            if index%3:
                data['cover_evidence']={'reference':f'synthetic-source-frame-display-consent-{case_id}',
                    'statement':'虚构样本封面取自本虚构视频；明确许可仅向本隔离节点的合法样本账号展示。','display_rights_confirmed':True}
            call(c,'post',f'/api/cases/{case_id}/publication',headers=hc,json=data)
            case_ids.append(case_id)
        # Fully fictitious business material; formal Human/Persona gates are unchanged.
        fixture_dir=REPO/'internal-console/tests/fixtures/customer_speaker_e2'
        outputs=json.loads((fixture_dir/'synthetic_outputs.json').read_text(encoding='utf-8'))
        conflict=next(i['evidence_quote'] for i in outputs['business']['constraints'] if i['constraint_type']=='identity_conflict')
        material=(fixture_dir/'GOLDEN_INPUT_FICTIONAL.md').read_text(encoding='utf-8').replace(conflict,'本品牌与合作餐厅分别归属，引用时分别核实。')+'\n[E2_UX_NORMAL]'
        businesses=[]
        names=['澄禾小馆','青瓷庭 · 社区日常与家庭聚餐服务中心','沐野烘焙','纸间手作','拾光花店','简素衣橱','街角咖啡']
        names += [f'社区样本商户 {index:02d}' for index in range(8,24)]
        for index,name in enumerate(names):
            body=call(a,'post','/api/customers/analyze',headers=ha,json={'customer_name':name,'materials':material if index<4 else '',
                       'save_only':index>=4,'submission_key':f'brand-fixture-customer-{index}'})
            business=body['business_id'];businesses.append(business)
            if index>=4:continue
            if index==3:
                update_task(settings.database_path,body['task']['task_id'],status='failed',error_code='SYNTHETIC_MODEL_BOUNDARY_FAILURE',error_message='资料整理未完成，请继续处理。')
                continue
            boundary(settings,body['task'])
            detail=call(a,'get',f'/api/customers/{business}')
            if index==2:continue  # Needs genuine Human fact review.
            payload=decisions(detail)  # Existing Golden already has an Industry Candidate.
            final=approve_full_flow(a,settings,ha['X-CSRF-Token'],business,payload)
            if index==1:
                speaker=final['speakers'][0]['speaker_id']
                result=call(a,'post','/api/create/confirm',headers=ha,json={'business_id':business,'speaker_id':speaker,
                    'profile':'mix','requested_quantity':1,'confirmed_quantity':1,'idempotency_key':'brand-existing-request'})
                request=result['result']['request_id']
                # Keep the real Request even when Business Constraint coverage blocks
                # planning. The fixture must never bypass the production Gate.
        # Owned pending, failed, running, rejected and review-ready submissions.
        for index in range(5):
            case_id=f'79999999999999999{60+index:02d}'
            group=call(a,'post','/api/case-intake/groups',headers=ha,json={'client_request_id':f'10000000-0000-0000-0000-{index:012d}','text':f'https://www.douyin.com/video/{case_id}'})
            task=group['items'][0]['task']
            if task is None:continue  # Existing admission cap leaves a durable pending item.
            if index==0:update_task(settings.database_path,task['task_id'],status='failed',error_code='SYNTHETIC_MODEL_BOUNDARY_FAILURE',error_message='解析未完成，可以继续原任务。')
            elif index==1:update_task(settings.database_path,task['task_id'],status='running',stage='正在整理视频结构')
            else:
                evidence=analysis_fixture(settings,root,task)
                if index>=3:classify(a,ha,case_id)
                if index==4:call(c,'post',f'/api/cases/{case_id}/review',headers=hc,json={'decision':'reject','reason':'虚构人审：需要更完整的结构证据。'})
        manifest={'fixture_only':True,'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
                  'source_worktree':str(REPO),'accounts':dict(zip('ABCD',PHONES)),'reviewer_user_id':3,
                  'database':str(settings.database_path),'canonical_root':str(settings.pipeline_root),
                  'shared_cases':case_ids,'customers':businesses,'model_calls':0,'qiyun_calls':0,'gpu_calls':0,
                  'cover_source':'Actual first frames of CPU-generated fictional local videos; explicit synthetic Human display receipts'}
        (root/'fixture-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        a.close();c.close()


def case_fixture_driver(settings,stop,root):
    """Only the documented acquisition/model boundary is substituted."""
    while not stop.wait(.4):
        for task in iter_queued_tasks(settings.database_path,task_types=('case_analysis',)):
            case_id=task['subject_ref']
            if not case_id.startswith('79999999999999999') or int(case_id[-2:])<80:
                continue
            if not claim_task(settings.database_path,task['task_id'],worker_id='isolated-synthetic-case-analysis',
                              lease_seconds=90,stage='整理虚构视频结构',task_type='case_analysis'):
                continue
            checkpoint=root/'fixture-checkpoints'/task['task_id']
            checkpoint.parent.mkdir(parents=True,exist_ok=True)
            event={'task_id':task['task_id'],'case_id':case_id,'boundary':'synthetic-only'}
            if case_id.endswith('81') and not checkpoint.exists():
                checkpoint.write_text('failed-once',encoding='utf-8')
                update_task(settings.database_path,task['task_id'],status='failed',error_code='SYNTHETIC_ANALYSIS_FAILURE',
                            error_message='解析未完成，请继续原任务。')
                event['result']='failed-once'
            else:
                try:
                    stop.wait(2)
                    analysis_fixture(settings,root,task)
                    event['result']='awaiting-human-classification'
                except Exception as exc:
                    update_task(settings.database_path,task['task_id'],status='failed',error_code='SYNTHETIC_FIXTURE_FAILURE',error_message=str(exc))
                    event['result']=str(exc)
            with (root/'case-fixture-events.jsonl').open('a',encoding='utf-8') as output:
                output.write(json.dumps(event,ensure_ascii=False)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workdir',type=Path,required=True)
    parser.add_argument('--port',type=int,default=18021)
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args();root=args.workdir.resolve()
    project=next(p for p in REPO.parents if (p/'.git').is_dir())
    if not any(root.is_relative_to(project/name) for name in ('.local','.verify')) or args.port==8000:parser.error('Isolated project-local root/port required')
    if not args.resume:
        if root.exists():parser.error('Use a new fixture root or --resume')
        root.mkdir(parents=True)
        settings=fixture_settings.__wrapped__(root)
        shutil.copytree(REPO/'internal-console/tests/fixtures/customer_navigation_v1/data',settings.pipeline_root/'data',dirs_exist_ok=True)
        shutil.copy2(REPO/'ops-pipeline/speaker_prompt.md',settings.pipeline_root/'speaker_prompt.md')
        shutil.copytree(REPO/'internal-console/tests/fixtures/customer_speaker_e2',root/'internal-console/tests/fixtures/customer_speaker_e2')
    else:
        manifest=json.loads((root/'fixture-manifest.json').read_text(encoding='utf-8'))
        if not manifest['fixture_only'] or manifest['source_worktree']!=str(REPO):parser.error('Not this fixture node')
        from app.config import Settings
        settings=Settings(repo_root=root,console_root=REPO/'internal-console',pipeline_root=root/'ops-pipeline',
            database_path=root/'console.sqlite3',python_executable=sys.executable)
    settings=replace(settings,repo_root=root,console_root=REPO/'internal-console',
        pipeline_python_executable=str(REPO/'ops-pipeline/.venv/Scripts/python.exe'),
        case_analysis_worker_enabled=False,customer_analysis_worker_enabled=False,speaker_analysis_worker_enabled=False,
        background_worker_enabled=False,default_business_id=None,session_cookie_name=f'brand_ui_fixture_{args.port}')
    if not args.resume:prepare(settings,root)
    application=build_app(settings);fixture_notice(application)
    stop=threading.Event()
    thread=threading.Thread(target=customer_driver,args=(settings,stop,.4,root),daemon=True)
    case_thread=threading.Thread(target=case_fixture_driver,args=(settings,stop,root),daemon=True)
    thread.start()
    case_thread.start()
    try:
        print(json.dumps({'fixture_only':True,'url':f'http://127.0.0.1:{args.port}','root':str(root)}),flush=True)
        uvicorn.run(application,host='127.0.0.1',port=args.port,workers=1,access_log=False)
    finally:stop.set();thread.join(timeout=4);case_thread.join(timeout=4)


if __name__=='__main__':main()
