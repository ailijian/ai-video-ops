"""Joint explicit Human action over unchanged native Business/Speaker gates."""
import json
from pathlib import Path
import pytest
from test_customer_final_confirmation import settings,prepare,preview,submit,hashes
from app.main import build_app
from fastapi.testclient import TestClient
from app import review_commands,customer_speaker_confirmation as joint
from app.persona_authority import resolve_persona_authority
from speaker_review_preparation_v1 import prepare as prepare_people
from human_review_operations_v1 import read


def receipts(settings,bid,status):
    return [p for identity in [bid,*[v['speaker_id'] for v in status['people']]]
        for p in (settings.pipeline_root/'data/personas'/identity).rglob('approval_receipt.json')]


def staged(client,settings,*,empty=False,existing=None):
    csrf,bid,body=existing or prepare(client,settings)
    body['joint_speaker_review']=True
    response=client.post(f'/api/customers/{bid}/review-preparation',headers={'X-CSRF-Token':csrf},json=body)
    assert response.status_code==200,response.text
    task=response.json()['task'];from app.task_service import get_task
    path=Path(get_task(settings.database_path,task['task_id'])['payload']['speaker_preparation_request'])
    def extract(privacy):
        material=privacy['projection']['materials_safe_semantic']
        return {'facts':[] if empty else [
            {'topic':'speaker_practice','value':['本人亲自负责洗护'],'evidence_quote':material},
            {'topic':'speaker_allowed_topics','value':['本人洗护职责'],'evidence_quote':material}]}
    prepare_people(pipeline_root=settings.pipeline_root,request_path=path,extractor=extract)
    status=client.post(f'/api/customers/{bid}/review-preparation',headers={'X-CSRF-Token':csrf},json=body)
    assert status.status_code==200,status.text
    people=status.json()['people']
    body['speaker_fact_decisions']=[{'candidate_id':p['candidate_id'],'decisions':[
        {'candidate_id':v['candidate_id'],'decision':'approve'} for v in p['facts']]} for p in people]
    return csrf,bid,body,path,status.json()


def test_preparation_is_not_human_review_and_once_confirmation_approves_both(client,settings):
    csrf,bid,body,path,status=staged(client,settings)
    assert not receipts(settings,bid,status)
    before=hashes(settings.pipeline_root)
    bundle=preview(client,bid,csrf,body)
    assert hashes(settings.pipeline_root)==before
    import base64
    signed=json.loads(base64.urlsafe_b64decode(bundle['review_context']['token'].split('.')[0]))
    assert 'speaker_request' not in signed['confirmation']['people'][0]
    assert signed['confirmation']['people'][0]['speaker_request_sha256']
    assert 'projection' not in signed['confirmation']['people'][0]
    assert signed['confirmation']['people'][0]['projection_sha256']
    assert bundle['mode']=='approve_customer_and_speakers'
    result=submit(client,bid,csrf,bundle)
    assert result.status_code==200,result.text
    assert result.json()['execution']['completion']=='customer_and_speakers_approved'
    assert resolve_persona_authority(settings,bid,'business').current
    person=status['people'][0]
    assert resolve_persona_authority(settings,person['speaker_id'],'speaker').current
    assert len(receipts(settings,bid,status))==2
    assert read(path.parent/'prepared.json')['authority']['speaker_approved'] is False
    before=hashes(settings.pipeline_root)
    replay=submit(client,bid,csrf,bundle)
    assert replay.status_code==200,replay.text
    assert replay.json()['execution']==result.json()['execution']
    assert hashes(settings.pipeline_root)==before


def test_saved_customer_review_and_speaker_draft_are_reused_without_rewriting_history(client,settings):
    csrf,bid,body=prepare(client,settings)
    saved=client.post(f'/api/customers/{bid}/facts/review',headers={'X-CSRF-Token':csrf},json=body)
    assert saved.status_code==200,saved.text
    protected={p:p.read_bytes() for folder in ('customer_intakes','speaker_intakes')
        for p in (settings.pipeline_root/'data'/folder/bid).rglob('*.json')}
    detail=client.get(f'/api/customers/{bid}').json()
    payload={'review_context':detail['review_context']['token'],'decisions':[],'constraint_decisions':[],'speaker_confirmations':[]}
    csrf,bid,body,path,status=staged(client,settings,existing=(csrf,bid,payload))
    bundle=preview(client,bid,csrf,body)
    assert bundle['mode']==joint.APPROVE
    result=submit(client,bid,csrf,bundle)
    assert result.status_code==200,result.text
    assert len(receipts(settings,bid,status))==2
    assert all(p.read_bytes()==v for p,v in protected.items())


def test_real_customer_worker_completes_preparation_without_human_review(client,settings):
    csrf,bid,body,path,status=staged(client,settings)
    from app.customer_task_service import CustomerTaskRunner
    from app.task_service import get_task
    task=joint.enqueue_preparation(settings,path,bid,1)
    worker=CustomerTaskRunner(settings)
    try:worker._run(task['task_id'])
    finally:worker.close()
    completed=get_task(settings.database_path,task['task_id'])
    assert completed['status']=='completed' and completed['stage']=='出镜人待审资料整理完成'
    assert not receipts(settings,bid,status)


def test_access_revoked_between_customer_and_person_commit_preserves_customer_receipt(client,settings,monkeypatch):
    csrf,bid,body,path,status=staged(client,settings)
    bundle=preview(client,bid,csrf,body)
    original=joint._commit_person
    def revoked(*args,**kwargs):
        from app.database import transaction
        with transaction(settings.database_path) as db:db.execute("UPDATE users SET status='disabled' WHERE id=1")
        return original(*args,**kwargs)
    monkeypatch.setattr(joint,'_commit_person',revoked)
    result=submit(client,bid,csrf,bundle)
    assert result.status_code==403,result.text
    assert resolve_persona_authority(settings,bid,'business').current
    assert not resolve_persona_authority(settings,status['people'][0]['speaker_id'],'speaker').current
    assert len(receipts(settings,bid,status))==1


def test_incomplete_person_does_not_approve_or_hide_behind_business_success(client,settings):
    csrf,bid,body,path,status=staged(client,settings,empty=True)
    bundle=preview(client,bid,csrf,body)
    assert bundle['can_submit'] is False and bundle['mode']=='save_review_progress'
    result=submit(client,bid,csrf,bundle)
    assert result.status_code==409,result.text
    assert not receipts(settings,bid,status)


def test_business_only_requires_explicit_preview_mode_and_does_not_approve_people(client,settings):
    csrf,bid,body,path,status=staged(client,settings)
    body['business_only']=True
    bundle=preview(client,bid,csrf,body)
    assert bundle['mode']=='approve_business_profile'
    result=submit(client,bid,csrf,bundle)
    assert result.status_code==200,result.text
    assert len(receipts(settings,bid,status))==1


@pytest.mark.parametrize('point',['person_target','person_receipt','result'])
def test_joint_commit_recovers_new_instance_and_session_without_duplicate_receipts(client,settings,monkeypatch,point):
    csrf,bid,body,path,status=staged(client,settings)
    bundle=preview(client,bid,csrf,body)
    import human_review_operations_v1 as native
    old_target=joint.write_once;old_native=native.write_once;old_finish=review_commands.finish
    sid=status['people'][0]['speaker_id']
    def target(p,*args,**kwargs):
        if point=='person_target' and p.parent.name=='speakers':raise OSError('synthetic target interruption')
        return old_target(p,*args,**kwargs)
    def receipt(p,*args,**kwargs):
        if point=='person_receipt' and p.name=='approval_receipt.json' and sid in p.parts:raise OSError('synthetic receipt interruption')
        return old_native(p,*args,**kwargs)
    def finish(command,value):
        if point=='result' and value.get('schema_version')==joint.VERSION:raise OSError('synthetic result interruption')
        return old_finish(command,value)
    with monkeypatch.context() as fault:
        fault.setattr(joint,'write_once',target);fault.setattr(native,'write_once',receipt);fault.setattr(review_commands,'finish',finish)
        result=submit(client,bid,csrf,bundle)
        assert result.status_code==503,result.text
    business=resolve_persona_authority(settings,bid,'business').current
    assert business
    protected={str(p):p.read_bytes() for p in (settings.pipeline_root/'data/personas'/bid).rglob('*.json')}
    pending=client.get(f'/api/review-commands/business/{bid}').json()['operations']
    assert len(pending)==1 and pending[0]['can_discard'] is False
    stable_before=hashes(settings.pipeline_root)
    replacement=client.post(f'/api/customers/{bid}/gaps/supplement',headers={'X-CSRF-Token':csrf},json={
        'answers':[{'target_gap':'business_offer','raw_answer':'新的虚构补充资料'}]})
    assert replacement.status_code==409 and replacement.json()['detail']['code']=='CUSTOMER_CONFIRMATION_PENDING'
    assert hashes(settings.pipeline_root)==stable_before
    # A second Speaker operation cannot race the unfinished joint operation.
    monkeypatch.setattr(review_commands,'_KEY',b'a-new-application-key-for-recovery')
    with TestClient(build_app(settings)) as restarted:
        login=restarted.post('/api/auth/login',json={'phone':'13800000000','password':'ReviewConsole2026!'})
        assert login.status_code==200,login.text
        new_csrf=login.json()['csrf_token']
        recovered=submit(restarted,bid,new_csrf,bundle)
        assert recovered.status_code==200,recovered.text
        assert recovered.json()['execution']['completion']=='customer_and_speakers_approved'
        stable=hashes(settings.pipeline_root)
        assert submit(restarted,bid,new_csrf,bundle).status_code==200
        assert hashes(settings.pipeline_root)==stable
    assert all(Path(p).read_bytes()==v for p,v in protected.items())
    assert len(receipts(settings,bid,status))==2


def test_joint_direct_requests_missing_decisions_wrong_sha_and_downgrade_are_rejected(client,settings):
    csrf,bid,body,path,status=staged(client,settings)
    incomplete={**body,'speaker_fact_decisions':[]}
    assert client.post(f'/api/customers/{bid}/review-preview',headers={'X-CSRF-Token':csrf},json=incomplete).status_code==409
    bundle=preview(client,bid,csrf,body);before=hashes(settings.pipeline_root)
    assert submit(client,bid,csrf,bundle,preview_sha256='0'*64).status_code==409
    assert submit(client,bid,csrf,bundle,confirmation='approve_business_profile').status_code==409
    assert client.post(f'/api/customers/{bid}/persona/approve',headers={'X-CSRF-Token':csrf},json={'review_context':bundle['review_context']['token']}).status_code==409
    assert client.post(f'/api/customers/{bid}/confirm',json={'review_context':bundle['review_context']['token'],'preview_sha256':bundle['preview_sha256'],'confirmation':bundle['mode']}).status_code==403
    assert hashes(settings.pipeline_root)==before


def test_staged_candidate_sha_change_cannot_be_approved(client,settings):
    csrf,bid,body,path,status=staged(client,settings)
    bundle=preview(client,bid,csrf,body)
    person=read(path.parent/'prepared.json')['people'][0]
    from human_review_operations_v1 import io_path
    candidate=io_path(settings.pipeline_root/person['artifacts']['candidates']['path'])
    value=read(candidate);value['fact_candidates'][0]['normalized_value']='tampered fictional identity'
    candidate.write_text(json.dumps(value),encoding='utf8')
    result=submit(client,bid,csrf,bundle)
    assert result.status_code==409,result.text
    assert not receipts(settings,bid,status)


def test_preparation_replay_and_failed_task_retry_keep_same_task(client,settings):
    csrf,bid,body=prepare(client,settings)
    body['joint_speaker_review']=True;url=f'/api/customers/{bid}/review-preparation'
    a=client.post(url,headers={'X-CSRF-Token':csrf},json=body)
    b=client.post(url,headers={'X-CSRF-Token':csrf},json=body)
    assert a.status_code==b.status_code==200
    tid=a.json()['task']['task_id'];assert tid==b.json()['task']['task_id']
    from app.task_service import update_task
    update_task(settings.database_path,tid,status='failed',error_code='SYNTHETIC_BOUNDARY_FAILURE')
    c=client.post(url,headers={'X-CSRF-Token':csrf},json=body)
    assert c.json()['state']=='failed'
    d=client.post(url,headers={'X-CSRF-Token':csrf},json={**body,'retry_preparation':True})
    assert d.status_code==200 and d.json()['task']['task_id']==tid and d.json()['task']['status']=='queued'


def test_person_identity_edits_must_rebuild_preparation_before_any_approval(client,settings):
    csrf,bid,body,path,status=staged(client,settings)
    body['speaker_fact_decisions'][0]['decisions'][0].update(decision='edit',edited_value='another fictional person')
    response=client.post(f'/api/customers/{bid}/review-preview',headers={'X-CSRF-Token':csrf},json=body)
    assert response.status_code==409,response.text
    assert not receipts(settings,bid,status)


def test_person_fact_correction_in_preview_is_exactly_the_approved_native_value(client,settings):
    csrf,bid,body,path,status=staged(client,settings)
    person=status['people'][0]
    fact=next(v for v in person['facts'] if v['field']=='speaker_role_facts')
    decision=next(v for v in body['speaker_fact_decisions'][0]['decisions'] if v['candidate_id']==fact['candidate_id'])
    decision.update(decision='edit',edited_value=['本人亲自洗护'])
    bundle=preview(client,bid,csrf,body)
    result=submit(client,bid,csrf,bundle)
    assert result.status_code==200,result.text
    actual=resolve_persona_authority(settings,person['speaker_id'],'speaker').current['artifact']
    assert actual['facts']['speaker_role_facts']['value']==['本人亲自洗护']
    assert joint.speaker_projection(actual)==bundle['people'][0]['projection']


def test_joint_context_cannot_forge_legacy_version_or_client_authority_fields(client,settings):
    import base64
    csrf,bid,body,path,status=staged(client,settings)
    bundle=preview(client,bid,csrf,body);before=hashes(settings.pipeline_root)
    token,signature=bundle['review_context']['token'].split('.')
    context=json.loads(base64.urlsafe_b64decode(token));context['version']=review_commands.VERSION
    forged=base64.urlsafe_b64encode(json.dumps(context,sort_keys=True).encode()).decode()+'.'+signature
    assert submit(client,bid,csrf,{**bundle,'review_context':{'token':forged}}).status_code==409
    body['actor']='forged'
    assert client.post(f'/api/customers/{bid}/review-preview',headers={'X-CSRF-Token':csrf},json=body).status_code==422
    assert hashes(settings.pipeline_root)==before
