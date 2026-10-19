"""Real HTTP/CSRF, Business lock, Human owners and recovery; synthetic parsing only."""
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from conftest import login_and_change_password
from test_customer_speaker_smart_intake_v1 import settings, seed_customer, review_payload
from test_customer_constraints_e2_http import seed as restricted_customer
from app import customer_confirmation as owner, review_commands
from app.main import build_app
from app.persona_authority import resolve_persona_authority


def hashes(root):
    return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*.json') if '.locks' not in p.parts}


def prepare(client, settings, *, restricted=False):
    csrf=login_and_change_password(client)
    body,detail=(restricted_customer(client,settings,csrf) if restricted else seed_customer(client,settings,csrf))
    payload=review_payload(detail) if not restricted else {
        'review_context':detail['review_context']['token'],
        'decisions':[{'candidate_id':v['candidate_id'],'decision':'approve'} for v in detail['fact_candidates'] if v['state']=='requires_review'],
        'constraint_decisions':[{'constraint_id':v['constraint_id'],'decision':'defer'} for v in detail['constraint_candidates']]}
    return csrf,body['business_id'],payload


def preview(client,bid,csrf,payload):
    response=client.post(f'/api/customers/{bid}/review-preview',headers={'X-CSRF-Token':csrf},json=payload)
    assert response.status_code==200,response.text
    return response.json()


def submit(client,bid,csrf,bundle,**changes):
    return client.post(f'/api/customers/{bid}/confirm',headers={'X-CSRF-Token':csrf},json={
        'review_context':bundle['review_context']['token'],'preview_sha256':bundle['preview_sha256'],
        'confirmation':bundle['mode'],**changes})


def test_preview_is_read_only_and_once_confirm_keeps_two_records_and_speaker_independent(client,settings):
    csrf,bid,payload=prepare(client,settings)
    before=hashes(settings.pipeline_root)
    bundle=preview(client,bid,csrf,payload)
    assert hashes(settings.pipeline_root)==before
    assert bundle['mode']==owner.APPROVE
    result=submit(client,bid,csrf,bundle)
    assert result.status_code==200,result.text
    approved=resolve_persona_authority(settings,bid,'business').current
    assert approved and owner.projection(approved['artifact'])==bundle['projection']
    decision=json.loads((settings.pipeline_root/result.json()['execution']['decision_ref']['path']).read_text())
    assert len(decision['fact_review_refs'])>=3
    receipt=json.loads(approved['receipt_path'].read_text())
    assert receipt['review_decision_metadata']['decision_artifact_ref']==result.json()['execution']['decision_ref']
    detail=client.get(f'/api/customers/{bid}').json()
    assert detail['speakers'] and all(v['status']!='approved' for v in detail['speakers'])
    before=hashes(settings.pipeline_root)
    again=submit(client,bid,csrf,bundle)
    assert again.status_code==200,again.text
    assert again.json()['execution']==result.json()['execution']
    assert hashes(settings.pipeline_root)==before
    assert len(list((settings.pipeline_root/'data/personas'/bid).rglob('approval_receipt.json')))==1
    assert submit(client,bid,csrf,bundle,confirmation=owner.SAVE).status_code==409
    assert hashes(settings.pipeline_root)==before


def test_edited_fact_is_exactly_the_approved_value(client,settings):
    csrf,bid,payload=prepare(client,settings)
    detail=client.get(f'/api/customers/{bid}').json()
    target=next(v for v in detail['fact_candidates'] if v['field']=='primary_products_or_services')
    item=next(v for v in payload['decisions'] if v['candidate_id']==target['candidate_id'])
    item.update(decision='edit',edited_value=['宠物洗护（先检查毛发）'])
    bundle=preview(client,bid,csrf,payload)
    assert bundle['projection']['facts']['primary_products_or_services']==['宠物洗护（先检查毛发）']
    result=submit(client,bid,csrf,bundle)
    assert result.status_code==200,result.text
    assert resolve_persona_authority(settings,bid,'business').current['artifact']['facts']['primary_products_or_services']['value']==['宠物洗护（先检查毛发）']


@pytest.mark.parametrize('point',['target','receipt','result'])
def test_committed_stage_recovers_across_process_and_session_without_duplicate_receipts(client,settings,monkeypatch,point):
    csrf,bid,payload=prepare(client,settings)
    bundle=preview(client,bid,csrf,payload)
    original_write=owner.write_once
    original_finish=review_commands.finish
    import human_review_operations_v1 as approval
    original_approval_write=approval.write_once
    def interrupted(path,*args,**kwargs):
        if (point=='target' and path.name=='business_approval_target.json') or (point=='receipt' and path.name=='approval_receipt.json'):
            raise OSError('synthetic interrupted persistence')
        return (original_approval_write if point=='receipt' else original_write)(path,*args,**kwargs)
    def finish(*args,**kwargs):
        if point=='result':raise OSError('synthetic result interrupted')
        return original_finish(*args,**kwargs)
    monkeypatch.setattr(owner,'write_once',interrupted if point=='target' else original_write)
    monkeypatch.setattr(approval,'write_once',interrupted if point=='receipt' else original_approval_write)
    monkeypatch.setattr(review_commands,'finish',finish)
    failed=submit(client,bid,csrf,bundle)
    assert failed.status_code==503,failed.text
    pending=client.get(f'/api/review-commands/business/{bid}').json()['operations']
    assert len(pending)==1 and pending[0]['can_discard'] is False
    progress=list((settings.pipeline_root/'data/customer_intakes'/bid).glob('*/review_progress/*.json'))
    assert len(progress)==1
    blocked=client.post(f'/api/customers/{bid}/review-preview',headers={'X-CSRF-Token':csrf},json=payload)
    assert blocked.status_code==409 and blocked.json()['detail']['code']=='CUSTOMER_CONFIRMATION_PENDING'
    protected={p:p.read_bytes() for p in progress}
    monkeypatch.setattr(owner,'write_once',original_write)
    monkeypatch.setattr(approval,'write_once',original_approval_write)
    monkeypatch.setattr(review_commands,'finish',original_finish)
    monkeypatch.setattr(review_commands,'_KEY',b'new process signing key')
    import app.customer_gateway as gateway
    monkeypatch.setattr(gateway,'_REVIEW_CONTEXT_KEY',b'new fact signing key')
    with TestClient(build_app(settings)) as restarted:
        login=restarted.post('/api/auth/login',json={'phone':'13800000000','password':'ReviewConsole2026!'})
        assert login.status_code==200,login.text
        new_csrf=login.json()['csrf_token']
        recovered=submit(restarted,bid,new_csrf,bundle)
        assert recovered.status_code==200,recovered.text
        assert recovered.json()['execution']['completion']=='business_approved'
        stable=hashes(settings.pipeline_root)
        assert submit(restarted,bid,new_csrf,bundle).status_code==200
        assert hashes(settings.pipeline_root)==stable
    assert all(p.read_bytes()==value for p,value in protected.items())
    assert len(list((settings.pipeline_root/'data/personas'/bid).rglob('approval_receipt.json')))==1


def test_missing_confirmation_wrong_preview_and_downgrade_cannot_write(client,settings):
    csrf,bid,payload=prepare(client,settings)
    bundle=preview(client,bid,csrf,payload);before=hashes(settings.pipeline_root)
    url=f'/api/customers/{bid}'
    assert client.post(url+'/confirm',headers={'X-CSRF-Token':csrf},json={'review_context':bundle['review_context']['token']}).status_code==422
    assert submit(client,bid,csrf,bundle,preview_sha256='0'*64).status_code==409
    assert submit(client,bid,csrf,bundle,actor='fake actor').status_code==422
    assert client.post(url+'/persona/approve',headers={'X-CSRF-Token':csrf},json={'review_context':bundle['review_context']['token']}).status_code==409
    assert hashes(settings.pipeline_root)==before


@pytest.mark.parametrize('action',['defer','exclude'])
def test_unverified_claim_can_only_proceed_with_legal_exclusion(client,settings,action):
    csrf,bid,payload=prepare(client,settings,restricted=True)
    payload['constraint_decisions'][0]['decision']=action
    bundle=preview(client,bid,csrf,payload)
    assert bundle['mode']==(owner.APPROVE if action=='exclude' else owner.SAVE)
    before=hashes(settings.pipeline_root)
    if action=='defer':
        assert submit(client,bid,csrf,bundle,confirmation=owner.APPROVE).status_code==409
        assert hashes(settings.pipeline_root)==before
    response=submit(client,bid,csrf,bundle)
    assert response.status_code==200,response.text
    assert bool(resolve_persona_authority(settings,bid,'business').current)==(action=='exclude')


def test_partial_review_saves_only_and_never_silently_approves(client,settings):
    csrf,bid,payload=prepare(client,settings)
    payload['decisions']=payload['decisions'][:1]
    bundle=preview(client,bid,csrf,payload)
    assert bundle['mode']==owner.SAVE
    response=submit(client,bid,csrf,bundle)
    assert response.status_code==200,response.text
    assert response.json()['execution']['completion']=='review_saved'
    assert resolve_persona_authority(settings,bid,'business').current is None


def test_existing_fact_review_is_not_resubmitted_or_rewritten(client,settings):
    csrf,bid,payload=prepare(client,settings)
    saved=client.post(f'/api/customers/{bid}/facts/review',headers={'X-CSRF-Token':csrf},json=payload)
    assert saved.status_code==200,saved.text
    protected={p:p.read_bytes() for p in (settings.pipeline_root/'data/customer_intakes'/bid).rglob('*.json')}
    detail=client.get(f'/api/customers/{bid}').json()
    bundle=preview(client,bid,csrf,{'review_context':detail['review_context']['token'],'decisions':[]})
    assert bundle['mode']==owner.APPROVE
    result=submit(client,bid,csrf,bundle)
    assert result.status_code==200,result.text
    assert all(p.read_bytes()==v for p,v in protected.items())


def test_csrf_stale_source_and_cancelled_operation_cannot_approve(client,settings):
    csrf,bid,payload=prepare(client,settings)
    bundle=preview(client,bid,csrf,payload);before=hashes(settings.pipeline_root)
    assert client.post(f'/api/customers/{bid}/confirm',json={}).status_code in {403,422}
    assert hashes(settings.pipeline_root)==before


def test_other_actor_cannot_borrow_confirmation_and_revoked_access_cannot_resume(client,settings):
    csrf,bid,payload=prepare(client,settings);bundle=preview(client,bid,csrf,payload)
    from app.auth_service import provision_user
    from app.database import transaction
    provision_user(settings.database_path,'13900000001')
    with TestClient(build_app(settings)) as other:
        login=other.post('/api/auth/login',json={'phone':'13900000001','password':'123456'})
        other_csrf=login.json()['csrf_token']
        changed=other.post('/api/auth/change-password',headers={'X-CSRF-Token':other_csrf},json={
            'current_password':'123456','new_password':'AnotherFixture2026!','confirm_password':'AnotherFixture2026!'})
        assert changed.status_code==200,changed.text
        before=hashes(settings.pipeline_root)
        assert submit(other,bid,other_csrf,bundle).status_code==403
        assert hashes(settings.pipeline_root)==before
    with transaction(settings.database_path) as connection:
        connection.execute("UPDATE users SET status='disabled' WHERE phone=?",('13800000000',))
    before=hashes(settings.pipeline_root)
    assert submit(client,bid,csrf,bundle).status_code in {401,403}
    assert hashes(settings.pipeline_root)==before


def test_context_version_cannot_be_forged_to_reuse_legacy_approval(client,settings):
    import base64
    csrf,bid,payload=prepare(client,settings);bundle=preview(client,bid,csrf,payload)
    body,signature=bundle['review_context']['token'].split('.')
    context=json.loads(base64.urlsafe_b64decode(body));context['version']=review_commands.VERSION
    forged=base64.urlsafe_b64encode(json.dumps(context).encode()).decode()+'.'+signature
    before=hashes(settings.pipeline_root)
    response=client.post(f'/api/customers/{bid}/persona/approve',headers={'X-CSRF-Token':csrf},json={'review_context':forged})
    assert response.status_code==409
    assert hashes(settings.pipeline_root)==before
    partial={**payload,'decisions':payload['decisions'][:1],'speaker_confirmations':[]}
    saved=client.post(f'/api/customers/{bid}/facts/review',headers={'X-CSRF-Token':csrf},json=partial)
    assert saved.status_code==200,saved.text
    before=hashes(settings.pipeline_root)
    assert submit(client,bid,csrf,bundle).status_code==409
    assert hashes(settings.pipeline_root)==before


def test_uncommitted_intent_can_be_cancelled_but_never_replayed_as_approval(client,settings,monkeypatch):
    csrf,bid,payload=prepare(client,settings);bundle=preview(client,bid,csrf,payload)
    original=review_commands.write_once
    def interrupted(path,value):
        original(path,value)
        if path.name=='intent.json':raise OSError('intent persisted before response')
    with monkeypatch.context() as patch:
        patch.setattr(review_commands,'write_once',interrupted)
        assert submit(client,bid,csrf,bundle).status_code==503
    pending=client.get(f'/api/review-commands/business/{bid}').json()['operations']
    assert len(pending)==1 and pending[0]['can_discard'] is True
    cancelled=client.post(f"/api/review-commands/business/{bid}/{pending[0]['operation_id']}/cancel",headers={'X-CSRF-Token':csrf})
    assert cancelled.status_code==200,cancelled.text
    before=hashes(settings.pipeline_root)
    assert submit(client,bid,csrf,bundle).status_code==409
    assert hashes(settings.pipeline_root)==before
    assert resolve_persona_authority(settings,bid,'business').current is None


def test_speaker_draft_failure_does_not_undo_or_repeat_business_approval(client,settings,monkeypatch):
    csrf,bid,payload=prepare(client,settings);bundle=preview(client,bid,csrf,payload)
    import app.customer_gateway as gateway
    with monkeypatch.context() as patch:
        patch.setattr(gateway,'prepare_discovered_speaker_draft',lambda *a,**k:(_ for _ in ()).throw(OSError('fictional draft disk interruption')))
        response=submit(client,bid,csrf,bundle)
    assert response.status_code==200,response.text
    assert response.json()['execution']['completion']=='business_approved'
    assert response.json()['execution']['speaker_confirmation']['retry_required'] is True
    current=resolve_persona_authority(settings,bid,'business').current
    protected={p:p.read_bytes() for p in (current['path'],current['receipt_path'])}
    retry=client.post(f'/api/customers/{bid}/speaker-discovery/confirm',headers={'X-CSRF-Token':csrf},json={'decisions':[]})
    assert retry.status_code==200 and not retry.json()['speaker_confirmation']['retry_required'],retry.text
    assert all(p.read_bytes()==v for p,v in protected.items())
    assert all(v['status']!='approved' for v in client.get(f'/api/customers/{bid}').json()['speakers'])


def test_access_revoked_between_review_and_approval_keeps_review_without_approving(client,settings,monkeypatch):
    csrf,bid,payload=prepare(client,settings);bundle=preview(client,bid,csrf,payload)
    import app.customer_gateway as gateway
    from app.database import transaction
    original=gateway.review_customer_facts
    def review_then_revoke(*args,**kwargs):
        result=original(*args,**kwargs)
        with transaction(settings.database_path) as connection:
            connection.execute("UPDATE users SET status='disabled' WHERE phone=?",('13800000000',))
        return result
    monkeypatch.setattr(gateway,'review_customer_facts',review_then_revoke)
    response=submit(client,bid,csrf,bundle)
    assert response.status_code==403,response.text
    assert resolve_persona_authority(settings,bid,'business').current is None
    assert len(list((settings.pipeline_root/'data/customer_intakes'/bid).glob('*/review_progress/*.json')))==1
    assert not list((settings.pipeline_root/'data/personas'/bid).rglob('approval_receipt.json'))
