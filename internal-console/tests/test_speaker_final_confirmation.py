"""Native HTTP/CSRF, Review/Approval writers and recovery; synthetic extraction only."""
import base64,json,subprocess
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from conftest import login_and_change_password
from test_customer_speaker_smart_intake_v1 import settings
from test_customer_speaker_revision_v1 import approved_customer,approved_speaker
from test_customer_final_confirmation import hashes
from app import speaker_confirmation as owner,review_commands
from app.main import build_app
from app.persona_authority import resolve_persona_authority
from app.task_service import update_task
from app.database import transaction
from review_protocol import post_review


def prepare(client,settings,*,reviewed=False,risky_scope=False):
    csrf=login_and_change_password(client);bid=approved_customer(client,settings,csrf)
    if reviewed:
        sid=approved_speaker(client,settings,csrf,bid,approve=False)
    else:
        response=client.post(f'/api/customers/{bid}/speakers/analyze',headers={'X-CSRF-Token':csrf},json={
            'speaker_name':'王琳','public_role':'店主','speaker_type':'owner_founder',
            'materials':'王琳是小爪宠物店店主，日常由她亲自接待顾客，检查宠物皮肤和毛发状态，并根据现场情况确认洗护方案。她可以分享自己在门店接待、宠物洗护前判断和日常服务中的实际经验。','forbidden_claims':[]})
        assert response.status_code==200,response.text
        value=response.json();sid=value['speaker_id'];task=value['task']
        code="""
import json,sys,runpy
from pathlib import Path
fixture=runpy.run_path(str(Path(sys.argv[1])/'ops-pipeline/tests/test_speaker_persona_vertical_slice_v1.py'))
extractor=fixture['fixture_extractor']
if sys.argv[4]=='risk':
    def extractor(*args,**kwargs):
        value=fixture['fixture_extractor'](*args,**kwargs)
        for fact in value['facts']:
            if fact['topic']=='speaker_scope':fact['value']=['可将企业的全部成绩作为本人经历讲述']
        return value
fixture['analysis'].analyze_speaker_onboarding(request=json.loads(Path(sys.argv[3]).read_text(encoding='utf8')),
    pipeline_root=Path(sys.argv[2]),extractor=extractor)
"""
        done=subprocess.run([settings.pipeline_python_executable,'-X','utf8','-c',code,str(settings.repo_root),str(settings.pipeline_root),task['payload']['request_path'],'risk' if risky_scope else 'protective'],capture_output=True,text=True,encoding='utf8',timeout=30)
        assert done.returncode==0,done.stderr
        update_task(settings.database_path,task['task_id'],status='awaiting_review',progress=100,stage='等待人工核对')
    url=f'/api/customers/{bid}/speakers/{sid}'
    detail=client.get(url).json()
    return csrf,bid,sid,url,detail,{'review_context':detail['approval_context']['token'],'decisions':[
        {'candidate_id':v['candidate_id'],'decision':'approve'} for v in detail['fact_candidates'] if v['state']=='requires_review'] if not reviewed else []}


def preview(client,url,csrf,body):
    result=client.post(url+'/review-preview',headers={'X-CSRF-Token':csrf},json=body)
    assert result.status_code==200,result.text
    return result.json()


def submit(client,url,csrf,bundle,**changes):
    return client.post(url+'/confirm',headers={'X-CSRF-Token':csrf},json={
        'review_context':bundle['review_context']['token'],'preview_sha256':bundle['preview_sha256'],
        'confirmation':bundle['mode'],**changes})


def test_one_confirmation_has_independent_review_and_approval_exact_replay_and_no_duplicate_task(client,settings):
    csrf,bid,sid,url,detail,body=prepare(client,settings)
    before=hashes(settings.pipeline_root)
    bundle=preview(client,url,csrf,body)
    assert hashes(settings.pipeline_root)==before and bundle['can_submit']
    assert detail['unified_confirmation_enabled'] and any(v.get('default_review_selection')=='approve' for v in detail['fact_candidates'])
    original_business={p:p.read_bytes() for p in (settings.pipeline_root/'data/personas'/bid).rglob('*.json')}
    result=submit(client,url,csrf,bundle);assert result.status_code==200,result.text
    execution=result.json()['execution'];assert execution['completion']=='speaker_approved'
    current=resolve_persona_authority(settings,sid,'speaker').current
    assert owner.projection(current['artifact'])==bundle['projection']
    receipt=json.loads(current['receipt_path'].read_text())
    assert receipt['review_decision_metadata']=={'decision_artifact_ref':execution['decision_ref']}
    assert execution['fact_review_ref']['path']!=execution['approval_receipt_ref']['path']
    assert result.json()['speaker']['media_rights']['established'] is False
    stable=hashes(settings.pipeline_root);again=submit(client,url,csrf,bundle)
    assert again.status_code==200 and again.json()['execution']==execution and hashes(settings.pipeline_root)==stable
    assert all(p.read_bytes()==data for p,data in original_business.items())
    assert len(list((settings.pipeline_root/'data/personas'/sid).rglob('approval_receipt.json')))==1
    with transaction(settings.database_path) as db:assert db.execute('select count(*) from tasks where task_type=? and subject_ref=?',('speaker_analysis',sid)).fetchone()[0]==1


def test_saved_legacy_review_is_preserved_and_approved_without_repeating_it(client,settings):
    csrf,bid,sid,url,detail,body=prepare(client,settings,reviewed=True)
    protected={p:p.read_bytes() for p in (settings.pipeline_root/'data/speaker_intakes'/bid/sid).rglob('*.json')}
    bundle=preview(client,url,csrf,body);assert bundle['can_submit']
    result=submit(client,url,csrf,bundle);assert result.status_code==200,result.text
    assert all(p.read_bytes()==v for p,v in protected.items())


def test_sourced_protective_boundary_is_pending_bulk_confirmation_not_a_saved_decision(client,settings):
    csrf,bid,sid,url,detail,body=prepare(client,settings)
    boundary=next(v for v in detail['fact_candidates'] if v['field']=='role_scope_constraints')
    assert boundary['protective_scope'] is True and boundary['default_review_selection']=='approve'
    assert not list((settings.pipeline_root/'data/personas'/sid).rglob('approval_receipt.json'))
    assert not list((settings.pipeline_root/'data/speaker_intakes'/bid/sid).rglob('speaker_fact_review_v1.json'))
    before=hashes(settings.pipeline_root)
    pending={'review_context':detail['approval_context']['token'],'decisions':[
        {'candidate_id':v['candidate_id'],'decision':v['default_review_selection']}
        for v in detail['fact_candidates'] if v['state']=='requires_review' and v.get('default_review_selection')]}
    bundle=preview(client,url,csrf,pending)
    assert bundle['can_submit'] and hashes(settings.pipeline_root)==before
    result=submit(client,url,csrf,bundle);assert result.status_code==200,result.text
    current=resolve_persona_authority(settings,sid,'speaker').current
    constraint=current['artifact']['facts']['role_scope_constraints']
    assert constraint['state']=='known' and constraint['value']==boundary['value']
    stable=hashes(settings.pipeline_root)
    assert submit(client,url,csrf,bundle).status_code==200 and hashes(settings.pipeline_root)==stable


def test_protective_scope_requires_exact_native_source_and_only_restrictive_clauses():
    import copy
    from human_review_operations_v1 import digest
    raw=[{'answer_id':'raw','source_ref':'source','answer_text':'我只讲自己实际参与的工作，不把公司的全部成绩写成个人功劳。'}]
    intake={'intake_id':'intake_0001','raw_answers':raw,'raw_input_contract':{'raw_answers_sha256':digest(raw)},
        'business_ref':{'persona_id':'business'},'speaker_selection':{'speaker_ref':{'persona_id':'speaker'}}}
    artifact={'intake_ref':{'intake_id':'intake_0001','raw_answers_sha256':digest(raw)}}
    candidate={'target_field':'role_scope_constraints','normalized_value':['只讲本人实际参与的工作，不转用公司的全部成绩'],
        'persona_scope':'speaker','raw_answer_ref':'raw','source_ref':'source','source_excerpt':raw[0]['answer_text']}
    def policy(c=candidate,a=artifact,i=intake):
        return owner.review_policy(c,source_verified=owner.sourced_scope(c,a,i,'business','speaker'))
    assert policy()['protective_scope'] and policy()['default_review_selection']=='approve'
    for changes in ({'source_ref':'foreign'},{'raw_answer_ref':'foreign'},{'source_excerpt':'不存在的原文'},
            {'persona_scope':'business'},{'conflict_refs':['unresolved']},{'authority_conflict':True},
            {'severity':'critical'},{'review_note':'本人经历待核实'},
            {'normalized_value':['只讲本人实际参与的工作，同时可以讲公司全部经历']},
            {'normalized_value':['不受角色限制']},{'normalized_value':['允许使用本人肖像']},
            {'normalized_value':['只讲本人实际参与的工作',None]}):
        assert policy({**candidate,**changes})['default_review_selection'] is None,changes
    for path in [('raw_input_contract','raw_answers_sha256'),('business_ref','persona_id')]:
        broken=copy.deepcopy(intake);broken[path[0]][path[1]]='wrong'
        assert policy(i=broken)['default_review_selection'] is None
    broken=copy.deepcopy(intake);broken['speaker_selection']['speaker_ref']['persona_id']='foreign'
    assert policy(i=broken)['default_review_selection'] is None
    for key in ['intake_id','raw_answers_sha256']:
        assert policy(a={'intake_ref':{**artifact['intake_ref'],key:'wrong'}})['default_review_selection'] is None
    assert owner.review_policy({**candidate,'protective_scope':True})['default_review_selection'] is None


@pytest.mark.parametrize('point',['review','target','approval_receipt','result'])
def test_interruption_recovers_new_session_instance_without_duplicate_review_receipt_or_task(client,settings,monkeypatch,point):
    csrf,bid,sid,url,detail,body=prepare(client,settings);bundle=preview(client,url,csrf,body)
    import human_review_operations_v1 as native
    original_review=__import__('speaker_fact_review_v1').review_speaker_facts
    def review(**kwargs):
        value=original_review(**kwargs)
        if point=='review':raise OSError('synthetic after native review')
        return value
    original_write=owner.write_once;original_native=native.write_once;original_finish=review_commands.finish
    def write(path,*args):
        if point=='target' and path.name=='speaker_approval_target.json':raise OSError('synthetic target interruption')
        return original_write(path,*args)
    def approval_write(path,*args):
        if point=='approval_receipt' and path.name=='approval_receipt.json':raise OSError('synthetic approval receipt interruption')
        return original_native(path,*args)
    def finish(command,value):
        if point=='result' and value.get('schema_version')==owner.VERSION:raise OSError('synthetic result interruption')
        return original_finish(command,value)
    with monkeypatch.context() as fault:
        fault.setattr(__import__('speaker_fact_review_v1'),'review_speaker_facts',review)
        fault.setattr(owner,'write_once',write);fault.setattr(native,'write_once',approval_write);fault.setattr(review_commands,'finish',finish)
        response=submit(client,url,csrf,bundle);assert response.status_code==503,response.text
    pending=client.get(f'/api/review-commands/speaker/{sid}').json()['operations']
    assert len(pending)==1 and pending[0]['can_discard'] is False
    assert client.post(url+'/review-preview',headers={'X-CSRF-Token':csrf},json=body).status_code==409
    # Neither a fresh legacy context nor a different actor can steal the unfinished stage.
    assert post_review(client,url+'/persona/approve',headers={'X-CSRF-Token':csrf},json={}).status_code==409
    protected={p:p.read_bytes() for p in (settings.pipeline_root/'data/speaker_intakes'/bid/sid).rglob('*.json')}
    monkeypatch.setattr(review_commands,'_KEY',b'fresh process key')
    with TestClient(build_app(settings)) as restarted:
        login=restarted.post('/api/auth/login',json={'phone':'13800000000','password':'ReviewConsole2026!'})
        assert login.status_code==200;new_csrf=login.json()['csrf_token']
        resumed=submit(restarted,url,new_csrf,bundle);assert resumed.status_code==200,resumed.text
        stable=hashes(settings.pipeline_root)
        assert submit(restarted,url,new_csrf,bundle).status_code==200 and hashes(settings.pipeline_root)==stable
    assert all(p.read_bytes()==v for p,v in protected.items())
    assert len(list((settings.pipeline_root/'data/personas'/sid).rglob('approval_receipt.json')))==1


def test_unhandled_risk_wrong_preview_missing_explicit_approval_and_downgrade_never_write(client,settings):
    csrf,bid,sid,url,detail,body=prepare(client,settings,risky_scope=True)
    required={v['candidate_id'] for v in detail['fact_candidates'] if v['state']=='requires_review' and not v.get('default_review_selection')}
    assert required, 'The native fixture must exercise explicit expression-boundary review'
    omitted=[v for v in body['decisions'] if v['candidate_id'] not in required]
    partial=preview(client,url,csrf,{**body,'decisions':omitted});assert partial['can_submit'] is False
    before=hashes(settings.pipeline_root)
    assert submit(client,url,csrf,partial).status_code==409 and hashes(settings.pipeline_root)==before
    bundle=preview(client,url,csrf,body)
    for changes in ({'preview_sha256':'0'*64},{'actor':'forged'},{'confirmation':'save_only'}):
        assert submit(client,url,csrf,bundle,**changes).status_code in {409,422}
    assert client.post(url+'/confirm',headers={'X-CSRF-Token':csrf},json={'review_context':bundle['review_context']['token']}).status_code==422
    assert post_review(client,url+'/persona/approve',headers={'X-CSRF-Token':csrf},json={'review_context':bundle['review_context']['token']}).status_code==409
    assert post_review(client,url+'/facts/review',headers={'X-CSRF-Token':csrf},json={'review_context':bundle['review_context']['token'],'decisions':body['decisions']}).status_code==409
    assert hashes(settings.pipeline_root)==before


def test_edit_preview_is_exact_and_rejection_of_required_truth_blocks_approval(client,settings):
    csrf,bid,sid,url,detail,body=prepare(client,settings)
    target=next(v for v in detail['fact_candidates'] if v['field']=='speaker_role_facts')
    change=next(v for v in body['decisions'] if v['candidate_id']==target['candidate_id']);change.update(decision='edit',edited_value=['本人先检查毛发，再核对洗护方案'])
    bundle=preview(client,url,csrf,body);assert bundle['projection']['facts']['speaker_role_facts']==change['edited_value']
    assert submit(client,url,csrf,bundle).status_code==200
    assert resolve_persona_authority(settings,sid,'speaker').current['artifact']['facts']['speaker_role_facts']['value']==change['edited_value']


def test_csrf_actor_access_and_stale_source_cannot_approve(client,settings):
    csrf,bid,sid,url,detail,body=prepare(client,settings);bundle=preview(client,url,csrf,body);before=hashes(settings.pipeline_root)
    assert client.post(url+'/confirm',json={}).status_code in {403,422}
    assert client.post(url+'/review-preview',headers={'X-CSRF-Token':csrf},json={**body,'actor':'fake'}).status_code==422
    from app.auth_service import provision_user
    provision_user(settings.database_path,'13900000001')
    with TestClient(build_app(settings)) as other:
        login=other.post('/api/auth/login',json={'phone':'13900000001','password':'123456'});other_csrf=login.json()['csrf_token']
        changed=other.post('/api/auth/change-password',headers={'X-CSRF-Token':other_csrf},json={
            'current_password':'123456','new_password':'AnotherFixture2026!','confirm_password':'AnotherFixture2026!'})
        assert changed.status_code==200
        assert submit(other,url,other_csrf,bundle).status_code==403
    assert hashes(settings.pipeline_root)==before
    with transaction(settings.database_path) as db:db.execute("update users set status='disabled' where phone='13800000000'")
    assert submit(client,url,csrf,bundle).status_code in {401,403}
    assert hashes(settings.pipeline_root)==before


def test_stale_candidate_cannot_commit_and_context_version_cannot_be_forged(client,settings):
    csrf,bid,sid,url,detail,body=prepare(client,settings);bundle=preview(client,url,csrf,body)
    token,signature=bundle['review_context']['token'].split('.');value=json.loads(base64.urlsafe_b64decode(token));value['version']=review_commands.VERSION
    forged=base64.urlsafe_b64encode(json.dumps(value).encode()).decode()+'.'+signature
    before=hashes(settings.pipeline_root)
    assert post_review(client,url+'/persona/approve',headers={'X-CSRF-Token':csrf},json={'review_context':forged}).status_code==409
    assert hashes(settings.pipeline_root)==before
    path=settings.pipeline_root/'data/speaker_intakes'/bid/sid/detail['latest_intake_id']/'speaker_fact_candidates_v1.json'
    path.write_text(path.read_text(encoding='utf8')+'\n',encoding='utf8');before=hashes(settings.pipeline_root)
    assert submit(client,url,csrf,bundle).status_code==409 and hashes(settings.pipeline_root)==before


def test_risk_policy_retains_explicit_identity_and_expression_boundary_review():
    for field in ['public_display_name','public_role','role_scope_constraints','first_person_forbidden_claims']:
        assert owner.review_policy({'target_field':field})['default_review_selection'] is None
    assert owner.review_policy({'target_field':'speaker_role_facts','conflict_refs':['conflict']})['default_review_selection'] is None
    assert owner.review_policy({'target_field':'speaker_role_facts'})['default_review_selection']=='approve'


def test_rejecting_missing_personal_truth_cannot_bypass_native_capability_gate(client,settings):
    csrf,bid,sid,url,detail,body=prepare(client,settings)
    target=next(v['candidate_id'] for v in detail['fact_candidates'] if v['field']=='speaker_role_facts')
    next(v for v in body['decisions'] if v['candidate_id']==target)['decision']='reject'
    bundle=preview(client,url,csrf,body);assert not bundle['can_submit'] and bundle['blockers']
    before=hashes(settings.pipeline_root)
    assert submit(client,url,csrf,bundle).status_code==409 and hashes(settings.pipeline_root)==before
    assert resolve_persona_authority(settings,sid,'speaker').current is None


def test_access_is_rechecked_between_native_review_and_approval(client,settings,monkeypatch):
    csrf,bid,sid,url,detail,body=prepare(client,settings);bundle=preview(client,url,csrf,body)
    import speaker_fact_review_v1 as native
    original=native.review_speaker_facts
    def review(**kwargs):
        result=original(**kwargs)
        with transaction(settings.database_path) as db:db.execute("update users set status='disabled' where phone='13800000000'")
        return result
    monkeypatch.setattr(native,'review_speaker_facts',review)
    response=submit(client,url,csrf,bundle);assert response.status_code==403,response.text
    assert resolve_persona_authority(settings,sid,'speaker').current is None
    assert list((settings.pipeline_root/'data/speaker_intakes'/bid/sid).rglob('speaker_fact_review_v1.json'))
    assert not list((settings.pipeline_root/'data/personas'/sid).rglob('approval_receipt.json'))


def test_old_interrupted_command_recovers_under_original_contract_before_new_confirmation(client,settings,monkeypatch):
    csrf,bid,sid,url,detail,body=prepare(client,settings)
    original=review_commands.finish
    with monkeypatch.context() as fault:
        fault.setattr(review_commands,'finish',lambda *_:(_ for _ in ()).throw(OSError('legacy result interrupted')))
        with pytest.raises(OSError):post_review(client,url+'/facts/review',headers={'X-CSRF-Token':csrf},json={'decisions':body['decisions']})
    pending=client.get(f'/api/review-commands/speaker/{sid}').json()['operations'];assert len(pending)==1
    assert client.post(url+'/review-preview',headers={'X-CSRF-Token':csrf},json=body).status_code==409
    protected={p:p.read_bytes() for p in (settings.pipeline_root/'data/speaker_intakes'/bid/sid).rglob('*.json')}
    replay=client.post(pending[0]['request_path'],headers={'X-CSRF-Token':csrf},json=pending[0]['payload'])
    assert replay.status_code==200,replay.text
    assert all(p.read_bytes()==v for p,v in protected.items())
    fresh=client.get(url).json();bundle=preview(client,url,csrf,{'review_context':fresh['approval_context']['token'],'decisions':[]})
    assert submit(client,url,csrf,bundle).status_code==200


def test_explicit_business_revision_revalidation_remains_required_and_new_confirmation_preserves_R1(client,settings):
    from test_customer_speaker_revision_v1 import analyze_supplement,review_current
    csrf,bid,sid,url,detail,body=prepare(client,settings,reviewed=True);headers={'X-CSRF-Token':csrf}
    assert post_review(client,url+'/persona/approve',headers=headers,json={}).status_code==200
    old_limits={key:resolve_persona_authority(settings,sid,'speaker').current['artifact']['facts'][key]
        for key in ['role_scope_constraints','first_person_forbidden_claims']}
    protected={p:p.read_bytes() for identity in [bid,sid] for p in (settings.pipeline_root/'data/personas'/identity/'revision_0001').rglob('*.json')}
    added=client.post(f'/api/customers/{bid}/gaps/supplement',headers=headers,json={
        'answers':[{'target_gap':'additional_materials','raw_answer':'先预约，再进行真实皮肤检测'}]})
    assert added.status_code==200,added.text
    analyze_supplement(settings,added.json()['task']);review_current(client,bid,csrf)
    assert post_review(client,f'/api/customers/{bid}/persona/approve',headers=headers,json={}).status_code==200
    stale=client.get(url).json();assert stale['status']=='revalidation_required'
    assert client.post(url+'/review-preview',headers=headers,json={'review_context':stale['approval_context']['token'],'decisions':[]}).status_code==409
    evidence=stale['revalidation_evidence']
    rebound=client.post(url+'/revalidation/review',headers=headers,json={
        'confirmed':True,'business_sha256':evidence['business_sha256'],'speaker_sha256':evidence['speaker_sha256'],'note':'Explicit synthetic personal reuse review'})
    assert rebound.status_code==200,rebound.text
    fresh=client.get(url).json();assert fresh['status']=='persona_review_required'
    bundle=preview(client,url,csrf,{'review_context':fresh['approval_context']['token'],'decisions':[]})
    assert bundle['can_submit'];result=submit(client,url,csrf,bundle);assert result.status_code==200,result.text
    assert resolve_persona_authority(settings,sid,'speaker').current['revision']==2
    assert all(resolve_persona_authority(settings,sid,'speaker').current['artifact']['facts'][key]==value
        for key,value in old_limits.items()),'Explicit Business revalidation must retain confirmed expression restrictions'
    assert all(p.read_bytes()==v for p,v in protected.items())
