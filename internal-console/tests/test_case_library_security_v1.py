from review_protocol import post_historical_case_review as post_review
"""CASE-CL0: real Session/CSRF/Gateway/Pipeline Approval, synthetic analysis only."""
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
import hashlib
import json
import shutil
import sys

import pytest
from fastapi.testclient import TestClient
from app.auth_service import provision_user
from app.config import Settings
from app.database import connect
from app.main import build_app
from app.case_library_access import manage_reviewer, principal, reviewer_authorization
from app.canonical_gateway import CanonicalOperationError, approve_case_candidate, _sha256
from app.task_service import update_task
from test_production_case_review_acceptance_v1 import CASE_ID, provisional_review_fixture, write_json


@pytest.fixture
def node(tmp_path):
    console=Path(__file__).resolve().parents[1]
    pipeline=tmp_path/'repo/ops-pipeline'
    shutil.copytree(console.parent/'ops-pipeline/scripts',pipeline/'scripts',ignore=shutil.ignore_patterns('__pycache__'))
    settings=Settings(repo_root=pipeline.parent,console_root=console,pipeline_root=pipeline,
        database_path=tmp_path/'console.sqlite3',python_executable=sys.executable,pipeline_python_executable=sys.executable,
        case_analysis_worker_enabled=False,customer_analysis_worker_enabled=False,speaker_analysis_worker_enabled=False,
        background_worker_enabled=False,
        creation_batch_enabled=True)  # Explicit isolated engineering availability; Native grants remain independent.
    app=build_app(settings)
    with TestClient(app) as keeper:
        clients={}
        for index,name in enumerate('ABCD',1):
            phone=f'1390000000{index}'
            provision_user(settings.database_path,phone)
            client=TestClient(app)
            response=client.post('/api/auth/login',json={'phone':phone,'password':'123456'})
            assert response.status_code==200
            response=client.post('/api/auth/change-password',headers={'X-CSRF-Token':response.json()['csrf_token']},
                json={'current_password':'123456','new_password':'SyntheticCase2026!','confirm_password':'SyntheticCase2026!'})
            assert response.status_code==200
            clients[name]=(client,{'X-CSRF-Token':response.json()['csrf_token']},index)
        manage_reviewer(settings,3,action='grant',operator='offline-test-operator',reason='Explicit synthetic reviewer C')
        yield settings,clients,tmp_path
        for client,_,_ in clients.values(): client.close()


def analyze(node,who='A',case_id=CASE_ID):
    settings,accounts,tmp=node
    client,headers,_=accounts[who]
    response=client.post('/api/case-intake/groups',headers=headers,json={
        'client_request_id':f"00000000-0000-0000-0000-00000000000{accounts[who][2]}",
        'text':f'https://www.douyin.com/video/{case_id}'})
    assert response.status_code==200,response.text
    group=response.json()
    return group,group['items'][0].get('task')


def ready(node):
    settings,accounts,tmp=node
    group,task=analyze(node)
    _,candidate,decisions=provisional_review_fixture(tmp,attempt_id=task['task_id'])
    case=json.loads(candidate.read_text(encoding='utf-8'))
    cover=candidate.parent/'fixture-cover.png'
    cover.write_bytes(b'synthetic offline cover bytes')
    video=settings.repo_root/'douyin-downloader/Downloaded/fixture.mp4'
    video.parent.mkdir(parents=True,exist_ok=True)
    video.write_bytes(b'source-media-was-cleaned')
    case['source_evidence']['video']['path']=str(video)
    case['source_evidence']['cover']={'path':str(cover),'sha256':_sha256(cover)}
    acquisition_path=Path(case['source_provenance']['source_acquisition_ref']['path'])
    acquisition=json.loads(acquisition_path.read_text(encoding='utf-8'))
    acquisition['video']=str(video)
    write_json(acquisition_path,acquisition)
    case['source_provenance']['source_acquisition_ref']['sha256']=_sha256(acquisition_path)
    write_json(candidate,case)
    decisions['candidate_sha256']=_sha256(candidate)
    update_task(settings.database_path,task['task_id'],status='awaiting_review',progress=100)
    a,headers,_=accounts['A']
    classification=a.get(f'/api/cases/{CASE_ID}/classification').json()
    r=a.post(f'/api/cases/{CASE_ID}/classification',headers=headers,json={
        'industry':'餐饮','profile':'mix','candidate_sha256':classification['candidate_sha256'],
        'expected_confirmation_sha256':classification['confirmation_sha256']})
    assert r.status_code==200,r.text
    return group,task,candidate,decisions,cover,video


def approve(node,decisions):
    c,headers,_=node[1]['C']
    r=post_review(c, f'/api/cases/{CASE_ID}/review',headers=headers,json={'decision':'approve','evidence_review':decisions})
    assert r.status_code==200,r.text
    return r.json()


def publish(node,*,cover=False,action='publish'):
    c,headers,_=node[1]['C']
    context=c.get(f'/api/cases/{CASE_ID}').json()['publication_context']
    assert context['available'],context
    data={'action':action,'title':'澄禾小馆：一餐背后的认真','structure_summary':'从具体场景切入，再展示过程与结尾。',
          'approved_case_sha256':context['approved_case_sha256'],'approval_receipt_sha256':context['approval_receipt_sha256'],
          'expected_display_receipt_sha256':context['display_receipt_sha256']}
    if cover and action=='publish':
        data['cover_evidence']={'reference':'synthetic-display-rights-fixture-1','statement':'明确许可该虚构封面仅供合格平台用户展示。','display_rights_confirmed':True}
    r=c.post(f'/api/cases/{CASE_ID}/publication',headers=headers,json=data)
    assert r.status_code==200,r.text
    return r.json()


def test_four_principals_formal_approval_and_private_isolation(node):
    group,task,candidate,decisions,cover,video=ready(node)
    a,ha,_=node[1]['A']; b,hb,_=node[1]['B']; c,hc,_=node[1]['C']; d,hd,_=node[1]['D']
    original=candidate.read_bytes()
    for path in (f'/api/cases/{CASE_ID}',f'/api/cases/{CASE_ID}/classification',f'/api/cases/{CASE_ID}/cover',
                 f'/api/cases/{CASE_ID}/media',f'/api/tasks/{task["task_id"]}',f'/api/case-intake/groups/{group["group_id"]}'):
        assert b.get(path).status_code==404,path
    assert b.get('/api/cases?view=mine').json()['total']==0
    assert b.get('/api/case-intake/groups').json()['groups']==[]
    assert b.get('/api/tasks').json()['tasks']==[]
    assert b.get('/api/tasks/activity').json()['events']==[]
    duplicate=b.post('/api/cases/analyze',headers=hb,json={'url':f'https://www.douyin.com/video/{CASE_ID}'}).json()
    assert duplicate['state']=='submitted' and not any(k in duplicate for k in ('existing_task','attempt_id','actor','existing_case'))
    assert task['task_id'] not in json.dumps(duplicate)
    for client,headers in ((a,ha),(d,hd)):
        r=post_review(client, f'/api/cases/{CASE_ID}/review',headers=headers,json={'decision':'approve','evidence_review':decisions})
        assert r.status_code==403 and r.json()['detail']['code']=='CASE_REVIEWER_REQUIRED'
        forged=post_review(client,f'/api/cases/{CASE_ID}/review',headers=headers,json={
            'decision':'approve','evidence_review':decisions,'reviewer':'13900000003'})
        assert forged.status_code==422  # Strict new DTO rejects undeclared actor fields.
    assert candidate.read_bytes()==original
    with pytest.raises(CanonicalOperationError) as error:
        approve_case_candidate(node[0],CASE_ID,reviewer='13900000004',note='forged owner call',
                               approval_principal=principal(node[0],4),evidence_review=decisions)
    assert error.value.code=='CASE_REVIEWER_REQUIRED'
    approved=approve(node,decisions)
    assert approved['case']['review']['approved'] and not approved['case']['media_rights']['production_authorized']
    assert b.get('/api/cases').json()['total']==0
    assert b.get(f'/api/cases/{CASE_ID}').status_code==404
    root=node[0].pipeline_root/'data/cases'/CASE_ID
    receipt=json.loads((root/'approval_receipt.json').read_text(encoding='utf-8'))
    auth=json.loads((root/'console_authorization_receipt_v1.json').read_text(encoding='utf-8'))
    assert receipt['reviewer']=='13900000003' and receipt['human_gate'] is True
    assert auth['authorized_principal']['user_id']==3
    assert not (root/'case_profile_compatibility_approval_v1.json').exists()
    assert not (node[0].pipeline_root/'data/patterns/approved').exists()
    assert auth['approval_receipt_sha256']==_sha256(root/'approval_receipt.json')


def test_publish_clearance_withdraw_and_immutable_case(node):
    _,_,_,decisions,cover,_=ready(node)
    approve(node,decisions)
    b,_,_=node[1]['B']
    root=node[0].pipeline_root/'data/cases'/CASE_ID
    before={p.name:p.read_bytes() for p in root.iterdir() if p.is_file()}
    publish(node)
    safe=b.get(f'/api/case-library/{CASE_ID}').json()
    assert node[1]['C'][0].get(f'/api/cases/{CASE_ID}').json()['shared_display']['title']==safe['title']
    assert safe['industry']=='餐饮' and safe['video_type'] is None and safe['cover_url'] is None
    assert not any(k in safe for k in ('source_url','evidence_review','full_breakdown','approved_by','submitted_by','review_media'))
    assert b.get(f'/api/cases/{CASE_ID}/media').status_code==404
    assert b.get(f'/api/case-library/{CASE_ID}/cover').status_code==404
    assert b.get('/api/cases?search=不存在').json()['total']==0
    assert b.get('/api/cases?industry=餐饮&page_size=1').json()['total']==1
    publish(node,cover=True)
    response=b.get(f'/api/case-library/{CASE_ID}/cover')
    assert response.status_code==200 and response.content==cover.read_bytes() and 'no-store' in response.headers['cache-control']
    publish(node,action='withdraw')
    assert b.get('/api/cases').json()['total']==0
    for path in (f'/api/case-library/{CASE_ID}',f'/api/case-library/{CASE_ID}/cover',f'/api/cases/{CASE_ID}',f'/api/cases/{CASE_ID}/cover'):
        assert b.get(path).status_code==404,path
    assert len(list((node[0].pipeline_root/'data/case_governance/cases'/CASE_ID/'shared_display').glob('receipt_*.json')))==3
    assert before=={p.name:p.read_bytes() for p in root.iterdir() if p.is_file()}


def test_revoke_reviewer_and_capability_history_is_immutable(node):
    _,_,_,decisions,_,_=ready(node)
    settings=node[0]; c,hc,_=node[1]['C']
    manage_reviewer(settings,3,action='revoke',operator='offline-test-operator',reason='Explicit revoke')
    assert post_review(c, f'/api/cases/{CASE_ID}/review',headers=hc,json={'decision':'approve','evidence_review':decisions}).status_code==403
    assert c.get('/api/cases?view=review').status_code==404
    with pytest.raises(CanonicalOperationError): reviewer_authorization(settings,principal(settings,3))
    db=connect(settings.database_path)
    try:
        import sqlite3
        with pytest.raises(sqlite3.IntegrityError): db.execute("UPDATE case_capability_events SET action='grant'")
        with pytest.raises(sqlite3.IntegrityError): db.execute('DELETE FROM case_capability_events')
    finally: db.close()


def test_foreign_retry_boundary_review_and_legacy_owner_are_not_guessed(node):
    _,task,_,_,_,_=ready(node)
    settings,accounts,_=node
    b,hb,_=accounts['B']
    update_task(settings.database_path,task['task_id'],status='failed',error_code='SYNTHETIC_ANALYSIS_FAILED')
    assert b.post(f'/api/tasks/{task["task_id"]}/retry',headers=hb).status_code==404
    assert b.post(f'/api/tasks/{task["task_id"]}/boundary-review',headers=hb,json={'shot_sha256':'0'*64,'decisions':[{'frame_id':'frame_000003000ms.jpg','action':'keep'}]}).status_code==404
    db=connect(settings.database_path)
    try:
        db.execute('UPDATE tasks SET created_by_user_id=NULL WHERE task_id=?',(task['task_id'],));db.commit()
    finally:db.close()
    a,_,_=accounts['A']
    assert a.get(f'/api/tasks/{task["task_id"]}').status_code==404
    submission=a.get('/api/cases?view=mine').json()
    assert submission['total']==1 and submission['cases'][0]['status']=='submitted'
    assert 'task_id' not in submission['cases'][0]  # Own Group remains known; no orphan Task is claimed.
    assert a.get(f'/api/cases/{CASE_ID}').status_code==404


def test_A_cannot_read_B_and_duplicate_group_does_not_claim_A_attempt(node):
    group_a,task_a,_,_,_,_=ready(node)
    settings,accounts,_=node
    b,hb,_=accounts['B']; a,ha,_=accounts['A']
    group_b,task_b=analyze(node,'B','7999999999999999902')
    from app.canonical_gateway import _write_atomic
    root=settings.pipeline_root/'data/case_analysis_attempts/7999999999999999902'/task_b['task_id']
    path=root/'candidate_cases/7999999999999999902/case_v1.json'
    cover=path.parent/'cover.png';cover.parent.mkdir(parents=True);cover.write_bytes(b'synthetic-B-cover')
    video=settings.repo_root/'douyin-downloader/Downloaded/B.mp4';video.write_bytes(b'synthetic-B-video')
    _write_atomic(path,{'case_id':'7999999999999999902','lifecycle':{'status':'review_required','approved':False},
        'identity':{'source_url':'https://www.douyin.com/video/7999999999999999902','industry':'待分类'},
        'analysis_lineage':{'attempt_id':task_b['task_id']},
        'source_evidence':{'cover':{'path':str(cover),'sha256':_sha256(cover)},'video':{'path':str(video)}}})
    _write_atomic(root/'case_analysis_attempt_v1.json',{'case_id':'7999999999999999902','attempt_id':task_b['task_id'],
        'status':'awaiting_review','artifacts':{'case_candidate_v1':str(path)}})
    update_task(settings.database_path,task_b['task_id'],status='awaiting_review')
    for suffix in ('','/classification','/cover','/media'):
        assert a.get('/api/cases/7999999999999999902'+suffix).status_code==404
    assert a.get(f'/api/case-intake/groups/{group_b["group_id"]}').status_code==404
    assert a.get(f'/api/tasks/{task_b["task_id"]}').status_code==404
    r=b.post('/api/case-intake/groups',headers=hb,json={'client_request_id':'00000000-0000-0000-0000-000000000012',
        'text':f'https://www.douyin.com/video/{CASE_ID}'})
    assert r.status_code==200 and r.json()['items'][0]['task'] is None
    assert r.json()['items'][0]['classification'] is None and r.json()['items'][0]['case'] is None
    assert task_a['task_id'] not in r.text and '13900000001' not in r.text
    mine=b.get('/api/cases?view=mine').json()['cases']
    assert len(mine)==2 and sum('task_id' in card for card in mine)==1


def test_pipeline_owner_rejects_ungranted_console_context_and_forged_reviewer(node):
    _,_,candidate,decisions,_,_=ready(node)
    import subprocess
    settings=node[0]
    actor=principal(settings,4)
    command=[sys.executable,str(settings.pipeline_root/'scripts/approve_case_v1.py'),'--case',str(candidate),
        '--reviewer','13900000004','--console-authority-db',str(settings.database_path),
        '--console-user-id','4','--console-principal-namespace',actor['namespace']]
    original=candidate.read_bytes()
    result=subprocess.run(command,capture_output=True,text=True)
    assert result.returncode!=0 and candidate.read_bytes()==original
    command[command.index('--console-user-id')+1]='3'
    result=subprocess.run(command,capture_output=True,text=True)
    assert result.returncode!=0 and candidate.read_bytes()==original
    assert not (settings.pipeline_root/'data/cases'/CASE_ID/'approval_receipt.json').exists()


def test_failed_media_duplicate_is_sanitized_in_all_owned_surfaces(node):
    _,task_a,_,_,_,_=ready(node)
    settings,accounts,_=node
    group_b,task_b=analyze(node,'B','7999999999999999902')
    from app.task_service import patch_task_payload
    patch_task_payload(settings.database_path,task_b['task_id'],{'duplicate':{
        'existing_case_id':CASE_ID,'existing_task_id':task_a['task_id'],'actor':'13900000001'}})
    update_task(settings.database_path,task_b['task_id'],status='failed',error_code='MEDIA_DUPLICATE_CASE',
                error_message=f"private task {task_a['task_id']} submitted by 13900000001")
    b,_,_=accounts['B']
    for path in ('/api/tasks',f'/api/tasks/{task_b["task_id"]}',f'/api/case-intake/groups/{group_b["group_id"]}',
                 '/api/cases?view=mine'):
        response=b.get(path)
        assert response.status_code==200,(path,response.text)
        assert task_a['task_id'] not in response.text and '13900000001' not in response.text,path


def test_cover_integrity_and_stale_classification_fail_closed(node):
    _,task,_,evidence,cover,_=ready(node)
    approve(node,evidence);publish(node,cover=True)
    settings,accounts,_=node
    b,_,_=accounts['B'];c,hc,_=accounts['C']
    original=cover.read_bytes();cover.write_bytes(b'corrupt-synthetic-cover')
    assert b.get(f'/api/case-library/{CASE_ID}/cover').status_code==404
    assert b.get(f'/api/case-library/{CASE_ID}').json()['cover_url'] is None
    cover.write_bytes(original)
    classification=settings.pipeline_root/'data/case_analysis_attempts'/CASE_ID/task['task_id']/'case_classification_review_v1.json'
    record=json.loads(classification.read_text(encoding='utf-8'))
    record['confirmed_case_sha256']='0'*64
    write_json(classification,record)
    assert b.get('/api/cases').json()['total']==0
    assert b.get(f'/api/case-library/{CASE_ID}').status_code==404
    context=c.get(f'/api/cases/{CASE_ID}').json()['publication_context']
    assert context['published'] is False
    response=c.post(f'/api/cases/{CASE_ID}/publication',headers=hc,json={
        'action':'publish','title':'人工标题','structure_summary':'结构参考',
        'approved_case_sha256':context['approved_case_sha256'],'approval_receipt_sha256':context['approval_receipt_sha256'],
        'expected_display_receipt_sha256':context['display_receipt_sha256']})
    assert response.status_code==409
