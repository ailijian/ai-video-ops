"""Revision contract: synthetic source evidence; real authorization and Gateway."""
from pathlib import Path
import json

import pytest

from test_case_library_security_v1 import node as security_node, ready, CASE_ID
from app.case_library_access import principal, manage_reviewer
from app.canonical_gateway import _approval_candidate, CanonicalOperationError
from case_evidence_revision_v1 import (source_refs, save_revision, resolve_target,
    RevisionError, normalize_edits, root_for_candidate)
from human_review_operations_v1 import digest, file_sha
import subprocess
import os
from test_case_library_security_v1 import analyze
from app.task_service import update_task


@pytest.fixture
def node(tmp_path_factory):
    # Revision lineage has intentionally nested immutable companions. Keep test
    # storage short on Windows; the production path and contract are unchanged.
    # Choose synthetic identifiers without phone-like digit runs. The real
    # privacy scanner deliberately scans nested provenance strings; random hex
    # sometimes resembles a phone number. No Gate or source validator is mocked.
    import secrets, uuid
    serial=0
    def safe_hex(n=16):
        nonlocal serial
        serial+=1;value=serial;letters=''
        while value:
            letters='abcdef'[value%6]+letters;value//=6
        return letters.ljust(n*2,'a')
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(secrets,'token_hex',safe_hex)
        patch.setattr(uuid,'uuid4',lambda:uuid.UUID(hex=safe_hex()))
        yield from security_node.__wrapped__(tmp_path_factory.mktemp('r'))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def revision_source(node):
    _, task, candidate, _, _, video = ready(node)
    case = json.loads(candidate.read_text(encoding='utf-8'))
    root = candidate.parents[2]
    frames = [{'frame_id':f'F{i}', 'timestamp_seconds':i} for i in range(6)]
    raw = {'case_id':CASE_ID, 'duration_seconds':6, 'validation':{'passed':True},
        'speech_evidence_status':'detected', 'words':[{'word_id':'W1','start':0,'end':2,'text':'原词'}],
        'segments':[{'segment_id':'A1','start':0,'end':2,'source_text':'早上好','word_refs':['W1']}]}
    narration = {'case_id':CASE_ID, 'segments':[{**raw['segments'][0], 'reviewed_text':'早上好'}],
        'manual_review':{'required':False,'items':[]}}
    shots = {'case_id':CASE_ID, 'shots':[{'shot_id':'S1','start':0,'end':3,'boundary':{'selected_from_frame_ref':'F0','reason_type':'video_start'}},
        {'shot_id':'S2','start':3,'end':6,'boundary':{'selected_from_frame_ref':'F3','reason_type':'camera_view_change'}}]}
    for key, value in [('audio_v1',raw),('narration_review_v1',narration),('shot_boundaries',shots),
            ('visual_manifest',{'case_id':CASE_ID,'duration_seconds':6,'frames':frames}),
            ('visual_v1',{'case_id':CASE_ID,'frames':frames})]:
        path = root/'evidence'/key/(key+'.json')
        write(path,value)
        case['source_artifacts'][key]=str(path)
    case['source_evidence']['video']['sha256']=file_sha(video)
    case['source_provenance']['recorded_source_media_sha256']=file_sha(video)
    write(candidate,case)
    return task,candidate


def request(node, candidate, **changes):
    settings=node[0]
    return dict(operation_id='a'*32, actor=principal(settings,3), database_path=settings.database_path,
        expected_candidate_sha256=file_sha(candidate), expected_sources_sha256=digest(source_refs(settings.pipeline_root,candidate)),
        expected_revision_sha256=None, narration_edits=[{'segment_id':'A1','corrected_text':'早上好呀',
            'basis':'source_audio_listening','evidence_frame_refs':['F1']}], boundary_edits=[], **changes)


def save(node,task,payload):
    return save_revision(node[0].pipeline_root,CASE_ID,task['task_id'],**payload)


def test_save_is_append_only_replay_safe_and_not_approval_ready(node):
    task,candidate=revision_source(node)
    before={p:p.read_bytes() for p in candidate.parents[2].rglob('*.json')}
    payload=request(node,candidate)
    target=save(node,task,payload)
    assert target.state=='saved' and target.candidate is None
    assert target.attempt_root==candidate.parents[2]
    assert save(node,task,payload)==target
    assert len(list(target.attempt_root.glob('human_revisions/*/revision_v1.json')))==1
    assert all(p.read_bytes()==data for p,data in before.items())
    with pytest.raises(CanonicalOperationError): _approval_candidate(node[0],CASE_ID)
    with pytest.raises(RevisionError,match='等待重新校验'):
        resolve_target(node[0].pipeline_root,CASE_ID,task['task_id'],require_valid=True)


@pytest.mark.parametrize('field,value',[('actor',{'namespace':'b'*32,'user_id':3}),
    ('expected_candidate_sha256','0'*64),('expected_sources_sha256','0'*64),('expected_revision_sha256','0'*64)])
def test_actor_source_or_parent_mismatch_fails_closed(node,field,value):
    task,candidate=revision_source(node)
    payload=request(node,candidate);payload[field]=value
    with pytest.raises((RevisionError,RuntimeError)): save(node,task,payload)
    assert not list(candidate.parents[2].glob('human_revisions/*/revision_v1.json'))


def test_replay_cannot_change_actor_or_edit(node):
    task,candidate=revision_source(node);payload=request(node,candidate)
    save(node,task,payload)
    payload['narration_edits'][0]['corrected_text']='另一段无关内容'
    with pytest.raises(RevisionError) as exc: save(node,task,payload)
    assert exc.value.code=='CASE_REVISION_REPLAY_CONFLICT'


def test_revoked_reviewer_cannot_save_or_recover(node):
    task,candidate=revision_source(node);payload=request(node,candidate)
    save(node,task,payload)
    manage_reviewer(node[0],3,action='revoke',operator='offline-fixture',reason='revoke current authorization')
    with pytest.raises(RuntimeError): save(node,task,payload)


def test_unknown_segment_and_arbitrary_seconds_are_not_accepted(node):
    task,candidate=revision_source(node);payload=request(node,candidate)
    payload['narration_edits'][0]['segment_id']='not-a-real-segment'
    with pytest.raises(RevisionError): save(node,task,payload)
    payload=request(node,candidate);payload['narration_edits']=[]
    payload['boundary_edits']=[{'boundary_frame_id':'F3','target_seconds':2.2}]
    with pytest.raises(RevisionError): save(node,task,payload)


@pytest.mark.parametrize('old,new',[('F0','F1'),('F3','missing-frame'),('F3','F0')])
def test_invalid_boundary_cannot_mutate_original_timeline(node,old,new):
    task,candidate=revision_source(node);payload=request(node,candidate)
    payload['narration_edits']=[];payload['boundary_edits']=[{'boundary_frame_id':old,'target_frame_id':new}]
    with pytest.raises(RevisionError): save(node,task,payload)


def test_legal_manifest_boundary_and_text_share_one_edit(node):
    task,candidate=revision_source(node);payload=request(node,candidate)
    payload['boundary_edits']=[{'boundary_frame_id':'F3','target_frame_id':'F4'}]
    target=save(node,task,payload)
    edit=json.loads((target.revision_root/'edit_v1.json').read_text(encoding='utf-8'))
    assert edit['boundary_edits'][0]['target_seconds']==4
    assert edit['narration_edits'][0]['original']['word_refs']==['W1']
    assert root_for_candidate(candidate)==target.attempt_root


def test_terminal_attempt_and_pending_final_command_block_edits(node):
    task,candidate=revision_source(node);payload=request(node,candidate)
    final=node[0].pipeline_root/'data/review_operations/case'/CASE_ID/('b'*32)/'intent.json'
    write(final,{'intent':{'payload':{'decision':'approve'}}})
    with pytest.raises(RevisionError) as exc: save(node,task,payload)
    assert exc.value.code=='CASE_REVISION_FINAL_COMMAND_PENDING'
    write(final.with_name('result.json'),{'cancelled':True})
    state=candidate.parents[2]/'case_analysis_attempt_v1.json'
    data=json.loads(state.read_text(encoding='utf-8'));data['status']='rejected';write(state,data)
    with pytest.raises(RevisionError) as exc: save(node,task,payload)
    assert exc.value.code=='CASE_REVISION_TERMINAL'


def model_boundary(node,*arguments,expect_failure=False):
    repo=Path(__file__).resolve().parents[2]
    python=repo/'ops-pipeline/.venv/Scripts/python.exe'
    helper=repo/'ops-pipeline/tests/case_review_synthetic.py'
    environment={k:v for k,v in os.environ.items() if not k.startswith(('DEEPSEEK_','QYAPI_','AIVO_'))}
    environment.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
    result=subprocess.run([str(python),str(helper),*map(str,arguments)],capture_output=True,text=True,encoding='utf-8',env=environment,timeout=90)
    assert (result.returncode!=0) if expect_failure else result.returncode==0,result.stdout+result.stderr
    return result


def native_source(node,*,uncertain=False):
    _,task=analyze(node)
    model_boundary(node,'prepare',node[0].pipeline_root,CASE_ID,task['task_id'],*(['uncertain'] if uncertain else []))
    update_task(node[0].database_path,task['task_id'],status='awaiting_review',progress=100)
    client,headers,_=node[1]['A']
    context=client.get(f'/api/cases/{CASE_ID}/classification').json()
    result=client.post(f'/api/cases/{CASE_ID}/classification',headers=headers,json={
        'industry':'餐饮','profile':'mix','candidate_sha256':context['candidate_sha256'],
        'expected_confirmation_sha256':context['confirmation_sha256']})
    assert result.status_code==200,result.text
    return task


def final_payload(detail,explicit=None):
    from review_protocol import frozen_v11_context
    return {'decision':'approve','review_context':frozen_v11_context(detail['approval_context']['token']),
        'quality_decision':{**detail['quality_context'],'decision':'suitable','origin':'human_final_confirmation'},
        'evidence_review':{'schema_version':'case-evidence-final-review-v2.0','confirmation_mode':'final_bulk_keep',
            'scope_sha256':detail['evidence_workspace']['scope']['scope_sha256'],'explicit_keep_ids':explicit or []}}


def edit_payload(detail):
    space=detail['evidence_workspace']
    return {'review_context':detail['approval_context']['token'],'attempt_id':detail['review']['attempt_id'],
        'expected_candidate_sha256':space['candidate_sha256'],'expected_sources_sha256':space['sources_sha256'],
        'expected_revision_sha256':space['revision_sha256'],
        'narration_edits':[{'segment_id':'A1','corrected_text':'这是一条完全虚构的演示口播',
            'basis':'source_audio_listening','evidence_frame_refs':['F1']}],'boundary_edits':[]}


def test_native_ordinary_evidence_final_confirmation_has_exact_coverage(node):
    task=native_source(node)
    c,h,_=node[1]['C'];url=f'/api/cases/{CASE_ID}'
    detail=c.get(url).json();space=detail['evidence_workspace']
    assert space['state']=='original',space
    assert space['scope']['summary']=={'keep_original':3,'ordinary':3,'explicit':0,'blocked':0,'corrected_narration':0,'adjusted_boundaries':0}
    assert not list(node[0].pipeline_root.glob('data/case_analysis_attempts/*/*/final_reviews/*.json'))
    result=c.post(url+'/review',headers=h,json=final_payload(detail))
    assert result.status_code==200,result.text
    receipt=next(node[0].pipeline_root.glob('data/case_analysis_attempts/*/*/final_reviews/*.json'))
    value=json.loads(receipt.read_text(encoding='utf-8'))
    assert len(value['decisions'])==3 and all(d['origin']=='human_final_confirmation' for d in value['decisions'])
    assert node[1]['B'][0].get(url).status_code==404


def test_new_scope_cannot_downgrade_to_legacy_evidence_request(node):
    native_source(node,uncertain=True);c,h,_=node[1]['C'];url=f'/api/cases/{CASE_ID}'
    detail=c.get(url).json();evidence=detail['evidence_review']
    payload=final_payload(detail)
    payload['evidence_review']={'candidate_sha256':evidence['candidate_sha256'],
        'narration_sha256':evidence['narration_sha256'],'shot_sha256':evidence['shot_sha256'],
        'narration_decisions':[{'item_id':i['item_id'],'action':'keep'} for i in evidence['narration_items']],
        'shot_decisions':[{'item_id':i['item_id'],'action':'keep'} for i in evidence['shot_items']]}
    result=c.post(url+'/review',headers=h,json=payload)
    assert result.status_code==409 and result.json()['detail']['code']=='CASE_EVIDENCE_SCOPE_STALE'


@pytest.mark.parametrize('kind',['narration','boundary','joint'])
def test_native_revision_rebuilds_effective_candidate_and_preserves_original(node,kind):
    task=native_source(node,uncertain=kind!='boundary')
    c,h,_=node[1]['C'];url=f'/api/cases/{CASE_ID}'
    detail=c.get(url).json();space=detail['evidence_workspace']
    root=node[0].pipeline_root/'data/case_analysis_attempts'/CASE_ID/task['task_id']
    before={p:p.read_bytes() for p in root.rglob('*.json')}
    payload={'review_context':detail['approval_context']['token'],'attempt_id':task['task_id'],
        'expected_candidate_sha256':space['candidate_sha256'],'expected_sources_sha256':space['sources_sha256'],
        'expected_revision_sha256':space['revision_sha256'],
        'narration_edits':[{'segment_id':'A1','corrected_text':'这是一条完全虚构的演示口播','basis':'source_audio_listening','evidence_frame_refs':['F1']}] if kind!='boundary' else [],
        'boundary_edits':[{'boundary_frame_id':'F3','target_frame_id':'F4'}] if kind!='narration' else []}
    result=c.post(url+'/review-revisions',headers=h,json=payload)
    assert result.status_code==200,result.text
    saved=result.json();assert c.post(url+'/review-revisions',headers=h,json=payload).json()==saved
    pending=c.get(url).json();assert pending['evidence_workspace']['state']=='pending'
    assert c.post(url+'/review',headers=h,json=final_payload(detail)).status_code==409
    model_boundary(node,'derive',node[0].pipeline_root,node[0].database_path,CASE_ID,task['task_id'],saved['revision_id'],saved['build_task_id'])
    assert all(p.read_bytes()==v for p,v in before.items())
    current=c.get(url).json();assert current['evidence_workspace']['state']=='validated',current
    assert current['quality_context']['candidate_sha256']!=detail['quality_context']['candidate_sha256']
    summary=current['evidence_workspace']['scope']['summary']
    assert summary['corrected_narration']==(kind!='boundary')
    assert summary['adjusted_boundaries']==(kind!='narration')
    if kind!='boundary':
        assert current['full_breakdown']['narration']=='这是一条完全虚构的演示口播'
    # Classification remains its own source-bound Human Gate.
    classification=c.get(url+'/classification').json()
    if classification['status']!='confirmed':
        result=c.post(url+'/classification',headers=h,json={'industry':'餐饮','profile':'mix',
            'candidate_sha256':classification['candidate_sha256'],'expected_confirmation_sha256':classification['confirmation_sha256']})
        assert result.status_code==200,result.text
        current=c.get(url).json()
    result=c.post(url+'/review',headers=h,json=final_payload(current))
    assert result.status_code==200,result.text
    assert node[1]['B'][0].get(url).status_code==404


def test_http_revision_requires_current_reviewer_csrf_and_strict_fields(node):
    native_source(node);url=f'/api/cases/{CASE_ID}'
    c,h,_=node[1]['C'];payload=edit_payload(c.get(url).json())
    for name in 'ABD':
        client,headers,_=node[1][name]
        assert client.post(url+'/review-revisions',headers=headers,json=payload).status_code==403
    assert c.post(url+'/review-revisions',json=payload).status_code==403
    for key,value in [('actor',{'user_id':3}),('passed',True),('path','arbitrary.json')]:
        assert c.post(url+'/review-revisions',headers=h,json={**payload,key:value}).status_code==422
    response=c.post(url+'/review-revisions',headers=h,json=payload)
    assert response.status_code==200,response.text
    saved=response.json()
    for name in 'ABD':
        assert node[1][name][0].get(url+'/review-revisions/'+saved['revision_id'],params={'attempt_id':payload['attempt_id']}).status_code==403
    manage_reviewer(node[0],3,action='revoke',operator='fixture-maintenance',reason='test current revocation')
    assert c.post(url+'/review-revisions',headers=h,json=payload).status_code==403


def test_uncertain_evidence_cannot_be_silently_bulk_confirmed(node):
    native_source(node,uncertain=True);url=f'/api/cases/{CASE_ID}'
    c,h,_=node[1]['C'];detail=c.get(url).json()
    assert detail['evidence_workspace']['scope']['summary']['explicit']==1
    result=c.post(url+'/review',headers=h,json=final_payload(detail))
    assert result.status_code==409 and result.json()['detail']['code']=='CASE_EVIDENCE_RISK_UNRESOLVED'
    assert not list(node[0].pipeline_root.glob('data/cases/*/approval_receipt.json'))
    # The original uncommitted command must be cancelled before another action.
    pending=c.get('/api/review-commands/case/'+CASE_ID).json()['operations']
    assert len(pending)==1
    assert c.post('/api/review-commands/case/'+CASE_ID+'/'+pending[0]['operation_id']+'/cancel',headers=h).status_code==200
    detail=c.get(url).json()
    result=c.post(url+'/review',headers=h,json=final_payload(detail,['narration:A1']))
    assert result.status_code==200,result.text


def test_revision_save_response_loss_recovers_original_edit_and_single_task(node,monkeypatch):
    native_source(node);url=f'/api/cases/{CASE_ID}'
    c,h,_=node[1]['C'];payload=edit_payload(c.get(url).json())
    from app import review_commands
    with monkeypatch.context() as m:
        m.setattr(review_commands,'finish',lambda *a: (_ for _ in ()).throw(OSError('after saved edit and task')))
        with pytest.raises(OSError): c.post(url+'/review-revisions',headers=h,json=payload)
    root=node[0].pipeline_root/'data/case_analysis_attempts'/CASE_ID/payload['attempt_id']
    before={p:p.read_bytes() for p in root.rglob('*.json')}
    assert len(list(root.glob('human_revisions/*/revision_v1.json')))==1
    pending=c.get('/api/review-commands/case/'+CASE_ID).json()['operations']
    assert len(pending)==1 and pending[0]['can_discard'] is False
    from fastapi.testclient import TestClient
    from app.main import build_app
    # A new app/key/Session must recover only the exact durable operation.
    with TestClient(build_app(node[0])) as restarted:
        auth=restarted.post('/api/auth/login',json={'phone':'13900000003','password':'SyntheticCase2026!'}).json()
        response=restarted.post(pending[0]['request_path'],headers={'X-CSRF-Token':auth['csrf_token']},json=pending[0]['payload'])
        assert response.status_code==200,response.text
        assert restarted.post(pending[0]['request_path'],headers={'X-CSRF-Token':auth['csrf_token']},json=pending[0]['payload']).json()==response.json()
    assert all(p.read_bytes()==v for p,v in before.items())
    from app.database import connect
    db=connect(node[0].database_path)
    try: assert db.execute("SELECT count(*) FROM tasks WHERE json_extract(payload_json,'$.evidence_revision') IS NOT NULL").fetchone()[0]==1
    finally: db.close()


def test_v2_approval_result_interruption_restores_same_receipt(node,monkeypatch):
    native_source(node);url=f'/api/cases/{CASE_ID}'
    c,h,_=node[1]['C'];payload=final_payload(c.get(url).json())
    from app import review_commands
    with monkeypatch.context() as m:
        m.setattr(review_commands,'finish',lambda *a: (_ for _ in ()).throw(OSError('after Domain Commit')))
        with pytest.raises(OSError): c.post(url+'/review',headers=h,json=payload)
    approved=node[0].pipeline_root/'data/cases'/CASE_ID
    before={p:p.read_bytes() for p in approved.glob('*.json')}
    assert (approved/'approval_receipt.json') in before
    for _ in range(2):
        response=c.post(url+'/review',headers=h,json=payload)
        assert response.status_code==200,response.text
    assert all(p.read_bytes()==v for p,v in before.items())


def test_fake_build_task_cannot_make_saved_revision_valid(node):
    native_source(node);c,h,_=node[1]['C'];url=f'/api/cases/{CASE_ID}'
    payload=edit_payload(c.get(url).json())
    response=c.post(url+'/review-revisions',headers=h,json=payload)
    from case_evidence_revision_v1 import bind_build_execution
    with pytest.raises(RevisionError):
        bind_build_execution(node[0].pipeline_root,node[0].database_path,CASE_ID,payload['attempt_id'],response.json()['revision_id'],payload['attempt_id'])
    assert resolve_target(node[0].pipeline_root,CASE_ID,payload['attempt_id']).candidate is None


def test_failed_derivation_retries_same_task_and_never_falls_back(node):
    native_source(node);c,h,_=node[1]['C'];url=f'/api/cases/{CASE_ID}'
    old=c.get(url).json();payload=edit_payload(old)
    saved=c.post(url+'/review-revisions',headers=h,json=payload).json()
    arguments=('derive',node[0].pipeline_root,node[0].database_path,CASE_ID,payload['attempt_id'],saved['revision_id'],saved['build_task_id'])
    model_boundary(node,*arguments,'build_narration_review_v1',expect_failure=True)
    failed=c.get(url).json()['evidence_workspace']
    assert failed['state']=='failed' and not failed['can_approve']
    assert c.post(url+'/review',headers=h,json=final_payload(old)).status_code==409
    update_task(node[0].database_path,saved['build_task_id'],status='failed',error_code='SYNTHETIC_MODEL_UNAVAILABLE')
    task_url='/api/tasks/'+saved['build_task_id']
    detail=c.get(task_url)
    assert detail.status_code==200 and detail.json()['boundary_review'] is None
    from app.database import connect
    with connect(node[0].database_path) as db:
        task_count=db.execute('SELECT count(*) FROM tasks').fetchone()[0]
    resumed=c.post('/api/tasks/'+saved['build_task_id']+'/retry',headers=h)
    assert resumed.status_code==200 and resumed.json()['task']['task_id']==saved['build_task_id'],resumed.text
    assert c.post(task_url+'/retry',headers=h).status_code==409
    model_boundary(node,*arguments)
    update_task(node[0].database_path,saved['build_task_id'],status='completed',progress=100)
    assert c.get(task_url).status_code==200
    with connect(node[0].database_path) as db:
        assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==task_count
    assert c.get(url).json()['evidence_workspace']['state']=='validated'
    root=node[0].pipeline_root/'data/case_analysis_attempts'/CASE_ID/payload['attempt_id']/'human_revisions'/saved['revision_id']
    assert len(list(root.glob('r*/result.json')))==2
    assert len(list(root.glob('validation_receipt_v1.json')))==1
    assert not list(node[0].pipeline_root.glob('data/cases/*/approval_receipt.json'))


def test_privacy_risk_in_human_text_cannot_become_approved_truth(node):
    native_source(node);c,h,_=node[1]['C'];url=f'/api/cases/{CASE_ID}'
    payload=edit_payload(c.get(url).json());payload['narration_edits'][0]['corrected_text']='我的私人电话是13912345678'
    response=c.post(url+'/review-revisions',headers=h,json=payload)
    assert response.status_code==200,response.text
    saved=response.json()
    model_boundary(node,'derive',node[0].pipeline_root,node[0].database_path,CASE_ID,payload['attempt_id'],saved['revision_id'],saved['build_task_id'],expect_failure=True)
    assert c.get(url).json()['evidence_workspace']['can_approve'] is False
    assert not list(node[0].pipeline_root.glob('data/cases/*/approval_receipt.json'))
    assert not list(node[0].pipeline_root.glob('data/personas/*/*.json'))


def test_unknown_risk_is_not_reclassified_as_ordinary(node):
    task=native_source(node)
    target=resolve_target(node[0].pipeline_root,CASE_ID,task['task_id'])
    case=json.loads(target.candidate.read_text(encoding='utf-8'))
    path=Path(case['source_artifacts']['narration_review_v1'])
    narration=json.loads(path.read_text(encoding='utf-8'))
    # New synthetic model output, before review; never a real or approved record.
    narration['segments'][0]['risk_codes']=['unsupported_proof_conflict']
    write(path,narration)
    case['provenance']['narration_review_v1']['sha256']=file_sha(path)
    case['review_pending']['narration_sha256']=file_sha(path)
    write(target.candidate,case)
    c,h,_=node[1]['C'];url=f'/api/cases/{CASE_ID}'
    detail=c.get(url).json();summary=detail['evidence_workspace']['scope']['summary']
    assert summary['blocked']==1
    result=c.post(url+'/review-revisions',headers=h,json=edit_payload(detail))
    assert result.status_code==409 and result.json()['detail']['code']=='CASE_REVISION_RISK_UNRESOLVED'
    # A fresh model cannot silently wash away an unsupported original risk.
    assert not list(target.attempt_root.glob('human_revisions/*/edit_v1.json'))
    # Predictable validation errors do not consume the signed save context.
    assert c.get('/api/review-commands/case/'+CASE_ID).json()['operations']==[]
    detail=c.get(url).json()
    assert c.post(url+'/review',headers=h,json=final_payload(detail)).status_code==409


def test_invalid_edit_does_not_consume_context_or_create_intent(node):
    native_source(node);c,h,_=node[1]['C'];url=f'/api/cases/{CASE_ID}'
    payload=edit_payload(c.get(url).json())
    payload['boundary_edits']=[{'boundary_frame_id':'F3','target_frame_id':'F0'}]
    result=c.post(url+'/review-revisions',headers=h,json=payload)
    assert result.status_code==422,result.text
    assert c.get('/api/review-commands/case/'+CASE_ID).json()['operations']==[]
    payload['boundary_edits']=[]
    assert c.post(url+'/review-revisions',headers=h,json=payload).status_code==200


def test_delayed_save_result_binds_original_revision_after_a_new_head(node,monkeypatch):
    native_source(node);c,h,_=node[1]['C'];url=f'/api/cases/{CASE_ID}'
    original=edit_payload(c.get(url).json())
    from app import review_commands
    with monkeypatch.context() as m:
        m.setattr(review_commands,'finish',lambda *a: (_ for _ in ()).throw(OSError('lost first save result')))
        with pytest.raises(OSError):c.post(url+'/review-revisions',headers=h,json=original)
    pending=c.get('/api/review-commands/case/'+CASE_ID).json()['operations'][0]
    first=resolve_target(node[0].pipeline_root,CASE_ID,original['attempt_id'])
    task=json.loads((first.revision_root/'build_execution_v1.json').read_text(encoding='utf-8'))['build_task_id']
    model_boundary(node,'derive',node[0].pipeline_root,node[0].database_path,CASE_ID,original['attempt_id'],first.revision_root.name,task)
    later=edit_payload(c.get(url).json());later['narration_edits'][0]['corrected_text']='这是一条完全虚构的演示口播。'
    second=c.post(url+'/review-revisions',headers=h,json=later)
    assert second.status_code==200,second.text
    assert second.json()['revision_id']!=first.revision_root.name
    recovered=c.post(pending['request_path'],headers=h,json=pending['payload'])
    assert recovered.status_code==200,recovered.text
    assert recovered.json()['revision_id']==first.revision_root.name
    assert recovered.json()['build_task_id']==task
    assert resolve_target(node[0].pipeline_root,CASE_ID,original['attempt_id']).revision_root.name==second.json()['revision_id']
    assert len(list(first.attempt_root.glob('human_revisions/*/build_execution_v1.json')))==2


@pytest.mark.parametrize('validated',[False,True])
def test_pending_or_validated_revision_can_be_rejected_and_reopened_after_cleanup(node,monkeypatch,validated):
    native_source(node);c,h,_=node[1]['C'];url=f'/api/cases/{CASE_ID}'
    original=edit_payload(c.get(url).json())
    from app import review_commands
    if not validated:
        with monkeypatch.context() as m:
            m.setattr(review_commands,'finish',lambda *a: (_ for _ in ()).throw(OSError('saved result interrupted')))
            with pytest.raises(OSError):c.post(url+'/review-revisions',headers=h,json=original)
        first=resolve_target(node[0].pipeline_root,CASE_ID,original['attempt_id'])
        saved={'revision_id':first.revision_root.name,'build_task_id':json.loads((first.revision_root/'build_execution_v1.json').read_text(encoding='utf-8'))['build_task_id']}
    else:
        saved=c.post(url+'/review-revisions',headers=h,json=original).json()
        model_boundary(node,'derive',node[0].pipeline_root,node[0].database_path,CASE_ID,original['attempt_id'],saved['revision_id'],saved['build_task_id'])
    current=c.get(url).json()
    result=c.post(url+'/review',headers=h,json={'review_context':current['approval_context']['token'],
        'decision':'reject','reason':'保留原证据，本次不收录，不继续派生。'})
    assert result.status_code==200,result.text
    for client in (c,node[1]['A'][0]):
        history=client.get(url)
        assert history.status_code==200,history.text
        assert history.json()['review']['decision']=='reject' and history.json()['approval_context'] is None
    assert node[1]['B'][0].get(url).status_code==404
    assert c.post('/api/tasks/'+saved['build_task_id']+'/retry',headers=h).status_code==409
    # The CLI shares the terminal check, not just the hidden Console button.
    from case_evidence_revision_v1 import approval_attempt_errors
    target=resolve_target(node[0].pipeline_root,CASE_ID,original['attempt_id'])
    candidate=target.candidate or target.original_candidate
    assert 'terminal' in ' '.join(approval_attempt_errors(json.loads(candidate.read_text(encoding='utf-8')),file_sha(candidate),candidate))
    if not validated:
        recovered=c.post(url+'/review-revisions',headers=h,json=original)
        assert recovered.status_code==200,recovered.text
        assert recovered.json()['build_task_id']==saved['build_task_id']


def test_unedited_uncertainty_survives_unrelated_revision_and_new_high_confidence(node):
    task=native_source(node,uncertain=True);c,h,_=node[1]['C'];url=f'/api/cases/{CASE_ID}'
    payload=edit_payload(c.get(url).json());payload['narration_edits']=[]
    payload['boundary_edits']=[{'boundary_frame_id':'F3','target_frame_id':'F4'}]
    response=c.post(url+'/review-revisions',headers=h,json=payload)
    assert response.status_code==200,response.text
    saved=response.json()
    model_boundary(node,'derive',node[0].pipeline_root,node[0].database_path,CASE_ID,task['task_id'],saved['revision_id'],saved['build_task_id'])
    current=c.get(url).json()['evidence_workspace']['scope']
    row=next(r for r in current['items'] if r['item_id']=='narration:A1')
    assert row['mode']=='explicit' and current['summary']['explicit']==1
    assert current['summary']['corrected_narration']==0
