"""Excel -> real upload/Task/Orchestrator -> three real Human records."""
from dataclasses import replace
from pathlib import Path
import json,os,subprocess
from contextlib import ExitStack
import pytest
from fastapi.testclient import TestClient
from app.main import build_app
from test_case_evidence_revision_v1 import node
from test_case_excel_import import payload,prepared,post
from test_case_excel_native import submission,submit
from test_case_share_joint_v1 import payload as human_payload
from app.task_service import CaseTaskRunner,get_task
from human_review_operations_v1 import file_sha


def fictional_video(path,seed=0):
    project=Path(__file__).resolve().parents[2]
    subprocess.run([str(project/'ops-pipeline/.venv/Scripts/python.exe'),str(project/'ops-pipeline/tests/case_excel_native_synthetic.py'),
        '--make-media',str(path),str(seed)],check=True,capture_output=True)
    return path.read_bytes()


@pytest.fixture
def excel_native_node(node):
    project=Path(__file__).resolve().parents[2]
    settings=replace(node[0],pipeline_python_executable=str(project/'ops-pipeline/.venv/Scripts/python.exe'),case_acquisition_provider='upload_only')
    app=build_app(settings)
    with ExitStack() as stack:
        stack.enter_context(TestClient(app));accounts={}
        for name,index in [('A',1),('B',2),('C',3)]:
            client=stack.enter_context(TestClient(app))
            login=client.post('/api/auth/login',json={'phone':f'1390000000{index}','password':'SyntheticCase2026!'})
            assert login.status_code==200,login.text
            accounts[name]=(client,{'X-CSRF-Token':login.json()['csrf_token']},index)
        yield settings,accounts,node[2]


def run_native_task(node,task_id,monkeypatch):
    settings=node[0];project=Path(__file__).resolve().parents[2]
    runner=CaseTaskRunner(settings);original=subprocess.Popen
    def external_models(command,*args,**kw):
        if len(command)>1 and Path(command[1]).name=='case_analysis_v1.py':
            command=[command[0],str(project/'ops-pipeline/tests/case_excel_native_synthetic.py'),'--pipeline',str(settings.pipeline_root),*command[2:]]
        return original(command,*args,**kw)
    try:
        with monkeypatch.context() as patch:
            patch.setattr('app.task_service.subprocess.Popen',external_models);runner._run(task_id)
    finally:runner.executor.shutdown(wait=True)
    return get_task(settings.database_path,task_id)


def test_excel_uploaded_native_analysis_one_review_typed_share_and_withdraw(excel_native_node,monkeypatch):
    node=excel_native_node
    settings=node[0];c,h,_=node[1]['A'];case_id='7999999999999999700'
    upload=c.post('/api/cases/source-files',params={'url':'https://www.douyin.com/video/'+case_id,'suffix':'.mp4',
        'rights_confirmed':True,'source_match_confirmed':True},content=fictional_video(node[2]/'fictional.mp4'),headers=h)
    assert upload.status_code==200,upload.text
    data=payload(1,op='native_closed_loop');data['source_uploads']=[{'source_row':5,'upload_id':upload.json()['upload_id']}]
    save,_=prepared(c,data,h['X-CSRF-Token']);saved=post(c,'save',save,h['X-CSRF-Token'])
    assert saved.status_code==200,saved.text
    batch=saved.json()['batch_id'];record=c.get('/api/case-excel/imports/'+batch).json()
    row=record['rows'][0];op=record['operations'][0]
    from app.case_excel_import import record_sha
    p={'schema_version':'case-excel-native-prepare-input-v1.0-proposal','batch_id':batch,'row_id':row['row_id'],
        'import_operation_id':'native_closed_loop','expected_row_sha256':record_sha(row),'expected_import_intent_sha256':op['intent_sha256'],
        'expected_import_head_sha256':record['head_sha256'],'source_upload_id':upload.json()['upload_id'],
        'action':'analyze_new','reason':'','expected_prior_attempt':None}
    admitted=submit(c,h['X-CSRF-Token'],p,submission(c,h['X-CSRF-Token'],p,'native_real_single'))
    assert admitted.status_code==200,admitted.text
    task_id=admitted.json()['task_id'];project=Path(__file__).resolve().parents[2]
    python=project/'ops-pipeline/.venv/Scripts/python.exe'
    runner=CaseTaskRunner(replace(settings,pipeline_python_executable=str(python)))
    original=subprocess.Popen
    def external_models(command,*args,**kw):
        if len(command)>1 and Path(command[1]).name=='case_analysis_v1.py':
            command=[command[0],str(project/'ops-pipeline/tests/case_excel_native_synthetic.py'),'--pipeline',str(settings.pipeline_root),*command[2:]]
        return original(command,*args,**kw)
    with monkeypatch.context() as patch:
        patch.setattr('app.task_service.subprocess.Popen',external_models)
        runner._run(task_id)
    runner.executor.shutdown(wait=True)
    task=get_task(settings.database_path,task_id)
    state_path=settings.pipeline_root/'data/case_analysis_attempts'/case_id/task_id/'case_analysis_attempt_v1.json'
    assert task['status']=='awaiting_review',(task['error_code'],task['error_message'],state_path.read_text('utf8') if state_path.exists() else 'no native state')
    from case_source_upload_v1 import native_review_reservation
    from storage_retention_v1 import _transient_targets
    acquisition=json.loads((state_path.parent/'source_acquisition_v1.json').read_text('utf8'))
    media=Path(acquisition['video']);assert media.is_file()
    assert native_review_reservation(settings.pipeline_root,state_path.parent,acquisition)
    hold=next(settings.pipeline_root.glob('data/case_intake_imports/*/*/native_submissions/*/source_upload_reservation.json'))
    raw=hold.read_bytes();bad=json.loads(raw);bad['submission_input_sha256']='0'*64
    hold.write_text(json.dumps(bad),'utf8')
    try:
        with pytest.raises(ValueError,match='mismatch'):
            _transient_targets(state_path.parent,settings.repo_root/'douyin-downloader')
        assert media.is_file()  # Broken reservation fails closed before deletion.
    finally:hold.write_bytes(raw)
    context=c.get('/api/cases/'+case_id+'/classification').json()
    classified=c.post('/api/cases/'+case_id+'/classification',headers=h,json={'industry':'餐饮','profile':'mix',
        'candidate_sha256':context['candidate_sha256'],'expected_confirmation_sha256':context['confirmation_sha256']})
    assert classified.status_code==200,classified.text
    reviewer,rh,_=node[1]['C'];url='/api/cases/'+case_id
    detail=reviewer.get(url).json();assert detail['excel_notes_available']
    notes=reviewer.get(url+'/attempts/'+task_id+'/excel-notes');assert notes.status_code==200,notes.text
    assert notes.json()['trust']=='unverified_submitter_candidate'
    confirmation={'schema_version':'case-joint-type-confirmation-v1.0','catalog':detail['video_type_context']['catalog']['ref'],
        'type_id':'persona','other_note':'','profile_conflict_resolution':'correct_suggestion_with_reason',
        'reason':'人工依据实际视频纠正投稿类型建议，保留 mix 制作方式。','explicitly_confirmed':True}
    from app.case_shared_display import _build_share_preview
    from app.case_library_access import principal
    _build_share_preview(settings,case_id,principal(settings,3))
    preview=reviewer.post(url+'/share-preview',headers=rh,json={'type_confirmation':confirmation})
    assert preview.status_code==200,preview.text
    detail.update(preview.json());review=human_payload(detail);review['type_confirmation']=confirmation
    approved=reviewer.post(url+'/review',headers=rh,json=review)
    assert approved.status_code==200,approved.text
    result=approved.json();execution=result['execution'];assert execution['completion']=='approved_shared'
    for key in ['approval_receipt_ref','type_decision_ref','publication_receipt_ref']:
        ref=execution[key];assert file_sha(settings.pipeline_root/ref['path'])==ref['sha256']
    ordinary,_,_=node[1]['B'];shared=ordinary.get('/api/case-library/'+case_id)
    assert shared.status_code==200 and shared.json()['video_type']=='persona'
    assert ordinary.get('/api/cases?video_type=persona').json()['total']==1
    assert ordinary.get(url+'/media').status_code==404
    assert not (settings.pipeline_root/'data/patterns/approved').exists()
    evidence={'batch_id':batch,'row_id':row['row_id'],'task_id':task_id,'attempt_id':task_id,'execution':execution,
        'pipeline_root':str(settings.pipeline_root),'source_upload_receipt_sha256':task['payload']['source_upload']['receipt_sha256'],
        'media_actual_and_uploaded':True,'platform_original_verified':False,'model_transports_synthetic':True,
        'approval_type_publication_owners_real':True,'source_media_production_rights_granted':False}
    target=os.environ.get('AIVO_VERIFICATION_ARTIFACTS')
    if target:(Path(target)/'native-single-case.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),'utf8')
    context=reviewer.get(url).json()['publication_context']
    withdrawn=reviewer.post(url+'/publication',headers=rh,json={'action':'withdraw',
        'approved_case_sha256':context['approved_case_sha256'],'approval_receipt_sha256':context['approval_receipt_sha256'],
        'expected_display_receipt_sha256':context['display_receipt_sha256']})
    assert withdrawn.status_code==200,withdrawn.text
    assert ordinary.get('/api/case-library/'+case_id).status_code==404
    assert ordinary.get(url).status_code==404
    assert ordinary.get('/api/cases?view=shared&search=视频结构参考').json()['total']==0
    assert reviewer.post(url+'/review',headers=rh,json=review).status_code==200
    assert ordinary.get(url).status_code==404
