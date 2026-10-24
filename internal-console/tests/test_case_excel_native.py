"""Isolated Native admission tests. No Case/type/Publication is fabricated."""
import copy
import json
import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime,timedelta,timezone

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app import case_excel_native as native, case_uploads
from app.auth_service import provision_user,resolve_session
from app.database import connect
from app.main import build_app
from app.task_service import claim_task,get_task,recover_expired_tasks,create_case_task,TaskSubmissionError,CaseTaskRunner
from conftest import login_and_change_password
from test_case_excel_import import payload,prepared,post


def setup_row(client,settings,monkeypatch,*,op='op_save_1',media=True):
    csrf=login_and_change_password(client)
    monkeypatch.setattr(case_uploads,'probe_upload',lambda *a:{'duration_seconds':2,'width':64,'height':64,'audio_present':True})
    data=payload(1,op=op)
    if media:
        upload=client.post('/api/cases/source-files',params={'url':'https://www.douyin.com/video/7999999999999999700',
            'suffix':'.mp4','rights_confirmed':True,'source_match_confirmed':True},content=b'FICTIONAL media boundary unit fixture',headers={'X-CSRF-Token':csrf})
        assert upload.status_code==200,upload.text
        data['source_uploads']=[{'source_row':5,'upload_id':upload.json()['upload_id']}]
    request,context=prepared(client,data,csrf)
    saved=post(client,'save',request,csrf)
    assert saved.status_code==200,saved.text
    batch=saved.json()['batch_id'];detail=client.get('/api/case-excel/imports/'+batch).json()
    row=detail['rows'][0];operation=detail['operations'][0];binding=operation['intent']['row_source_bindings'][0]
    prepare={'schema_version':'case-excel-native-prepare-input-v1.0-proposal','batch_id':batch,'row_id':row['row_id'],
        'import_operation_id':op,'expected_row_sha256':native.imports.record_sha(row),
        'expected_import_intent_sha256':operation['intent_sha256'],'expected_import_head_sha256':detail['head_sha256'],
        'source_upload_id':(binding['native_upload_ref'] or {}).get('upload_id'),'action':'analyze_new','reason':'','expected_prior_attempt':None}
    return csrf,prepare


def preview(client,csrf,prepare):
    return client.post(f"/api/case-excel/imports/{prepare['batch_id']}/rows/{prepare['row_id']}/native-preview",json=prepare,headers={'X-CSRF-Token':csrf})


def submission(client,csrf,prepare,operation='native_one'):
    response=preview(client,csrf,prepare)
    assert response.status_code==200,response.text
    v=response.json();assert v['can_submit'],v
    return {'schema_version':'case-excel-native-submission-input-v1.0-proposal','submission_operation_id':operation,
        'origin':v['origin'],'expected_submission_parent_sha256':None,'source_upload_id':prepare['source_upload_id'],
        'confirmed_submit_analysis':True,'preflight_sha256':v['preflight_sha256'],'action':'analyze_new','reason':'','expected_prior_attempt':None}


def submit(client,csrf,p,data):
    return client.post(f"/api/case-excel/imports/{p['batch_id']}/rows/{p['row_id']}/native-submissions",json=data,headers={'X-CSRF-Token':csrf})


def test_exact_task_and_atomic_mapping_replay_and_reader(client,settings,monkeypatch):
    csrf,p=setup_row(client,settings,monkeypatch);data=submission(client,csrf,p)
    with connect(settings.database_path) as db:assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==0
    first=submit(client,csrf,p,data);assert first.status_code==200,first.text
    result=first.json();assert result['state']=='admitted' and result['case_approved'] is False and result['shared_published'] is False
    task=get_task(settings.database_path,result['task_id']);native.validate_primary_origin(settings,task)
    assert task['payload'].get('operator_profile_hint') is None  # Excel hint is not Native classification.
    assert 'raw_case' not in task['payload'] and 'raw_segments' not in task['payload']
    assert submit(client,csrf,p,data).json()==result
    url=f"/api/case-excel/imports/{p['batch_id']}/rows/{p['row_id']}/native-submissions/native_one"
    assert client.get(url).json()==result
    cards=client.get('/api/cases?view=mine').json()['cases']
    assert len(cards)==1 and cards[0]['task_id']==result['task_id'] and cards[0]['status']=='queued'
    with connect(settings.database_path) as db:
        assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM case_excel_native_admissions_v1').fetchone()[0]==1
    assert not (settings.pipeline_root/'data/cases/7999999999999999700').exists()


@pytest.mark.parametrize('point',['intent','reservation','task_transaction','task_committed','submission_receipt','association','scheduled'])
def test_failure_windows_keep_one_task_and_exact_intent(client,settings,monkeypatch,point):
    csrf,p=setup_row(client,settings,monkeypatch);data=submission(client,csrf,p);fired=False
    def crash(here):
        nonlocal fired
        if here==point and not fired:fired=True;raise OSError('isolated interruption')
    monkeypatch.setattr(native,'checkpoint',crash)
    first=submit(client,csrf,p,data);assert first.status_code==503,first.text
    assert fired
    with connect(settings.database_path) as db:
        count=db.execute('SELECT count(*) FROM tasks').fetchone()[0]
        if point=='task_transaction':assert count==0
        if point=='task_committed':
            assert count==1
            task_id=db.execute('SELECT task_id FROM tasks').fetchone()[0]
            assert not claim_task(settings.database_path,task_id,worker_id='test',lease_seconds=1,stage='test',task_type='case_analysis')
    final=submit(client,csrf,p,data);assert final.status_code==200,final.text
    assert final.json()==submit(client,csrf,p,data).json()
    with connect(settings.database_path) as db:assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==1


def test_claim_and_unknown_fence_cover_old_url_task_entry(client,settings,monkeypatch):
    csrf,p=setup_row(client,settings,monkeypatch);result=submit(client,csrf,p,submission(client,csrf,p)).json();tid=result['task_id']
    native.validate_primary_origin(settings,get_task(settings.database_path,tid))
    assert claim_task(settings.database_path,tid,worker_id='test',lease_seconds=1,stage='test',task_type='case_analysis',excel_native_ready=True)
    with connect(settings.database_path) as db:db.execute("UPDATE tasks SET lease_expires_at='2000-01-01T00:00:00Z' WHERE task_id=?",(tid,))
    assert recover_expired_tasks(settings.database_path,task_types=('case_analysis',))==[]
    task=get_task(settings.database_path,tid)
    assert task['status']=='failed' and task['error_code']=='CASE_EXTERNAL_RESULT_UNKNOWN'
    assert not claim_task(settings.database_path,tid,worker_id='new',lease_seconds=1,stage='test',excel_native_ready=True)
    with pytest.raises(TaskSubmissionError,match='原分析结果未知'):
        create_case_task(settings.database_path,source_url=task['payload']['source_url'],case_id=task['subject_ref'],created_by_user_id=1,reanalyze=True)
    assert native.upload_is_reserved(settings,p['source_upload_id'])


def test_worker_does_not_claim_before_companions(client,settings,monkeypatch):
    csrf,p=setup_row(client,settings,monkeypatch);data=submission(client,csrf,p)
    monkeypatch.setattr(native,'checkpoint',lambda point:(_ for _ in ()).throw(OSError('stop')) if point=='task_committed' else None)
    assert submit(client,csrf,p,data).status_code==503
    with connect(settings.database_path) as db:tid=db.execute('SELECT task_id FROM tasks').fetchone()[0]
    runner=CaseTaskRunner(settings)
    try:runner._run(tid)
    finally:runner.close()
    assert get_task(settings.database_path,tid)['status']=='queued'
    with connect(settings.database_path) as db:assert db.execute('SELECT execution_claimed FROM case_excel_native_admissions_v1').fetchone()[0]==0


def test_strict_inputs_and_source_shortage_do_not_create_tasks(client,settings,monkeypatch):
    csrf,p=setup_row(client,settings,monkeypatch,media=False)
    session=resolve_session(settings.database_path,client.cookies.get(settings.session_cookie_name))
    assert native.preview(replace(settings,case_acquisition_provider='upload_only'),session,p['batch_id'],p['row_id'],p)['can_submit'] is False
    assert preview(client,csrf,{**p,'actor':{'user_id':2}}).status_code==422
    assert preview(client,csrf,{**p,'expected_row_sha256':'a'*64}).status_code==409
    url=f"/api/case-excel/imports/{p['batch_id']}/rows/{p['row_id']}/native-preview"
    assert client.post(url,json=p).status_code==403
    with connect(settings.database_path) as db:assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==0


def test_draft_2020_schema_catalog_integer_and_unknown_fields():
    schema=native.schema();Draft202012Validator.check_schema(schema)
    root=__import__('pathlib').Path(__file__).resolve().parents[2]
    catalog=json.loads((root/'docs/deliveries/case-excel-import-1/native-i3-review-r2/CATALOG_EXAMPLE_REVIEW_ONLY.json').read_text('utf8'))['candidate']
    with pytest.raises(native.imports.ImportError):native.checked(catalog,'TypeCatalog')
    catalog['version']=1;native.checked(catalog,'TypeCatalog')
    for value in ['1',True,0]:
        with pytest.raises(native.imports.ImportError):native.checked({**catalog,'version':value},'TypeCatalog')
    with pytest.raises(native.imports.ImportError):native.checked({**catalog,'approved':True},'TypeCatalog')


def test_owned_existing_task_links_without_new_primary_origin(client,settings,monkeypatch):
    csrf,p=setup_row(client,settings,monkeypatch);first=submit(client,csrf,p,submission(client,csrf,p)).json()
    before=get_task(settings.database_path,first['task_id'])['payload']
    second=submit(client,csrf,p,submission(client,csrf,p,'native_second')).json()
    assert second['state']=='linked_owned_task' and second['task_id']==first['task_id']
    assert get_task(settings.database_path,first['task_id'])['payload']==before
    with connect(settings.database_path) as db:
        assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==1
        assert db.execute("SELECT count(*) FROM case_excel_native_admissions_v1 WHERE relation_kind='new_origin_task'").fetchone()[0]==1


def test_second_account_private_duplicate_gets_no_task_or_notes(settings,monkeypatch):
    with TestClient(build_app(settings)) as first:
        provision_user(settings.database_path,'13800000000')
        csrf,p=setup_row(first,settings,monkeypatch);a=submit(first,csrf,p,submission(first,csrf,p)).json()
        with TestClient(build_app(settings)) as second:
            provision_user(settings.database_path,'13900000882')
            login=second.post('/api/auth/login',json={'phone':'13900000882','password':'123456'}).json()
            changed=second.post('/api/auth/change-password',json={'current_password':'123456','new_password':'PrivateFixture2026!','confirm_password':'PrivateFixture2026!'},headers={'X-CSRF-Token':login['csrf_token']}).json()
            data=payload(1,'second_save');request,context=prepared(second,data,changed['csrf_token'])
            b=post(second,'save',request,changed['csrf_token']).json();detail=second.get('/api/case-excel/imports/'+b['batch_id']).json();op=detail['operations'][0]
            q={**p,'batch_id':b['batch_id'],'row_id':detail['rows'][0]['row_id'],'import_operation_id':'second_save',
                'expected_row_sha256':native.imports.record_sha(detail['rows'][0]),'expected_import_intent_sha256':op['intent_sha256'],
                'expected_import_head_sha256':detail['head_sha256'],'source_upload_id':None}
            result=submit(second,changed['csrf_token'],q,submission(second,changed['csrf_token'],q)).json()
            assert result['state']=='duplicate_private_recorded' and result['task_id'] is None and result['native_input_sha256'] is None
            assert a['task_id'] not in json.dumps(result)
            assert second.get(f"/api/case-excel/imports/{p['batch_id']}/rows/{p['row_id']}/native-submissions/native_one").status_code==404
            assert second.get(f"/api/cases/7999999999999999700/attempts/{a['task_id']}/excel-notes").status_code in {403,404}
    with connect(settings.database_path) as db:
        assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM case_excel_native_admissions_v1').fetchone()[0]==1


@pytest.mark.parametrize('change',['different_input','stale_head','revoke_session','source_sha','unknown_field'])
def test_changed_inputs_and_authorization_fail_closed(client,settings,monkeypatch,change):
    csrf,p=setup_row(client,settings,monkeypatch);data=submission(client,csrf,p)
    if change=='different_input':
        assert submit(client,csrf,p,data).status_code==200;data={**data,'reason':'changed intent'}
    elif change=='stale_head':
        # Original I2 path creates a new legitimate import intent/head.
        # A regenerated XLSX may have identical cells but different ZIP times
        # and therefore a different Batch. Exercise the SAME exact input bytes.
        original=settings.pipeline_root/'data/case_intake_imports/1'/p['batch_id']/'workbook.xlsx'
        next_import={'file_base64':base64.b64encode(original.read_bytes()).decode(),'operation_id':'new_import_head','selected_rows':[5],'source_uploads':[]}
        request,_=prepared(client,next_import,csrf);saved=post(client,'save',request,csrf)
        assert saved.status_code==200,saved.text
        assert saved.json()['batch_id']==p['batch_id']
        assert client.get('/api/case-excel/imports/'+p['batch_id']).json()['head_sha256']!=p['expected_import_head_sha256']
    elif change=='revoke_session':
        with connect(settings.database_path) as db:db.execute("UPDATE sessions SET expires_at='2000-01-01T00:00:00Z'")
    elif change=='source_sha':
        directory=settings.pipeline_root/'data/case_source_uploads'/p['source_upload_id']
        media=next(v for v in directory.iterdir() if v.suffix=='.mp4');media.write_bytes(b'changed bytes')
    else:data={**data,'approved':True}
    result=submit(client,csrf,p,data)
    assert result.status_code in {401,403,409,422},result.text
    with connect(settings.database_path) as db:assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==(1 if change=='different_input' else 0)


def test_pending_upload_hold_blocks_original_cleanup(client,settings,monkeypatch):
    csrf,p=setup_row(client,settings,monkeypatch);data=submission(client,csrf,p)
    monkeypatch.setattr(native,'checkpoint',lambda point:(_ for _ in ()).throw(OSError('stop')) if point=='reservation' else None)
    assert submit(client,csrf,p,data).status_code==503
    assert native.upload_is_reserved(settings,p['source_upload_id'])
    base=settings.pipeline_root/'data/case_intake_imports'
    reservation=next(base.glob('*/*/native_submissions/*/source_upload_reservation.json'))
    raw=json.loads(reservation.read_text('utf8'));raw['submission_input_sha256']='a'*64;reservation.write_text(json.dumps(raw),'utf8')
    with pytest.raises(ValueError,match='Invalid native upload reservation'):native.upload_is_reserved(settings,p['source_upload_id'])


def test_reviewer_notes_only_exact_primary_origin_fixture(client,settings,monkeypatch,tmp_path):
    from test_production_case_review_acceptance_v1 import approval_fixture
    from app.task_service import update_task
    csrf,p=setup_row(client,settings,monkeypatch);result=submit(client,csrf,p,submission(client,csrf,p)).json();tid=result['task_id']
    # Existing isolated review-required evidence fixture, NOT a Native/model E2E
    # success or fabricated Approval. Current Task remains the original Task.
    approval_fixture(tmp_path/'notes_fixture',case_id='7999999999999999700',attempt_id=tid,pipeline_root=settings.pipeline_root)
    update_task(settings.database_path,tid,status='awaiting_review',stage='unit review fixture')
    response=client.get(f'/api/cases/7999999999999999700/attempts/{tid}/excel-notes')
    assert response.status_code==200,response.text
    value=response.json();assert value['trust']=='unverified_submitter_candidate'
    assert value['evidence_promoted'] is value['case_approved'] is value['shared_published'] is False
    assert set(value['notes'])=={'case_notes','segments','rights_claims'}
    assert 'media_filename' not in value['notes']['case_notes']
    assert 'supporting_document_ref' not in value['notes']['rights_claims']
    assert client.get('/api/cases/7999999999999999700/attempts/another_attempt/excel-notes').status_code==404
    from app.case_library_access import manage_reviewer
    manage_reviewer(settings,1,action='revoke',operator='isolated-test',reason='negative reader fixture')
    assert client.get(f'/api/cases/7999999999999999700/attempts/{tid}/excel-notes').status_code==403


def test_concurrent_confirmation_and_legacy_entry_share_original_task(client,settings,monkeypatch):
    csrf,p=setup_row(client,settings,monkeypatch);data=submission(client,csrf,p)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:submit(client,csrf,p,data),range(2)))
    assert all(r.status_code in {200,409} for r in responses)
    result=submit(client,csrf,p,data).json()
    legacy=create_case_task(settings.database_path,source_url='https://www.douyin.com/video/7999999999999999700',case_id='7999999999999999700',created_by_user_id=1)
    assert legacy['task_id']==result['task_id']
    with connect(settings.database_path) as db:
        assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM case_excel_native_admissions_v1').fetchone()[0]==1


def test_missing_admission_table_cannot_downgrade_a_native_execution_fence(client,settings,monkeypatch):
    csrf,p=setup_row(client,settings,monkeypatch);submit(client,csrf,p,submission(client,csrf,p))
    with connect(settings.database_path) as db:db.execute('DROP TABLE case_excel_native_admissions_v1')
    with pytest.raises(TaskSubmissionError,match='调度身份缺失'):
        create_case_task(settings.database_path,source_url='https://www.douyin.com/video/7999999999999999701',case_id='7999999999999999701')


@pytest.mark.parametrize('kind',['filename_only','text_only','unsupported_platform'])
def test_unsupported_sources_remain_private_without_invented_native_identity(client,settings,monkeypatch,kind):
    from test_case_excel_preview_v03 import VECTORS,workbook
    csrf=login_and_change_password(client)
    row=copy.deepcopy(VECTORS[8 if kind=='text_only' else 0]['case_row'])
    if kind=='unsupported_platform':row.update(source_url='https://www.example.com/video/fictional',source_platform='其它')
    else:
        row['source_url']='';row['media_filename']='fictional.mp4' if kind=='filename_only' else ''
        if kind=='text_only':row['submission_mode']='仅文字待补证'
    data=payload(1,op='unsupported_save');data['file_base64']=base64.b64encode(workbook([row])).decode()
    request,context=prepared(client,data,csrf);saved=post(client,'save',request,csrf)
    assert saved.status_code==200,saved.text
    record=client.get('/api/case-excel/imports/'+saved.json()['batch_id']).json()
    candidate=record['rows'][0];op=record['operations'][0]
    q={'schema_version':'case-excel-native-prepare-input-v1.0-proposal','batch_id':record['batch']['batch_id'],'row_id':candidate['row_id'],
        'import_operation_id':'unsupported_save','expected_row_sha256':native.imports.record_sha(candidate),
        'expected_import_intent_sha256':op['intent_sha256'],'expected_import_head_sha256':record['head_sha256'],'source_upload_id':None,
        'action':'analyze_new','reason':'','expected_prior_attempt':None}
    response=preview(client,csrf,q);assert response.status_code==200,response.text
    assert response.json()['can_submit'] is False and response.json()['source'] is None
    with connect(settings.database_path) as db:assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==0
