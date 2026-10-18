"""Progress reads reuse exact commit proof and never resume a pending command."""
import pytest

from test_case_evidence_revision_v1 import node
from test_case_share_joint_v1 import prepared, receipts
from test_case_library_security_v1 import CASE_ID, publish
from app import review_commands
from app.case_library_access import manage_reviewer
from human_review_operations_v1 import file_sha


def snapshot(node):
    return {str(p.relative_to(node[0].pipeline_root)):file_sha(p)
            for p in node[0].pipeline_root.rglob('*.json')}


@pytest.mark.parametrize('point', ['publication', 'result', 'withdrawn'])
def test_pending_progress_is_exact_read_only_and_stage_specific(node, monkeypatch, point):
    c,h,url,data,_=prepared(node)
    if point=='publication':
        monkeypatch.setattr('app.case_shared_display.publish_joint',lambda *a,**k:(_ for _ in ()).throw(OSError('isolated outage')))
        assert c.post(url+'/review',headers=h,json=data).status_code==503
    else:
        monkeypatch.setattr(review_commands,'finish',lambda *a,**k:(_ for _ in ()).throw(OSError('isolated result outage')))
        with pytest.raises(OSError):c.post(url+'/review',headers=h,json=data)
        if point=='withdrawn': publish(node,action='withdraw')
    before=snapshot(node)
    for _ in range(2):
        response=c.get(f'/api/review-commands/case/{CASE_ID}')
        assert response.status_code==200,response.text
        items=response.json()['operations'];assert len(items)==1
        progress=items[0]['progress']
        assert progress['stage']==('publication_pending' if point=='publication' else 'result_pending')
        assert progress['sharing_state']=={'publication':'approved_only','result':'approved_shared','withdrawn':'approved_withdrawn'}[point]
        assert progress['attempt_id']==c.get(url).json()['review']['attempt_id']
        assert items[0]['can_discard'] is False
    assert snapshot(node)==before
    assert len(receipts(node))=={'publication':0,'result':1,'withdrawn':2}[point]
    for role in ('A','B','D'):
        assert node[1][role][0].get(f'/api/review-commands/case/{CASE_ID}').json()['operations']==[]


@pytest.mark.parametrize('change', ['grant', 'candidate', 'binding'])
def test_changed_proof_is_not_presented_as_share_retry(node,monkeypatch,change):
    import json
    c,h,url,data,_=prepared(node)
    monkeypatch.setattr('app.case_shared_display.publish_joint',lambda *a,**k:(_ for _ in ()).throw(OSError('isolated outage')))
    failed=c.post(url+'/review',headers=h,json=data)
    assert failed.status_code==503,failed.text
    if change=='grant':
        manage_reviewer(node[0],3,action='revoke',operator='isolated-review',reason='isolated revoke')
        assert c.get(f'/api/review-commands/case/{CASE_ID}').json()['operations']==[]
        manage_reviewer(node[0],3,action='grant',operator='isolated-review',reason='isolated new grant')
    else:
        path=(node[0].pipeline_root/data['sharing_decision']['preview']['candidate_ref']['path'] if change=='candidate'
              else node[0].pipeline_root/'data/cases'/CASE_ID/'console_review_command_v1.json')
        value=json.loads(path.read_text())
        if change=='candidate':value['isolated_tamper']=True
        else:value['intent_sha256']='0'*64
        path.write_text(json.dumps(value),encoding='utf-8')
    before=snapshot(node)
    result=c.get(f'/api/review-commands/case/{CASE_ID}')
    assert result.status_code==200,result.text
    assert result.json()['operations'][0]['progress']['stage']=='recheck_required'
    assert snapshot(node)==before and len(receipts(node))==0


def test_progress_lookup_never_invokes_a_terminal_writer(node,monkeypatch):
    c,h,url,data,_=prepared(node)
    monkeypatch.setattr('app.case_shared_display.publish_joint',lambda *a,**k:(_ for _ in ()).throw(OSError('isolated outage')))
    failed=c.post(url+'/review',headers=h,json=data)
    assert failed.status_code==503,failed.text
    def forbidden(*a,**k):raise AssertionError('GET must not write a terminal result')
    monkeypatch.setattr(review_commands,'finish',forbidden)
    for _ in range(2):
        assert c.get(f'/api/review-commands/case/{CASE_ID}').json()['operations'][0]['progress']['stage']=='publication_pending'
