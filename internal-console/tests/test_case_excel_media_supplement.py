"""Same-file supplementation uses existing immutable Intake/Upload contracts."""
import copy
from app import case_uploads
from app.database import connect
from conftest import login_and_change_password
from test_case_excel_import import payload,prepared,post


def test_supplement_same_workbook_links_private_candidate_and_preserves_old_intent(client,settings,monkeypatch):
    cases_before={p:p.read_bytes() for p in (settings.pipeline_root/'data/cases').rglob('*') if p.is_file()}
    csrf=login_and_change_password(client);headers={'X-CSRF-Token':csrf}
    original=payload(1,op='save_before_media');request,_=prepared(client,original,csrf)
    old=post(client,'save',request,csrf);assert old.status_code==200,old.text
    batch=old.json()['batch_id'];before=client.get('/api/case-excel/imports/'+batch).json()
    saved_sha=before['operations'][0]['result']['row_results'][0]['candidate_ref_sha256']
    root=settings.pipeline_root/'data/case_intake_imports/1'/batch
    prior={p:p.read_bytes() for p in root.glob('operations/save_before_media/*.json')}
    monkeypatch.setattr(case_uploads,'probe_upload',lambda *a:{'duration_seconds':2,'width':64,'height':64,'audio_present':True})
    upload=client.post('/api/cases/source-files',headers=headers,params={'url':'https://www.douyin.com/video/7999999999999999700',
        'suffix':'.mp4','rights_confirmed':True,'source_match_confirmed':True},content=b'fictional upload boundary fixture')
    assert upload.status_code==200,upload.text
    supplement=copy.deepcopy(original);supplement.update(operation_id='save_with_media',source_uploads=[{'source_row':5,'upload_id':upload.json()['upload_id']}])
    new,_=prepared(client,supplement,csrf);saved=post(client,'save',new,csrf)
    assert saved.status_code==200,saved.text
    assert saved.json()['batch_id']==batch
    record=client.get('/api/case-excel/imports/'+batch).json()
    assert len(record['rows'])==1 and len(record['operations'])==2
    latest=next(x for x in record['operations'] if x['intent']['operation_id']=='save_with_media')
    assert latest['result']['row_results'][0]['candidate_ref_sha256']==saved_sha
    assert latest['current_bindings'][0]['current_media_state']=='checked_unverified_upload'
    assert latest['intent']['row_source_bindings'][0]['native_upload_ref']['upload_id']==upload.json()['upload_id']
    assert prior=={p:p.read_bytes() for p in prior}
    with connect(settings.database_path) as db:assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==0
    assert cases_before=={p:p.read_bytes() for p in (settings.pipeline_root/'data/cases').rglob('*') if p.is_file()}
