"""EX-S2 actual Intake/Task admission; execution-status capacity fixtures only.

This module does not claim multi-video model quality or fabricate Case Approval.
The single-case Native test owns the real analysis/Human/type/share proof.
"""
import base64,copy,json
from pathlib import Path
import pytest
from app import case_excel_orchestration as orchestration
from app.database import connect
from app.task_service import update_task,get_task,claim_task,recover_expired_tasks
from app.case_library_access import principal
from test_case_evidence_revision_v1 import node
from test_case_excel_joint_native_v1 import excel_native_node,fictional_video,run_native_task
from test_case_share_joint_v1 import payload as human_payload
from test_case_excel_import import prepared,post
from test_case_excel_preview_v03 import VECTORS,workbook


def prepared_fifteen(node,*,distinct_media=False):
    c,h,_=node[1]['A'];rows=[];uploads=[];raw=fictional_video(node[2]/'fifteen-source.mp4')
    for n in range(15):
        row=copy.deepcopy(VECTORS[8 if n>=12 else 0]['case_row'])
        row.update(external_case_key=f'FICTIONAL-FINITE-{n}',source_title=f'【全虚构】有限投稿 {n+1}',
            source_url=f'https://www.douyin.com/video/{7999999999999999750+n}' if n<12 else '',media_filename='')
        row['video_content_type_hint']=['新闻体','人设型','故事型','高转化型'][n%4]
        rows.append(row)
        if n<4:
            media=fictional_video(node[2]/f'source-{n}.mp4',seed=[1,2,1,3][n]) if distinct_media else raw
            u=c.post('/api/cases/source-files',params={'url':row['source_url'],'suffix':'.mp4','rights_confirmed':True,
                'source_match_confirmed':True},content=media,headers=h)
            assert u.status_code==200,u.text
            uploads.append({'source_row':5+n,'upload_id':u.json()['upload_id']})
    data={'file_base64':base64.b64encode(workbook(rows)).decode(),'operation_id':'save_finite_fifteen',
        'selected_rows':list(range(5,20)),'source_uploads':uploads}
    request,_=prepared(c,data,h['X-CSRF-Token']);saved=post(c,'save',request,h['X-CSRF-Token'])
    assert saved.status_code==200,saved.text
    batch=saved.json()['batch_id'];detail=c.get('/api/case-excel/imports/'+batch).json()
    refs=detail['operations'][0]['intent']['selected_rows']
    p={'operation_id':'orch_'+'a'*32,'import_operation_id':data['operation_id'],
        'expected_import_head_sha256':detail['head_sha256'],'selected_rows':refs}
    return c,h,batch,p


def checked_preview(c,h,batch,p):
    r=c.post(f'/api/case-excel/imports/{batch}/orchestration-preview',headers=h,json=p)
    assert r.status_code==200,r.text
    return {'schema_version':'case-excel-orchestration-submit-v1.0','preview':r.json(),'confirmed_submit_analysis':True}


def test_fifteen_finite_rows_respect_original_capacity_and_never_create_text_tasks(excel_native_node):
    node=excel_native_node;c,h,batch,p=prepared_fifteen(node);data=checked_preview(c,h,batch,p)
    assert data['preview']['new_task_count']==4
    base=f'/api/case-excel/imports/{batch}/orchestrations'
    with connect(node[0].database_path) as db:assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==0
    r=c.post(base,headers=h,json=data);assert r.status_code==200,r.text
    view=r.json();assert len(view['rows'])==15
    assert view['actual_new_task_count']==3 and not view['submission_complete']
    assert sum(x['state']=='pending_source' for x in view['rows'])==0  # Capacity stops before later rows.
    original_ids={x['task_id'] for x in view['rows'] if x['task_id']}
    for task in original_ids:update_task(node[0].database_path,task,status='awaiting_review')
    final=c.post(base+'/'+p['operation_id']+'/advance',headers=h)
    assert final.status_code==200,final.text
    view=final.json();assert view['submission_complete'] and view['actual_new_task_count']==4
    assert sum(x['state']=='pending_source' for x in view['rows'])==11
    assert sum(x['state']=='awaiting_review' for x in view['rows'])==3
    with connect(node[0].database_path) as db:assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==4
    assert not (node[0].pipeline_root/'data/cases').exists()
    assert c.post(base,headers=h,json=data).json()['actual_new_task_count']==4
    assert c.get(base+'/'+p['operation_id']).json()['rows']==view['rows']
    changed=copy.deepcopy(data);changed['preview']['items'][0]['relation']='duplicate'
    assert c.post(base,headers=h,json=changed).status_code==422
    duplicate=copy.deepcopy(p);duplicate['operation_id']='orch_'+'b'*32
    next_preview=checked_preview(c,h,batch,duplicate)
    assert next_preview['preview']['new_task_count']==0


@pytest.mark.parametrize('point',['native_admitted','row_result'])
def test_orchestration_response_loss_replays_same_native_tasks(excel_native_node,monkeypatch,point):
    node=excel_native_node;c,h,batch,p=prepared_fifteen(node);data=checked_preview(c,h,batch,p);seen=False
    def crash(here):
        nonlocal seen
        if here==point and not seen:seen=True;raise OSError('fictional finite response interruption')
    monkeypatch.setattr(orchestration,'checkpoint',crash)
    base=f'/api/case-excel/imports/{batch}/orchestrations'
    first=c.post(base,headers=h,json=data)
    assert first.status_code in {200,503},first.text
    with connect(node[0].database_path) as db:before={r[0] for r in db.execute('SELECT task_id FROM tasks')}
    monkeypatch.setattr(orchestration,'checkpoint',lambda *a:None)
    second=c.post(base,headers=h,json=data);assert second.status_code==200,second.text
    with connect(node[0].database_path) as db:
        after={r[0] for r in db.execute('SELECT task_id FROM tasks')}
        assert len(after)==3 and before<=after
        assert db.execute('SELECT count(DISTINCT task_id) FROM case_excel_native_admissions_v1').fetchone()[0]==3


def test_cancel_only_unadmitted_and_direct_exs1_cannot_bypass_finite_cancellation(excel_native_node):
    node=excel_native_node;c,h,batch,p=prepared_fifteen(node);data=checked_preview(c,h,batch,p)
    base=f'/api/case-excel/imports/{batch}/orchestrations';r=c.post(base,headers=h,json=data);assert r.status_code==200,r.text
    root=base+'/'+p['operation_id'];view=r.json()
    cancel={'operation_id':'control_'+'c'*32,'action':'cancel','expected_parent_sha256':view['control_head_sha256']}
    result=c.post(root+'/control',headers=h,json=cancel);assert result.status_code==200,result.text
    assert result.json()['actual_new_task_count']==3
    item=data['preview']['items'][3]
    direct=c.post(f"/api/case-excel/imports/{batch}/rows/{item['row']['row_id']}/native-submissions",headers=h,json=orchestration.native_input(item))
    assert direct.status_code==409,direct.text
    final=c.post(root+'/advance',headers=h);assert final.status_code==200,final.text
    assert final.json()['actual_new_task_count']==3 and final.json()['submission_complete']
    assert sum(x['state']=='cancelled' for x in final.json()['rows'])==12
    b,bh,_=node[1]['B']
    assert b.get(root).status_code==404
    assert b.post(root+'/advance',headers=bh).status_code==404
    assert c.post(root+'/advance').status_code==403


def test_pause_and_resume_preserve_exact_finite_intent(excel_native_node):
    node=excel_native_node;c,h,batch,p=prepared_fifteen(node);data=checked_preview(c,h,batch,p)
    base=f'/api/case-excel/imports/{batch}/orchestrations';r=c.post(base,headers=h,json=data);assert r.status_code==200,r.text
    root=base+'/'+p['operation_id']
    pause=c.post(root+'/control',headers=h,json={'operation_id':'control_'+'d'*32,'action':'pause','expected_parent_sha256':None})
    assert pause.status_code==200,pause.text
    for row in r.json()['rows']:
        if row['task_id']:update_task(node[0].database_path,row['task_id'],status='awaiting_review')
    assert c.post(root+'/advance',headers=h).json()['actual_new_task_count']==3
    resume=c.post(root+'/control',headers=h,json={'operation_id':'control_'+'e'*32,'action':'resume',
        'expected_parent_sha256':pause.json()['control_head_sha256']})
    assert resume.status_code==200,resume.text
    assert c.post(root+'/advance',headers=h).json()['actual_new_task_count']==4


def test_unknown_native_result_never_requeues_or_recounts_on_finite_replay(excel_native_node):
    node=excel_native_node;c,h,batch,p=prepared_fifteen(node);data=checked_preview(c,h,batch,p)
    base=f'/api/case-excel/imports/{batch}/orchestrations'
    submitted=c.post(base,headers=h,json=data);assert submitted.status_code==200,submitted.text
    tid=submitted.json()['rows'][0]['task_id']
    assert claim_task(node[0].database_path,tid,worker_id='fictional',lease_seconds=1,stage='analysis',task_type='case_analysis',excel_native_ready=True)
    with connect(node[0].database_path) as db:db.execute("UPDATE tasks SET lease_expires_at='2000-01-01T00:00:00Z' WHERE task_id=?",(tid,))
    assert recover_expired_tasks(node[0].database_path,task_types=('case_analysis',))==[]
    replay=c.post(base,headers=h,json=data);assert replay.status_code==200,replay.text
    row=replay.json()['rows'][0]
    assert row['task_id']==tid and row['error_code']=='CASE_EXTERNAL_RESULT_UNKNOWN' and row['state']=='failed'
    assert not claim_task(node[0].database_path,tid,worker_id='again',lease_seconds=1,stage='analysis',excel_native_ready=True)
    assert get_task(node[0].database_path,tid)['attempt_count']==1


def test_finite_admission_honors_original_backup_barrier(excel_native_node):
    from app.operation_lock import operation_lock,AUTHORITY_BACKUP_GATE
    node=excel_native_node;c,h,batch,p=prepared_fifteen(node);data=checked_preview(c,h,batch,p)
    with operation_lock(node[0].pipeline_root,AUTHORITY_BACKUP_GATE):
        blocked=c.post(f'/api/case-excel/imports/{batch}/orchestrations',headers=h,json=data)
    assert blocked.status_code==409,blocked.text
    with connect(node[0].database_path) as db:assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==0


def test_terminal_stale_source_failure_finishes_row_without_blocking_other_rows(excel_native_node):
    node=excel_native_node;c,h,batch,p=prepared_fifteen(node);data=checked_preview(c,h,batch,p)
    base=f'/api/case-excel/imports/{batch}/orchestrations'
    submitted=c.post(base,headers=h,json=data);assert submitted.status_code==200,submitted.text
    for row in submitted.json()['rows']:
        if row['task_id']:update_task(node[0].database_path,row['task_id'],status='awaiting_review')
    fourth=data['preview']['items'][3]
    upload_id=fourth['native_preview']['source']['source_upload_id']
    receipt=node[0].pipeline_root/'data/case_source_uploads'/upload_id/'source_upload_receipt_v1.json'
    receipt.write_bytes(receipt.read_bytes()+b' ')
    final=c.post(base+'/'+p['operation_id']+'/advance',headers=h)
    assert final.status_code==200,final.text
    view=final.json();assert view['submission_complete'] and view['actual_new_task_count']==3
    assert view['rows'][3]['state']=='failed' and view['rows'][3]['task_id'] is None
    assert sum(row['state']=='pending_source' for row in view['rows'])==11
    assert c.post(base+'/'+p['operation_id']+'/advance',headers=h).json()['rows']==view['rows']


def test_fifteen_rows_two_native_human_shared_cases_and_real_media_duplicate_failure(excel_native_node,monkeypatch):
    node=excel_native_node;c,h,batch,p=prepared_fifteen(node,distinct_media=True);data=checked_preview(c,h,batch,p)
    base=f'/api/case-excel/imports/{batch}/orchestrations';submitted=c.post(base,headers=h,json=data)
    assert submitted.status_code==200,submitted.text
    executions=[]
    for index,row in enumerate(submitted.json()['rows'][:3]):
        task=run_native_task(node,row['task_id'],monkeypatch)
        if index==2:
            assert task['status']=='failed' and task['error_code']=='MEDIA_DUPLICATE_CASE',task
            continue
        assert task['status']=='awaiting_review',(task['error_code'],task['error_message'])
        case_id=task['subject_ref'];url='/api/cases/'+case_id
        classification=c.get(url+'/classification').json()
        confirmed=c.post(url+'/classification',headers=h,json={'industry':'餐饮','profile':'mix',
            'candidate_sha256':classification['candidate_sha256'],'expected_confirmation_sha256':classification['confirmation_sha256']})
        assert confirmed.status_code==200,confirmed.text
        reviewer,rh,_=node[1]['C'];detail=reviewer.get(url).json();selected=['persona','story'][index]
        confirmation={'schema_version':'case-joint-type-confirmation-v1.0','catalog':detail['video_type_context']['catalog']['ref'],
            'type_id':selected,'other_note':'','profile_conflict_resolution':'correct_suggestion_with_reason',
            'reason':'依据合成分析证据明确核对类型，不采用原投稿建议。','explicitly_confirmed':True}
        preview=reviewer.post(url+'/share-preview',headers=rh,json={'type_confirmation':confirmation})
        assert preview.status_code==200,preview.text
        detail.update(preview.json());review=human_payload(detail);review['type_confirmation']=confirmation
        approved=reviewer.post(url+'/review',headers=rh,json=review)
        assert approved.status_code==200,approved.text
        executions.append(approved.json()['execution'])
        assert approved.json()['shared_display']['video_type']==selected
    advanced=c.post(base+'/'+p['operation_id']+'/advance',headers=h);assert advanced.status_code==200,advanced.text
    value=advanced.json();assert value['submission_complete'] and value['actual_new_task_count']==4
    assert sum(r['state']=='approved_shared' for r in value['rows'])==2
    assert sum(r['state']=='failed' for r in value['rows'])==1
    assert sum(r['state']=='pending_source' for r in value['rows'])==11
    # A second finite consent on the same owned Rows only reads their existing
    # completed associations; it cannot count approved records as new Tasks.
    next_input=copy.deepcopy(p);next_input['operation_id']='orch_'+'f'*32
    next_preview=checked_preview(c,h,batch,next_input)
    assert next_preview['preview']['new_task_count']==0
    repeated=c.post(base,headers=h,json=next_preview)
    assert repeated.status_code==200,repeated.text
    assert repeated.json()['actual_new_task_count']==0
    assert sum(r['state']=='approved_shared' for r in repeated.json()['rows'])==2
    ordinary,_,_=node[1]['B'];shared=ordinary.get('/api/cases?view=shared').json()
    assert shared['total']==2 and set(shared['video_types'])=={'persona','story'}
    with connect(node[0].database_path) as db:assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==4
    import os
    if os.environ.get('AIVO_VERIFICATION_ARTIFACTS'):
        (Path(os.environ['AIVO_VERIFICATION_ARTIFACTS'])/'native-fifteen-reconciliation.json').write_text(json.dumps({
            'projection':value,'human_executions':executions,'pipeline_root':str(node[0].pipeline_root),
            'scope':'15 saved Rows; 4 actual Tasks; 2 real Human/type/shared Cases; 1 real media duplicate failure; 11 source-pending Rows; one queued Task',
            'model_transports_synthetic':True,'formal_owners_mocked':False},ensure_ascii=False,indent=2),'utf8')
    # The original Publication Owner distinguishes withdrawal from incomplete
    # sharing. A read of either finite result must preserve that distinction
    # without another approval, dispatch or publication.
    case_id=get_task(node[0].database_path,submitted.json()['rows'][0]['task_id'])['subject_ref']
    url='/api/cases/'+case_id
    context=reviewer.get(url).json()['publication_context']
    withdrawn=reviewer.post(url+'/publication',headers=rh,json={'action':'withdraw',
        'approved_case_sha256':context['approved_case_sha256'],'approval_receipt_sha256':context['approval_receipt_sha256'],
        'expected_display_receipt_sha256':context['display_receipt_sha256']})
    assert withdrawn.status_code==200,withdrawn.text
    immutable={path:path.read_bytes() for path in node[0].pipeline_root.rglob('*.json') if path.is_file()}
    for operation in (p['operation_id'],next_input['operation_id']):
        current=c.get(base+'/'+operation);assert current.status_code==200,current.text
        row=next(r for r in current.json()['rows'] if r['task_id']==submitted.json()['rows'][0]['task_id'])
        assert row['state']=='approved_pending_share'  # Existing state contract stays compatible.
        assert row['sharing_state']=='approved_withdrawn'
        assert '撤回' in row['sharing_label'] and '原收录记录保留' in row['sharing_next_action']
    assert immutable=={path:path.read_bytes() for path in immutable}
    assert ordinary.get('/api/case-library/'+case_id).status_code==404
    assert node[1]['B'][0].get(base+'/'+p['operation_id']).status_code==404
    with connect(node[0].database_path) as db:assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==4
