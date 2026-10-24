"""JC-01: actual Human/Case/Type/Publication owners, synthetic model boundary."""
import copy
import json
from pathlib import Path
import pytest
from app import review_commands,case_classification as types,case_shared_display as display
from app.case_library_access import principal,manage_reviewer
from test_case_evidence_revision_v1 import node,native_source
from test_case_share_joint_v1 import payload
from test_case_library_security_v1 import CASE_ID,publish
from human_review_operations_v1 import file_sha


def typed_prepared(node,type_id='persona'):
    native_source(node)
    c,h,_=node[1]['C'];url='/api/cases/'+CASE_ID
    detail=c.get(url).json()
    confirmation={'schema_version':'case-joint-type-confirmation-v1.0','catalog':detail['video_type_context']['catalog']['ref'],
        'type_id':type_id,'other_note':'人工核对的其它结构' if type_id=='other' else '',
        'profile_conflict_resolution':'defer' if type_id is None else 'preserve_dimensions_with_reason' if type_id=='news' else 'no_conflict',
        'reason':'业务内容类型与制作方式分别核对' if type_id=='news' else '', 'explicitly_confirmed':True}
    preview=c.post(url+'/share-preview',headers=h,json={'type_confirmation':confirmation})
    assert preview.status_code==200,preview.text
    detail.update(preview.json());data=payload(detail);data['type_confirmation']=confirmation
    return c,h,url,data


def test_strict_catalog_confirmation_and_result_schema():
    catalog=json.loads(Path(types.__file__).with_name('case_video_type_catalog.json').read_text('utf8'))
    types.type_checked(catalog,'TypeCatalog')
    for bad in ['1.0-review-r2',True,1.5]:
        value=copy.deepcopy(catalog);value['version']=bad
        with pytest.raises(RuntimeError):types.type_checked(value,'TypeCatalog')
    choice={'schema_version':'case-joint-type-confirmation-v1.0','catalog':{'path':'app/case_video_type_catalog.json','sha256':'a'*64},
        'type_id':None,'other_note':'','profile_conflict_resolution':'defer','reason':'','explicitly_confirmed':True}
    types.type_checked(choice,'TypeConfirmation')
    for key,val in [('profile_conflict_resolution','not_applicable'),('type_id',42),('explicitly_confirmed',False)]:
        bad={**choice,key:val}
        with pytest.raises(RuntimeError):types.type_checked(bad,'TypeConfirmation')


@pytest.mark.parametrize('type_id',['persona',None,'other','news'])
def test_one_final_operation_three_real_records_and_safe_shared_type(node,type_id):
    c,h,url,data=typed_prepared(node,type_id)
    response=c.post(url+'/review',headers=h,json=data)
    assert response.status_code==200,response.text
    result=response.json();execution=result['execution']
    assert execution['completion']=='approved_shared'
    assert result['shared_display']['video_type']==type_id
    assert result['shared_display']['cover_url'] is None
    root=node[0].pipeline_root
    records=[execution[k] for k in ['approval_receipt_ref','type_decision_ref','publication_receipt_ref']]
    assert len({v['path'] for v in records})==3
    for ref in records:assert file_sha(root/ref['path'])==ref['sha256']
    t=json.loads((root/execution['type_decision_ref']['path']).read_text('utf8'))
    assert t['operation_id']=='type_'+execution['operation_id'] and t['human_operation_id']==execution['operation_id']
    assert t['source_snapshot']['profile']=='mix'
    assert t['case_source']['sha256']==execution['approved_case_ref']['sha256']
    b,_,_=node[1]['B'];shared=b.get(url)
    assert shared.status_code==200 and shared.json()['video_type']==type_id
    assert 'other_note' not in shared.text and 'type_decision_ref' not in shared.text
    assert c.post(url+'/review',headers=h,json=data).json()['execution']==execution
    assert len(types.type_history(node[0],CASE_ID))==1 and len(display._history(node[0],CASE_ID))==1
    assert not (root/'data/patterns/approved').exists()


@pytest.mark.parametrize('point',['type_before','type_after','publication_before','publication_after','result'])
def test_joint_failure_recovers_only_missing_stage(node,monkeypatch,point):
    c,h,url,data=typed_prepared(node)
    apply=types.apply_joint_type;publication=display.publish_joint;finish=review_commands.finish
    def fail_type(*a,**kw):
        if point=='type_after':apply(*a,**kw)
        raise OSError('fictional type interruption')
    def fail_publication(*a,**kw):
        if point=='publication_after':publication(*a,**kw)
        raise OSError('fictional publication interruption')
    if point.startswith('type_'):monkeypatch.setattr(types,'apply_joint_type',fail_type)
    elif point.startswith('publication_'):monkeypatch.setattr(display,'publish_joint',fail_publication)
    else:monkeypatch.setattr(review_commands,'finish',lambda *a,**kw:(_ for _ in ()).throw(OSError('fictional result interruption')))
    if point=='result':
        with pytest.raises(OSError):c.post(url+'/review',headers=h,json=data)
    else:
        first=c.post(url+'/review',headers=h,json=data)
        assert first.status_code==503,first.text
    canonical=node[0].pipeline_root/'data/cases'/CASE_ID
    before={p.name:file_sha(p) for p in canonical.iterdir() if p.is_file()}
    monkeypatch.setattr(types,'apply_joint_type',apply);monkeypatch.setattr(display,'publish_joint',publication);monkeypatch.setattr(review_commands,'finish',finish)
    monkeypatch.setattr(review_commands,'_KEY',b'changed-process-key-only-fictional')
    c.post('/api/auth/logout',headers=h)
    login=c.post('/api/auth/login',json={'phone':'13900000003','password':'SyntheticCase2026!'})
    h={'X-CSRF-Token':login.json()['csrf_token']}
    pending=c.get('/api/review-commands/case/'+CASE_ID).json()['operations']
    assert len(pending)==1
    response=c.post(url+'/review',headers=h,json=pending[0]['payload'])
    assert response.status_code==200,response.text
    assert response.json()['execution']['completion']=='approved_shared'
    assert before=={p.name:file_sha(p) for p in canonical.iterdir() if p.is_file()}
    assert len(types.type_history(node[0],CASE_ID))==1 and len(display._history(node[0],CASE_ID))==1


def test_type_withdraw_hides_typed_projection_without_reviving_legacy(node):
    c,h,url,data=typed_prepared(node)
    response=c.post(url+'/review',headers=h,json=data);assert response.status_code==200,response.text
    result=response.json();t=result['execution']['type_decision_ref']
    request={'operation_id':'type_withdraw_'+'e'*32,'action':'revoke_type','confirmation':None,
        'approved_case_sha256':result['execution']['approved_case_ref']['sha256'],
        'approval_receipt_sha256':result['execution']['approval_receipt_ref']['sha256'],'expected_parent_sha256':t['sha256']}
    r=c.post(url+'/type-decisions',headers=h,json=request);assert r.status_code==200,r.text
    b,_,_=node[1]['B']
    assert b.get(url).status_code==404
    assert b.get('/api/cases?search='+CASE_ID).json()['total']==0
    assert c.post(url+'/review',headers=h,json=data).status_code==200
    assert b.get(url).status_code==404 and len(display._history(node[0],CASE_ID))==1
    assert c.post(url+'/type-decisions',headers=h,json=request).json()==r.json()


def test_historical_type_change_needs_independent_publication_and_replay_never_revives(node):
    c,h,url,data=typed_prepared(node)
    response=c.post(url+'/review',headers=h,json=data);assert response.status_code==200,response.text
    result=response.json();e=result['execution'];confirmation=copy.deepcopy(data['type_confirmation']);confirmation['type_id']='story'
    changed=c.post(url+'/type-decisions',headers=h,json={'operation_id':'type_'+'f'*32,'action':'confirm_type','confirmation':confirmation,
        'approved_case_sha256':e['approved_case_ref']['sha256'],'approval_receipt_sha256':e['approval_receipt_ref']['sha256'],
        'expected_parent_sha256':e['type_decision_ref']['sha256']})
    assert changed.status_code==200,changed.text
    b,_,_=node[1]['B'];assert b.get(url).status_code==404
    context=c.get(url).json()['publication_context']
    publish_input={'action':'publish','title':'独立人工核对的结构参考','structure_summary':'仅整理镜头结构。',
        'approved_case_sha256':e['approved_case_ref']['sha256'],'approval_receipt_sha256':e['approval_receipt_ref']['sha256'],
        'expected_display_receipt_sha256':context['display_receipt_sha256'],'publication_operation_id':'pub_'+'f'*32,
        'expected_type_decision_sha256':changed.json()['sha256']}
    publication=c.post(url+'/publication',headers=h,json=publish_input);assert publication.status_code==200,publication.text
    assert b.get(url).json()['video_type']=='story'
    assert c.post(url+'/publication',headers=h,json=publish_input).status_code==200
    assert len(display._history(node[0],CASE_ID))==2
    publish(node,action='withdraw')
    assert c.post(url+'/publication',headers=h,json=publish_input).status_code==200
    assert b.get(url).status_code==404 and len(display._history(node[0],CASE_ID))==3


def test_reviewer_revocation_after_approval_preserves_case_without_type_or_share(node,monkeypatch):
    c,h,url,data=typed_prepared(node);original=types.apply_joint_type
    monkeypatch.setattr(types,'apply_joint_type',lambda *a,**k:(_ for _ in ()).throw(OSError('fictional stage gap')))
    assert c.post(url+'/review',headers=h,json=data).status_code==503
    canonical=node[0].pipeline_root/'data/cases'/CASE_ID/'approval_receipt.json';before=file_sha(canonical)
    manage_reviewer(node[0],3,action='revoke',operator='fictional-maintainer',reason='test current permission')
    assert c.post(url+'/review',headers=h,json=data).status_code==403
    manage_reviewer(node[0],3,action='grant',operator='fictional-maintainer',reason='new grant must not borrow old scope')
    monkeypatch.setattr(types,'apply_joint_type',original)
    result=c.post(url+'/review',headers=h,json=data)
    assert result.status_code==200,result.text
    assert result.json()['execution']['completion']=='approval_kept_type_reconfirmation_required'
    assert file_sha(canonical)==before and not types.type_history(node[0],CASE_ID)
    assert node[1]['B'][0].get(url).status_code==404


@pytest.mark.parametrize('field',['type_decision_ref','publication_receipt_ref','approval_receipt_ref','completion','operation_id'])
def test_schema_and_semantic_result_invariants_require_actual_independent_receipts(node,field):
    c,h,url,data=typed_prepared(node);response=c.post(url+'/review',headers=h,json=data)
    assert response.status_code==200,response.text
    e=response.json()['execution'];directory=node[0].pipeline_root/'data/review_operations/case'/CASE_ID/e['operation_id']
    saved=json.loads((directory/'intent.json').read_text('utf8'))
    command={'context':saved['context'],'directory':directory,'result':e,'at':saved['at']}
    approved=review_commands.committed_case_result(node[0],command)
    bad=copy.deepcopy(e)
    if field.endswith('_ref'):bad[field]=None
    elif field=='completion':bad[field]='approved_only'
    else:bad[field]='a'*32 if e[field]!='a'*32 else 'b'*32
    with pytest.raises(RuntimeError):review_commands.validate_typed_result(node[0],{**command,'result':bad},approved)


def test_case_source_change_blocks_continuation_and_failed_eligibility_does_not_block_withdraw(node):
    c,h,url,data=typed_prepared(node);response=c.post(url+'/review',headers=h,json=data)
    assert response.status_code==200,response.text
    e=response.json()['execution'];base=node[0].pipeline_root
    preview=data['sharing_decision']['preview'];metadata=base.parent/preview['sources']['title']['ref']['path']
    metadata.write_bytes(metadata.read_bytes()+b' ')
    assert node[1]['B'][0].get(url).status_code==404
    assert c.post(url+'/review',headers=h,json=data).status_code in {409,503}
    context=display.publication_context(node[0],CASE_ID)
    withdraw=context.get('withdraw_context') or context
    result=c.post(url+'/publication',headers=h,json={'action':'withdraw','approved_case_sha256':withdraw['approved_case_sha256'],
        'approval_receipt_sha256':withdraw['approval_receipt_sha256'],'expected_display_receipt_sha256':withdraw['display_receipt_sha256']})
    assert result.status_code==200,result.text
    assert display._history(node[0],CASE_ID)[-1][0]['action']=='withdraw'


def test_legacy_publication_bytes_survive_typed_change_and_withdrawal(node):
    from test_case_share_joint_v1 import prepared
    c,h,url,data,_=prepared(node)
    old=c.post(url+'/review',headers=h,json=data)
    assert old.status_code==200,old.text
    publish(node)  # Original standalone v1.0 follows the joint v1.1.
    history=display._history(node[0],CASE_ID)
    assert {v['schema_version'] for v,_ in history}=={'case-shared-display-v1.0','case-shared-display-v1.1'}
    original={p:p.read_bytes() for p in display._root(node[0],CASE_ID).glob('receipt_*.json')}
    detail=c.get(url).json();e=old.json()['execution']
    choice={'schema_version':'case-joint-type-confirmation-v1.0','catalog':detail['video_type_context']['catalog']['ref'],
        'type_id':'persona','other_note':'','profile_conflict_resolution':'no_conflict','reason':'','explicitly_confirmed':True}
    changed=c.post(url+'/type-decisions',headers=h,json={'operation_id':'type_'+'c'*32,'action':'confirm_type','confirmation':choice,
        'approved_case_sha256':e['approved_case_ref']['sha256'],'approval_receipt_sha256':e['approval_receipt_ref']['sha256'],
        'expected_parent_sha256':None})
    assert changed.status_code==200,changed.text
    context=c.get(url).json()['publication_context']
    sent=c.post(url+'/publication',headers=h,json={'action':'publish','title':'安全历史结构参考','structure_summary':'人工核对结构。',
        'approved_case_sha256':e['approved_case_ref']['sha256'],'approval_receipt_sha256':e['approval_receipt_ref']['sha256'],
        'expected_display_receipt_sha256':context['display_receipt_sha256'],'publication_operation_id':'pub_'+'c'*32,
        'expected_type_decision_sha256':changed.json()['sha256']})
    assert sent.status_code==200,sent.text
    assert node[1]['B'][0].get(url).json()['video_type']=='persona'
    publish(node,action='withdraw')
    assert node[1]['B'][0].get(url).status_code==404
    assert original=={p:p.read_bytes() for p in original}
    assert c.post(url+'/review',headers=h,json=data).status_code==200
    assert node[1]['B'][0].get(url).status_code==404


@pytest.mark.parametrize('change',['unknown_type','other_whitespace','stale_catalog','conflict_without_reason','bad_null','schema_version'])
def test_type_preview_rejects_unconfirmed_or_stale_choices_without_any_approval(node,change):
    c,h,url,data=typed_prepared(node);choice=copy.deepcopy(data['type_confirmation'])
    if change=='unknown_type':choice['type_id']='forged_type'
    elif change=='other_whitespace':choice.update(type_id='other',other_note='   ')
    elif change=='stale_catalog':choice['catalog']['sha256']='f'*64
    elif change=='conflict_without_reason':choice.update(type_id='news',profile_conflict_resolution='preserve_dimensions_with_reason',reason='  ')
    elif change=='bad_null':choice.update(type_id=None,profile_conflict_resolution='no_conflict')
    else:choice['schema_version']='case-joint-type-confirmation-v999'
    result=c.post(url+'/share-preview',headers=h,json={'type_confirmation':choice})
    assert 400<=result.status_code<500,result.text
    assert not (node[0].pipeline_root/'data/cases'/CASE_ID/'approval_receipt.json').exists()
    assert not types.type_history(node[0],CASE_ID) and not display._history(node[0],CASE_ID)


def test_standalone_type_payload_conflict_stale_parent_and_private_permissions(node):
    c,h,url,data=typed_prepared(node);r=c.post(url+'/review',headers=h,json=data);assert r.status_code==200,r.text
    e=r.json()['execution'];choice=copy.deepcopy(data['type_confirmation']);choice['type_id']='story'
    p={'operation_id':'type_'+'d'*32,'action':'confirm_type','confirmation':choice,
        'approved_case_sha256':e['approved_case_ref']['sha256'],'approval_receipt_sha256':e['approval_receipt_ref']['sha256'],
        'expected_parent_sha256':e['type_decision_ref']['sha256']}
    b,bh,_=node[1]['B'];assert b.post(url+'/type-decisions',headers=bh,json=p).status_code in {403,404}
    assert c.post(url+'/type-decisions',headers=h,json=p).status_code==200
    changed=copy.deepcopy(p);changed['confirmation']['type_id']='conversion'
    assert c.post(url+'/type-decisions',headers=h,json=changed).status_code==409
    changed['operation_id']='type_'+'b'*32
    assert c.post(url+'/type-decisions',headers=h,json=changed).status_code==409
    assert len(types.type_history(node[0],CASE_ID))==2
    assert b.get(url).status_code==404


def test_corrupted_typed_history_never_falls_back_to_a_legacy_projection(node):
    c,h,url,data=typed_prepared(node);r=c.post(url+'/review',headers=h,json=data);assert r.status_code==200,r.text
    path=node[0].pipeline_root/r.json()['execution']['type_decision_ref']['path']
    original=path.read_bytes();case=node[0].pipeline_root/'data/cases'/CASE_ID
    stable={p:p.read_bytes() for p in case.iterdir() if p.is_file()}
    damaged=json.loads(original);damaged['parent_decision_sha256']='f'*64
    path.write_text(json.dumps(damaged),'utf8')
    try:
        assert node[1]['B'][0].get(url).status_code==404
        assert node[1]['B'][0].get('/api/cases?view=shared').json()['total']==0
        with pytest.raises(RuntimeError):types.type_history(node[0],CASE_ID)
    finally:path.write_bytes(original)
    assert stable=={p:p.read_bytes() for p in stable}
    assert node[1]['B'][0].get(url).json()['video_type']=='persona'
