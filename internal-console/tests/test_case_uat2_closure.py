"""Formal HTTP/Session/Gateway/Approval tests; isolated analysis fixture only."""
import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from app import review_commands
from app.main import build_app, CaseReviewRequest
from app.case_library_access import manage_reviewer
from app.canonical_gateway import _sha256, approve_case_candidate, CanonicalOperationError
from test_case_library_security_v1 import node, ready, publish, CASE_ID
from review_protocol import historical_case_context

URL = f"/api/cases/{CASE_ID}"


def submission(node, decisions):
    c = node[1]['C'][0]
    detail = c.get(URL).json()
    return {'decision': 'approve', 'evidence_review': decisions,
            'review_context': historical_case_context(c, detail),
            'quality_decision': {**detail['quality_context'], 'decision': 'suitable', 'origin': 'human_final_confirmation'}}


def files(root):
    return {str(p.relative_to(root)): _sha256(p) for p in root.rglob('*.json')}


def interrupt(node, monkeypatch):
    _, task, _, decisions, _, _ = ready(node)
    payload = submission(node, decisions)
    c, h, _ = node[1]['C']
    with monkeypatch.context() as m:
        m.setattr(review_commands, 'finish', lambda *a: (_ for _ in ()).throw(OSError('result persistence interrupted')))
        with pytest.raises(OSError):
            c.post(URL+'/review', headers=h, json=payload)
    assert (node[0].pipeline_root/'data/cases'/CASE_ID/'approval_receipt.json').is_file()
    return task, payload


def test_rejected_terminal_read_exact_owner_reviewer_and_no_new_context(node):
    _, task, candidate, decisions, _, _ = ready(node)
    c, h, _ = node[1]['C']; a = node[1]['A'][0]; b = node[1]['B'][0]
    old = submission(node, decisions)
    r = c.post(URL+'/review', headers=h, json={**old, 'decision':'reject', 'reason':'来源准确，但没有可复用的创作结构，本次不收录。'})
    assert r.status_code == 200, r.text
    receipt = candidate.parents[2]/'human_review_decision_v1.json'
    before = receipt.read_bytes()
    for client in (a, c):
        for path in (URL, URL+f'?attempt_id={task["task_id"]}'):
            detail = client.get(path)
            assert detail.status_code == 200, detail.text
            d = detail.json()
            assert d['review']['decision']=='reject' and d['review']['reason']
            assert d['review']['reviewed_at'] and d['reviewed_by']
            assert d['review']['can_review'] is False and d['approval_context'] is None
            assert d['classification_required'] is False
    assert b.get(URL+f'?attempt_id={task["task_id"]}').status_code == 404
    mine = a.get('/api/cases?view=mine').json()['cases'][0]
    assert mine['status']=='rejected' and mine['href'].startswith('/cases/'+CASE_ID+'?attempt_id=')
    queue = c.get('/api/cases?view=review&status=rejected').json()
    assert queue['total']==1 and queue['cases'][0]['status']=='rejected'
    assert c.post(URL+'/review',headers=h,json=old).status_code==409
    assert receipt.read_bytes()==before
    # Re-login and a new application instance still read the exact terminal object.
    with TestClient(build_app(node[0])) as restarted:
        auth=restarted.post('/api/auth/login',json={'phone':'13900000003','password':'SyntheticCase2026!'}).json()
        assert auth.get('csrf_token')
        assert restarted.get(URL).json()['review']['reason']==r.json()['review']['reason']


def test_new_attempt_cannot_overwrite_or_revive_terminal(node):
    _, task, candidate, decisions, _, _ = ready(node)
    c,h,_=node[1]['C']; payload=submission(node,decisions)
    assert c.post(URL+'/review',headers=h,json={**payload,'decision':'reject','reason':'本次不收录'}).status_code==200
    old=candidate.parents[2]/'human_review_decision_v1.json'; before=old.read_bytes()
    from app.task_service import create_case_task
    new=create_case_task(node[0].database_path,case_id=CASE_ID,source_url=f'https://www.douyin.com/video/{CASE_ID}',
        created_by_user_id=1,reanalyze=True,reason='新的独立分析')
    state=node[0].pipeline_root/'data/case_analysis_attempts'/CASE_ID/new['task_id']/'case_analysis_attempt_v1.json'
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({'case_id':CASE_ID,'attempt_id':new['task_id'],'status':'running','created_at':'2099-01-01T00:00:00Z','artifacts':{}}))
    assert c.get(URL).status_code==404  # Never fall back to the old rejected candidate.
    assert c.get(URL+f'?attempt_id={task["task_id"]}').json()['review']['decision']=='reject'
    assert c.get('/api/cases?view=review').json()['total']==0
    assert old.read_bytes()==before


@pytest.mark.parametrize('change', ['missing','negative','ai','candidate','evidence','attempt'])
def test_quality_direct_api_is_explicit_bound_and_not_ai_default(node, change):
    _,_,candidate,decisions,_,_=ready(node); c,h,_=node[1]['C']
    payload=submission(node,decisions)
    if change=='missing': payload.pop('quality_decision')
    elif change=='negative': payload['quality_decision']['decision']='unsuitable'
    elif change=='ai': payload['quality_decision']['origin']='ai_suggestion'
    elif change=='candidate': payload['quality_decision']['candidate_sha256']='0'*64
    elif change=='evidence': payload['quality_decision']['evidence_sha256']={}
    else: payload['quality_decision']['attempt_id']='another-attempt'
    before=candidate.read_bytes()
    r=c.post(URL+'/review',headers=h,json=payload)
    assert r.status_code==409 and r.json()['detail']['code']=='CASE_QUALITY_DECISION_REQUIRED', r.text
    assert candidate.read_bytes()==before
    assert not (node[0].pipeline_root/'data/cases'/CASE_ID/'approval_receipt.json').exists()


def test_positive_quality_no_reason_separate_publication_and_no_production_rights(node):
    _,_,_,decisions,_,_=ready(node); c,h,_=node[1]['C']; b=node[1]['B'][0]
    payload=submission(node,decisions)
    r=c.post(URL+'/review',headers=h,json=payload)
    assert r.status_code==200,r.text
    root=node[0].pipeline_root/'data/cases'/CASE_ID
    case=json.loads((root/'case_v1.json').read_text(encoding='utf-8'))
    receipt=json.loads((root/'approval_receipt.json').read_text(encoding='utf-8'))
    quality=receipt['human_quality_decision']
    assert receipt['contract_version']=='case-human-approval-v2.0'
    assert quality==case['approval']['human_quality_decision']
    assert quality['decision']=='suitable' and quality['actor']['user_id']==3 and quality['operation_id']
    assert quality['decided_at']==receipt['approved_at'] and receipt['note']==''
    assert b.get(URL).status_code==404 and b.get('/api/cases').json()['total']==0
    assert b.get(URL+'/media').status_code==404
    assert not r.json()['case']['media_rights']['production_authorized']
    before=files(root)
    publish(node)
    assert b.get('/api/case-library/'+CASE_ID).status_code==200
    assert files(root)==before
    assert b.get('/api/case-library/'+CASE_ID+'/cover').status_code==404


def test_B_approval_committed_then_response_interrupted_recovers_original_receipt(node, monkeypatch):
    task,payload=interrupt(node,monkeypatch)
    root=node[0].pipeline_root/'data/cases'/CASE_ID; before=files(root)
    from app.database import connect
    db=connect(node[0].database_path); count=db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0];db.close()
    with TestClient(build_app(node[0])) as restarted, monkeypatch.context() as m:
        auth=restarted.post('/api/auth/login',json={'phone':'13900000003','password':'SyntheticCase2026!'}).json()
        headers={'X-CSRF-Token':auth['csrf_token']}
        m.setattr(review_commands,'_KEY',b'new process signing key')
        import app.main as main
        m.setattr(main,'approve_case_candidate',lambda *a,**k: pytest.fail('Recovery must NEVER call Approval Writer'))
        operations=restarted.get('/api/review-commands/case/'+CASE_ID).json()['operations'];assert len(operations)==1
        for _ in range(3):
            r=restarted.post(operations[0]['request_path'],headers=headers,json=operations[0]['payload'])
            assert r.status_code==200,r.text
            assert r.json()['approval_receipt_ref']['sha256']==before['approval_receipt.json']
        assert restarted.get('/api/review-commands/case/'+CASE_ID).json()['operations']==[]
    assert files(root)==before
    db=connect(node[0].database_path);assert db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]==count;db.close()


@pytest.mark.parametrize('change',['actor','intent','candidate','evidence','receipt','association','revoke','quality','attempt'])
def test_exact_recovery_rejects_mismatched_commit(node,monkeypatch,change):
    task,payload=interrupt(node,monkeypatch);settings=node[0];c,h,_=node[1]['C']
    root=settings.pipeline_root/'data/cases'/CASE_ID; before=files(root)
    if change=='actor': c,h,_=node[1]['D']
    elif change in ('intent','quality'): payload['quality_decision']['origin']='forged'
    elif change=='attempt':
        payload['review_context']=review_commands.issue(settings,'case',CASE_ID,3)['token']
    elif change=='revoke': manage_reviewer(settings,3,action='revoke',operator='trusted fixture',reason='revocation test')
    else:
        path={'candidate':settings.pipeline_root/'data/case_analysis_attempts'/CASE_ID/task['task_id']/'candidate_cases'/CASE_ID/'case_v1.json',
              'evidence':settings.pipeline_root/'data/case_analysis_attempts'/CASE_ID/task['task_id']/'case_evidence_final_review_v1.json',
              'receipt':root/'approval_receipt.json','association':root/review_commands.CASE_COMMIT_FILE}[change]
        path.write_bytes(path.read_bytes()+b' ')
        if change=='association':
            value=json.loads(path.read_text());value['intent_sha256']='0'*64;path.write_text(json.dumps(value))
    r=c.post(URL+'/review',headers=h,json=payload)
    assert r.status_code in (403,409),r.text
    assert not list((settings.pipeline_root/'data/review_operations/case'/CASE_ID).glob('*/result.json'))
    assert _sha256(root/'case_v1.json')==before['case_v1.json']


@pytest.mark.parametrize('decision',['reject','reanalyze'])
def test_terminal_reason_remains_required(node,decision):
    _,_,_,decisions,_,_=ready(node); c,h,_=node[1]['C']
    payload=submission(node,decisions);payload.update(decision=decision,reason=' ')
    r=c.post(URL+'/review',headers=h,json=payload)
    assert r.status_code==422 and r.json()['detail']['code']=='CASE_REVIEW_REASON_REQUIRED'


@pytest.mark.parametrize('change',['missing','incomplete','stale'])
def test_evidence_errors_are_business_conflicts(node,change):
    _,_,_,decisions,_,_=ready(node);c,h,_=node[1]['C'];p=submission(node,decisions)
    if change=='missing':p.pop('evidence_review')
    elif change=='stale':p['evidence_review']['candidate_sha256']='0'*64
    else:p['evidence_review']['narration_decisions']=[]
    r=c.post(URL+'/review',headers=h,json=p)
    assert r.status_code==409 and r.json()['detail']['code'].startswith('CASE_EVIDENCE_REVIEW_'), r.text


def test_gateway_and_cli_cannot_bypass_explicit_quality(node):
    import subprocess,sys
    _,_,candidate,decisions,_,_=ready(node)
    with pytest.raises(CanonicalOperationError) as exc:
        approve_case_candidate(node[0],CASE_ID,reviewer='trusted-offline-reviewer',note='',evidence_review=decisions,reviewer_user_id=3)
    assert exc.value.code=='CASE_QUALITY_DECISION_REQUIRED'
    result=subprocess.run([sys.executable,str(node[0].pipeline_root/'scripts/approve_case_v1.py'),
        '--case',str(candidate),'--reviewer','trusted-offline-reviewer'],capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==2 and 'CASE_QUALITY_DECISION_REQUIRED' in result.stdout
    assert not (candidate.parent/'approval_receipt.json').exists()


def test_another_validated_intent_or_authorized_actor_cannot_claim_commit(node,monkeypatch):
    _,_,_,decisions,_,_=ready(node);c,h,_=node[1]['C']
    first=submission(node,decisions); second=submission(node,decisions)
    review_commands.begin(node[0],'case',CASE_ID,3,second['review_context'],
        {'request_path':URL+'/review','payload':CaseReviewRequest(**second).model_dump(exclude={'review_context'},exclude_none=True)})
    with monkeypatch.context() as m:
        m.setattr(review_commands,'finish',lambda *a: (_ for _ in ()).throw(OSError('interruption')))
        with pytest.raises(OSError): c.post(URL+'/review',headers=h,json=first)
    r=c.post(URL+'/review',headers=h,json=second)
    assert r.status_code==409 and r.json()['detail']['code']=='REVIEW_COMMIT_CONFLICT'
    manage_reviewer(node[0],4,action='grant',operator='trusted fixture',reason='Second legitimate reviewer, distinct actor')
    d,hd,_=node[1]['D']
    assert d.post(URL+'/review',headers=hd,json=first).status_code==403
    assert c.post(URL+'/review',headers=h,json=first).status_code==200


def test_missing_commit_proof_and_conflicting_result_fail_closed(node,monkeypatch):
    _,payload=interrupt(node,monkeypatch);c,h,_=node[1]['C']
    root=node[0].pipeline_root/'data/cases'/CASE_ID
    binding=root/review_commands.CASE_COMMIT_FILE;data=binding.read_bytes();binding.unlink()
    r=c.post(URL+'/review',headers=h,json=payload)
    assert r.status_code==409 and r.json()['detail']['code']=='REVIEW_COMMIT_BINDING_REQUIRED'
    binding.write_bytes(data)
    pending=c.get('/api/review-commands/case/'+CASE_ID).json()['operations'][0]
    result=node[0].pipeline_root/'data/review_operations/case'/CASE_ID/pending['operation_id']/'result.json'
    result.write_text(json.dumps({'decision':'rejected'}))
    assert c.post(URL+'/review',headers=h,json=payload).status_code==409


def test_historical_approval_read_and_new_publication_preserve_old_bytes(node):
    """A synthetic legacy artifact, never a migration of real historical data."""
    _,_,_,decisions,_,_=ready(node);c,h,_=node[1]['C']
    assert c.post(URL+'/review',headers=h,json=submission(node,decisions)).status_code==200
    root=node[0].pipeline_root/'data/cases'/CASE_ID
    # Derive a separate legacy-format fixture and rebuild only its fixture hashes.
    for name in ('case_v1.json','approval_receipt.json'):
        path=root/name;value=json.loads(path.read_text(encoding='utf-8'))
        value.pop('contract_version',None);value.pop('human_quality_decision',None)
        if name=='case_v1.json':
            value['approval'].pop('contract_version');value['approval'].pop('human_quality_decision')
        else:value['case_sha256_after_approval']=_sha256(root/'case_v1.json')
        path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    # Read and publish use legacy authority, without requiring a fabricated quality decision.
    from app.canonical_gateway import _governance_companion, _approval_companion_path
    companion=_governance_companion(node[0],root/'case_v1.json')
    _approval_companion_path(node[0],CASE_ID).write_text(json.dumps(companion),encoding='utf-8')
    auth=root/'console_authorization_receipt_v1.json';value=json.loads(auth.read_text())
    value['approved_case_sha256']=_sha256(root/'case_v1.json');value['approval_receipt_sha256']=_sha256(root/'approval_receipt.json')
    auth.write_text(json.dumps(value))
    before=files(root)
    assert c.get(URL).status_code==200
    publish(node)
    assert files(root)==before
