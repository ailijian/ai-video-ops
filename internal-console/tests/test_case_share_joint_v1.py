"""One explicit human action; real auth/CSRF/Approval/Publication, synthetic models."""
import json
from pathlib import Path

import pytest

from test_case_evidence_revision_v1 import node, native_source
from test_case_library_security_v1 import CASE_ID, publish
from app.case_library_access import principal, manage_reviewer
from app.case_shared_display import share_preview
from app import review_commands
from human_review_operations_v1 import file_sha


def payload(detail):
    sharing=detail['share_preview']
    return {'decision':'approve','review_context':detail['approval_context']['token'],
        'quality_decision':{**detail['quality_context'],'decision':'suitable','origin':'human_final_confirmation'},
        'evidence_review':{'schema_version':'case-evidence-final-review-v2.0','confirmation_mode':'final_bulk_keep',
            'scope_sha256':detail['evidence_workspace']['scope']['scope_sha256'],'explicit_keep_ids':[]},
        'sharing_decision':{'schema_version':'case-human-display-decision-v1.0',
            'decision':'publish_exact_preview' if sharing['mode']=='approve_and_share' else 'approve_only',
            'preview_sha256':sharing['preview_sha256'],'preview':sharing['preview'],
            'blocker_sha256':sharing['blocker_sha256'],'origin':'human_joint_final_confirmation'}}


def prepared(node):
    task=native_source(node)
    c,h,_=node[1]['C'];url=f'/api/cases/{CASE_ID}'
    # Call the Owner as well as HTTP so a preparation error is not hidden by UX.
    preview=share_preview(node[0],CASE_ID,principal(node[0],3))
    detail=c.get(url).json()
    assert detail['share_preview']==preview,detail.get('share_preview_error')
    return c,h,url,payload(detail),task


def receipts(node):
    return list((node[0].pipeline_root/'data/case_governance/cases'/CASE_ID/'shared_display').glob('receipt_*.json'))


def test_S1_trusted_preview_is_read_only_and_unknown_fields_rejected(node):
    c,h,url,data,task=prepared(node)
    preview=data['sharing_decision']['preview']
    assert preview['cover']['state']=='placeholder'
    assert preview['display']['industry']=='餐饮' and preview['display']['video_type'] is None
    assert preview['display']['duration_seconds']==6
    assert set(preview['sources'])==set(preview['allowed_fields'])
    assert not receipts(node)
    assert not list(node[0].pipeline_root.glob('data/review_operations/case/*/*/intent.json'))
    for field in ('actor','reviewer_grant_ref','passed','cover','industry','allowed_fields'):
        assert c.post(url+'/share-preview',headers=h,json={field:True}).status_code==422
    assert c.post(url+'/share-preview',json={}).status_code==403
    b,hb,_=node[1]['B']
    assert b.post(url+'/share-preview',headers=hb,json={}).status_code==403


def test_S2_one_confirmation_two_receipts_and_safe_current_projection(node):
    c,h,url,data,task=prepared(node)
    result=c.post(url+'/review',headers=h,json=data)
    assert result.status_code==200,result.text
    value=result.json();assert value['sharing_state']=='approved_shared'
    execution=value['execution'];assert execution['completion']=='approved_shared'
    publication=json.loads(receipts(node)[0].read_text(encoding='utf-8'))
    assert publication['schema_version']=='case-shared-display-v1.1'
    assert publication['human_display_decision']['operation_id']==execution['operation_id']
    assert publication['approval_receipt_sha256']==execution['approval_receipt_ref']['sha256']
    assert publication['case_sha256']==execution['approved_case_ref']['sha256']
    assert publication['cover_clearance'] is None
    b,_,_=node[1]['B'];shared=b.get(url)
    assert shared.status_code==200 and shared.json()['visibility']=='shared'
    assert not any(k in shared.json() for k in ('source_url','evidence_review','submitted_by','review_media'))
    assert b.get(url+'/media').status_code==404
    assert b.get(f'/api/case-library/{CASE_ID}/cover').status_code==404
    assert c.post(url+'/review',headers=h,json=data).json()['execution']==execution
    assert len(receipts(node))==1


@pytest.mark.parametrize('change',['missing','hash','source','scope','revision','unknown','origin','mode','quality','keep','numeric_type'])
def test_S1_S2_forged_or_missing_consent_cannot_approve_or_publish(node,change):
    c,h,url,data,_=prepared(node)
    if change=='missing': data.pop('sharing_decision')
    if change=='hash': data['sharing_decision']['preview_sha256']='0'*64
    if change=='source': data['sharing_decision']['preview']['evidence_sha256']['video']='0'*64
    if change=='scope': data['evidence_review']['scope_sha256']='0'*64
    if change=='revision': data['sharing_decision']['preview']['revision_ref']={'path':'bad','sha256':'0'*64}
    if change=='unknown': data['sharing_decision']['preview']['passed']=True
    if change=='origin': data['sharing_decision']['origin']='ai_suggestion'
    if change=='mode': data['sharing_decision']['decision']='approve_only'
    if change=='numeric_type': data['sharing_decision']['preview']['reviewer_grant_ref']['user_id']=3.0
    if change=='quality': data.pop('quality_decision')
    if change=='keep': data['evidence_review']={'candidate_sha256':'0'*64,'narration_sha256':'0'*64,'shot_sha256':'0'*64,'narration_decisions':[],'shot_decisions':[]}
    result=c.post(url+'/review',headers=h,json=data)
    assert 400<=result.status_code<500,result.text
    assert not receipts(node)
    assert not (node[0].pipeline_root/'data/cases'/CASE_ID/'approval_receipt.json').exists()


def test_S1_title_edit_reissues_exact_signed_preview_and_old_source_is_stale(node):
    c,h,url,old,_=prepared(node)
    changed=c.post(url+'/share-preview',headers=h,json={'title':'过程展示审核','structure_summary':'供创作拆解参考。'})
    assert changed.status_code==200,changed.text
    new=changed.json();assert new['share_preview']['preview_sha256']!=old['sharing_decision']['preview_sha256']
    # A client cannot substitute this new content under the old signed digest.
    old['sharing_decision']['preview']=new['share_preview']['preview']
    assert c.post(url+'/review',headers=h,json=old).status_code==409
    detail=c.get(url).json();detail.update(new)
    assert c.post(url+'/review',headers=h,json=payload(detail)).status_code==200
    assert node[1]['B'][0].get(url).json()['title']=='过程展示审核'


@pytest.mark.parametrize('change',['source','privacy','preview_io'])
def test_S1_independent_failure_never_silently_becomes_approve_only(node,monkeypatch,change):
    c,h,url,data,_=prepared(node)
    if change=='source':
        candidate=node[0].pipeline_root/data['sharing_decision']['preview']['candidate_ref']['path']
        value=json.loads(candidate.read_text(encoding='utf-8'))
        value['source_provenance']['source_metadata_ref']['sha256']='0'*64
        candidate.write_text(json.dumps(value),encoding='utf-8')
    elif change=='privacy':
        response=c.post(url+'/share-preview',headers=h,json={'title':'请联系 13912345678'})
        assert response.status_code==409
        assert not receipts(node);return
    else:
        def fail(*a,**k):raise OSError('synthetic preview IO')
        monkeypatch.setattr('app.case_shared_display.share_preview',fail)
    detail=c.get(url).json()
    assert detail['share_preview'] is None and detail['share_preview_error']
    assert detail['approval_context']['sharing_mode']=='unavailable'
    assert not receipts(node)


def test_S1_true_missing_display_title_is_approve_only_not_cover_absence(node):
    c,h,url,_,_=prepared(node)
    response=c.post(url+'/share-preview',headers=h,json={'title':''})
    assert response.status_code==200,response.text
    detail=c.get(url).json();detail.update(response.json())
    assert detail['share_preview']['mode']=='approve_only'
    result=c.post(url+'/review',headers=h,json=payload(detail))
    assert result.status_code==200,result.text
    assert result.json()['execution']['completion']=='approved_only'
    assert not receipts(node) and node[1]['B'][0].get(url).status_code==404


@pytest.mark.parametrize('point',['publication_before','publication_after','result'])
def test_S3_partial_commit_recovers_only_missing_step_new_session_and_instance(node,monkeypatch,point):
    from app import case_shared_display as display
    from fastapi.testclient import TestClient
    from app.main import build_app
    c,h,url,data,_=prepared(node)
    original_publish=display.publish_joint;original_finish=review_commands.finish
    def fail_publish(*a,**k):
        if point=='publication_after':original_publish(*a,**k)
        raise OSError('synthetic publication response interruption')
    def fail_finish(*a,**k):raise OSError('synthetic command result interruption')
    if point=='result':monkeypatch.setattr(review_commands,'finish',fail_finish)
    else:monkeypatch.setattr(display,'publish_joint',fail_publish)
    if point=='result':
        with pytest.raises(OSError):c.post(url+'/review',headers=h,json=data)
    else:
        response=c.post(url+'/review',headers=h,json=data)
        assert response.status_code==503,response.text
    root=node[0].pipeline_root/'data/cases'/CASE_ID
    hashes={p.name:file_sha(p) for p in root.iterdir() if p.is_file()}
    task_count=len(c.get('/api/tasks').json()['tasks'])
    assert (root/'approval_receipt.json').exists()
    assert len(receipts(node))==(0 if point=='publication_before' else 1)
    monkeypatch.setattr(display,'publish_joint',original_publish);monkeypatch.setattr(review_commands,'finish',original_finish)
    # Durable intent recovery survives a changed process signing key and Session.
    monkeypatch.setattr(review_commands,'_KEY',b'new-instance-key-for-isolated-test')
    with TestClient(build_app(node[0])) as fresh:
        login=fresh.post('/api/auth/login',json={'phone':'13900000003','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login.json()['csrf_token']}
        pending=fresh.get(f'/api/review-commands/case/{CASE_ID}').json()['operations']
        assert len(pending)==1
        for _ in range(2):
            response=fresh.post(pending[0]['request_path'],headers=headers,json=pending[0]['payload'])
            assert response.status_code==200,response.text
            assert response.json()['sharing_state']=='approved_shared'
        assert not fresh.get(f'/api/review-commands/case/{CASE_ID}').json()['operations']
        assert len(fresh.get('/api/tasks').json()['tasks'])==task_count
    assert len(receipts(node))==1
    assert hashes=={p.name:file_sha(p) for p in root.iterdir() if p.is_file()}


def test_S3_revocation_and_regrant_do_not_resurrect_old_share_intent(node,monkeypatch):
    import app.case_shared_display as display
    c,h,url,data,_=prepared(node)
    original=display.publish_joint
    monkeypatch.setattr(display,'publish_joint',lambda *a,**k:(_ for _ in ()).throw(OSError('synthetic outage')))
    assert c.post(url+'/review',headers=h,json=data).status_code==503
    receipt=node[0].pipeline_root/'data/cases'/CASE_ID/'approval_receipt.json';before=file_sha(receipt)
    manage_reviewer(node[0],3,action='revoke',operator='synthetic-maintainer',reason='synthetic revoke')
    assert c.post(url+'/review',headers=h,json=data).status_code==403
    manage_reviewer(node[0],3,action='grant',operator='synthetic-maintainer',reason='synthetic new grant')
    monkeypatch.setattr(display,'publish_joint',original)
    response=c.post(url+'/review',headers=h,json=data)
    assert response.status_code==200,response.text
    assert response.json()['execution']['completion']=='approval_kept_share_reconfirmation_required'
    assert not receipts(node) and file_sha(receipt)==before


def test_S3_published_then_result_interrupted_then_withdraw_cannot_republish(node,monkeypatch):
    c,h,url,data,_=prepared(node);finish=review_commands.finish
    monkeypatch.setattr(review_commands,'finish',lambda *a,**k:(_ for _ in ()).throw(OSError('synthetic result outage')))
    with pytest.raises(OSError):c.post(url+'/review',headers=h,json=data)
    assert len(receipts(node))==1
    publish(node,action='withdraw')
    monkeypatch.setattr(review_commands,'finish',finish)
    response=c.post(url+'/review',headers=h,json=data)
    assert response.status_code==200,response.text
    assert response.json()['execution']['completion']=='approved_shared'  # historical execution
    assert response.json()['sharing_state']=='approved_withdrawn'  # current authoritative state
    assert c.get(url).json()['sharing_label']=='已收录，已撤回共享'
    assert '继续原操作' not in c.get(url).json()['sharing_next_action']
    assert len(receipts(node))==2
    assert node[1]['B'][0].get(url).status_code==404


@pytest.mark.parametrize('change',['actor','intent','signature'])
def test_S3_borrowed_or_changed_recovery_cannot_publish(node,monkeypatch,change):
    c,h,url,data,_=prepared(node)
    monkeypatch.setattr('app.case_shared_display.publish_joint',lambda *a,**k:(_ for _ in ()).throw(OSError('synthetic outage')))
    assert c.post(url+'/review',headers=h,json=data).status_code==503
    if change=='actor':
        a,ha,_=node[1]['A'];response=a.post(url+'/review',headers=ha,json=data)
    elif change=='intent':
        data['reason']='different intent';response=c.post(url+'/review',headers=h,json=data)
    else:
        data['review_context']=data['review_context'][:-1]+'z';response=c.post(url+'/review',headers=h,json=data)
    assert 400<=response.status_code<500,response.text
    assert not receipts(node)


def test_S3_A_failure_never_executes_B(node,monkeypatch):
    from app.canonical_gateway import CanonicalOperationError
    c,h,url,data,_=prepared(node)
    def blocked(*a,**k):raise CanonicalOperationError('CASE_APPROVAL_BLOCKED','synthetic failed Approval Gate','核对来源')
    monkeypatch.setattr('app.main.approve_case_candidate',blocked)
    monkeypatch.setattr('app.case_shared_display.publish_joint',lambda *a,**k:pytest.fail('B must not run before A'))
    assert c.post(url+'/review',headers=h,json=data).status_code==409
    assert not receipts(node)


def test_S3_changed_policy_keeps_A_and_requires_fresh_display_review(node,monkeypatch):
    import app.case_shared_display as display
    c,h,url,data,_=prepared(node);original=display.publish_joint
    monkeypatch.setattr(display,'publish_joint',lambda *a,**k:(_ for _ in ()).throw(OSError('synthetic outage')))
    assert c.post(url+'/review',headers=h,json=data).status_code==503
    receipt=node[0].pipeline_root/'data/cases'/CASE_ID/'approval_receipt.json';before=file_sha(receipt)
    monkeypatch.setattr(display,'publish_joint',original)
    monkeypatch.setattr(display,'_policy',lambda settings:{'version':'changed','validator_sha256':'0'*64})
    response=c.post(url+'/review',headers=h,json=data)
    assert response.status_code==200,response.text
    assert response.json()['execution']['completion']=='approval_kept_share_reconfirmation_required'
    assert c.get(url).json()['sharing_state']=='approved_reconfirm'
    assert not receipts(node) and file_sha(receipt)==before


@pytest.mark.parametrize('version',['human-review-command-v1.0','human-review-command-v1.1'])
def test_S1_signed_v12_cannot_be_downgraded_by_client_version(node,version):
    import base64
    c,h,url,data,_=prepared(node)
    body,signature=data['review_context'].split('.')
    value=json.loads(base64.urlsafe_b64decode(body));value['version']=version
    data['review_context']=base64.urlsafe_b64encode(json.dumps(value,sort_keys=True).encode()).decode()+'.'+signature
    data.pop('sharing_decision')
    assert c.post(url+'/review',headers=h,json=data).status_code==409
    assert not receipts(node)


def test_S1_unsupported_new_business_claim_cannot_become_display_text(node):
    c,h,url,data,_=prepared(node)
    response=c.post(url+'/share-preview',headers=h,json={'title':'未经证明的全市销量第一','structure_summary':'客户有十万家门店'})
    assert response.status_code==409,response.text
    assert not receipts(node)


def test_S3_new_postapproval_classification_source_invalidates_pending_display(node,monkeypatch):
    import app.case_shared_display as display
    c,h,url,data,_=prepared(node);original=display.publish_joint
    monkeypatch.setattr(display,'publish_joint',lambda *a,**k:(_ for _ in ()).throw(OSError('synthetic outage')))
    assert c.post(url+'/review',headers=h,json=data).status_code==503
    detail=c.get(url).json()
    changed=c.post(url+'/industry-annotation',headers=h,json={'industry':'零售',
        'approved_case_sha256':detail['approved_case_sha256'],'expected_annotation_sha256':None})
    assert changed.status_code==200,changed.text
    monkeypatch.setattr(display,'publish_joint',original)
    result=c.post(url+'/review',headers=h,json=data)
    assert result.status_code==200,result.text
    assert result.json()['execution']['completion']=='approval_kept_share_reconfirmation_required'
    assert not receipts(node)


def test_S1_pending_classification_does_not_issue_editable_or_approve_only_preview(node):
    from test_case_library_security_v1 import analyze
    from test_case_evidence_revision_v1 import model_boundary
    from app.task_service import update_task
    _,task=analyze(node)
    model_boundary(node,'prepare',node[0].pipeline_root,CASE_ID,task['task_id'])
    update_task(node[0].database_path,task['task_id'],status='awaiting_review',progress=100)
    c,h,_=node[1]['C'];url=f'/api/cases/{CASE_ID}'
    detail=c.get(url).json()
    assert detail['classification_required'] and detail['share_preview'] is None
    assert detail['approval_context']['sharing_mode']=='unavailable'
    result=c.post(url+'/share-preview',headers=h,json={'title':''})
    assert result.status_code==409 and result.json()['detail']['code']=='CASE_CLASSIFICATION_REQUIRED'
    assert not receipts(node)


def test_S1_sensitive_source_title_can_be_reduced_to_safe_excerpt_before_final_confirmation(node):
    # Synthetic acquisition input, before any Approval or Publication exists.
    # The real source, classification, privacy, signature and final Gates run.
    c,h,url,data,_=prepared(node)
    preview=data['sharing_decision']['preview']
    candidate=node[0].pipeline_root/preview['candidate_ref']['path']
    value=json.loads(candidate.read_text(encoding='utf-8'))
    metadata=node[0].repo_root/preview['sources']['title']['ref']['path']
    raw=json.loads(metadata.read_text(encoding='utf-8'))
    raw['desc']='虚构制作过程 联系13912345678'
    metadata.write_text(json.dumps(raw,ensure_ascii=False),encoding='utf-8')
    value['source_provenance']['source_metadata_ref']['sha256']=file_sha(metadata)
    candidate.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    state=c.get(url+'/classification').json()
    assert c.post(url+'/classification',headers=h,json={'industry':'餐饮','profile':'mix',
        'candidate_sha256':state['candidate_sha256'],
        'expected_confirmation_sha256':state['confirmation_sha256']}).status_code==200
    detail=c.get(url).json()
    assert detail['share_preview'] is None and '联系方式' in detail['share_preview_error']['message']
    assert detail['evidence_workspace']['can_approve'] and not receipts(node)
    assert c.post(url+'/review',headers=h,json=data).status_code==409
    fixed=c.post(url+'/share-preview',headers=h,json={'title':'虚构制作过程','structure_summary':''})
    assert fixed.status_code==200,fixed.text
    detail.update(fixed.json())
    source_sha=file_sha(metadata)
    result=c.post(url+'/review',headers=h,json=payload(detail))
    assert result.status_code==200,result.text
    assert result.json()['sharing_state']=='approved_shared'
    public=node[1]['B'][0].get(url)
    assert public.json()['title']=='虚构制作过程' and '13912345678' not in public.text
    assert file_sha(metadata)==source_sha and len(receipts(node))==1


def test_checkpoint_shared_case_does_not_grant_creative_or_media_authority(node):
    from resolve_generation_source_plan_v1 import resolve_matching_universe, SourcePlanError
    from production_profile_v1 import case_is_eligible_for_production_footage
    c, h, url, data, _ = prepared(node)
    response = c.post(url + '/review', headers=h, json=data)
    assert response.status_code == 200, response.text
    assert response.json()['sharing_state'] == 'approved_shared'
    settings = node[0]
    consumer = node[1]['B'][0]
    assert consumer.get(url).status_code == 200
    assert consumer.get(url + '/media').status_code == 404
    assert not (settings.pipeline_root / 'data/cases' / CASE_ID /
                'case_profile_compatibility_approval_v1.json').exists()
    assert not list(settings.pipeline_root.glob('data/patterns/approved/*/approval_receipt.json'))
    with pytest.raises(ValueError, match='schema'):
        case_is_eligible_for_production_footage({})
    before = {str(p): file_sha(p) for p in settings.pipeline_root.rglob('*.json')}
    with pytest.raises(SourcePlanError) as blocked:
        resolve_matching_universe(settings.pipeline_root)
    assert blocked.value.code == 'SOURCE_PLAN_AUTHORITY_MISSING'
    assert before == {str(p): file_sha(p) for p in settings.pipeline_root.rglob('*.json')}
