"""Read projection unit contracts. Stubs below are not Native approval evidence."""
import copy
import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import creative_capacity_read_v1 as subject


@pytest.fixture
def readers(monkeypatch):
    state={'news_error':None,'style_error':None}
    business={'artifact':{} }; speaker={'artifact':{}}
    ledger={'entries':[{'business_id':'customer_a','content_id':'c1','status':'exported','title':'已审核标题'}]}
    binding={'structural_sources':[1,2,3]}
    catalog={'styles':[{'style_id':s,'style_version':'1','release_ref':{'sha256':'a'*64}} for s in ('persona','story','conversion')]}
    monkeypatch.setattr(subject,'basis',lambda *a:(copy.deepcopy(state),business,speaker,ledger,[],binding,catalog))
    native={'schema_version':'novel-news-opportunity-projection-v1.0','business_id':'customer_a','speaker_id':'speaker_a',
        'opportunities':[{'concept_id':'n1','fact_atom_refs':['pricing_facts::a'],'novelty_status':'novel','production_feasibility':{'status':'supported'}},
            {'concept_id':'n2','novelty_status':'already_communicated'},{'concept_id':'n3','novelty_status':'already_communicated'}]}
    monkeypatch.setattr(subject,'project_novel_news_opportunities',lambda **kw:copy.deepcopy(native))
    monkeypatch.setattr(subject,'preview_news_delivery',lambda **kw:{'schema_version':'news-delivery-preview-v1.0','business_id':'customer_a','speaker_id':'speaker_a','eligible_sources':[],'already_presented_sources':[{'source_content_id':'c1','presentation_count':1}]})
    monkeypatch.setattr(subject,'pending_source_ids',lambda *a:set())
    monkeypatch.setattr(subject,'build_recommendation',lambda **kw:{'status':'supported'})
    monkeypatch.setattr(subject,'validate_style_facts',lambda *a:None)
    return state,native,ledger


def read(): return subject.read_inventory(pipeline_root='.',business_id='customer_a',speaker_id='speaker_a',novel_target=10,authorization_scope_sha256='a'*64)


def test_counts_do_not_add_structures_or_repurpose(readers):
    value=read()
    assert value['new_semantic_inventory']['qualified_count']==1
    assert value['target_gap']['novel_shortfall']==9
    assert value['new_expression_inventory']['qualified_source_count']==0
    assert value['new_semantic_inventory']['opportunities'][0]['fact_atom_refs']==['pricing_facts::a']
    assert value['authority']['actual_deliverable_total'] is None
    assert not value['authority']['authorizes_execution']
    assert all(s.get('qualified_topic_count') is None for s in value['structure_qualification'])


def test_pending_not_released(readers):
    readers[1]['opportunities'][0]['novelty_status']='reserved'
    value=read()
    assert value['new_semantic_inventory']['qualified_count']==0
    assert any(r['code']=='PENDING_NATIVE_RESERVATION' for r in value['target_gap']['diagnostic_reasons'])
    assert value['authority']['reservation_released'] is False


def test_reader_failure_is_unknown_not_zero(readers,monkeypatch):
    monkeypatch.setattr(subject,'project_novel_news_opportunities',lambda **kw:(_ for _ in ()).throw(RuntimeError('private path should not escape')))
    value=read()
    assert value['new_semantic_inventory']['qualified_count'] is None
    assert value['target_gap']['novel_shortfall'] is None
    assert 'private path' not in str(value)


def test_scope_mismatch_fails_closed(readers):
    readers[1]['business_id']='customer_foreign'
    with pytest.raises(subject.CapacityReadError,match='SCOPE_OR_VERSION'): read()


def test_foreign_history_never_returned(readers):
    readers[2]['entries'][0]['business_id']='customer_foreign'
    with pytest.raises(subject.CapacityReadError,match='LEDGER_SCOPE'): read()


def test_changed_source_requires_fresh_read(readers,monkeypatch):
    original=subject.basis; calls=[]
    def changed(*args):
        values=list(original(*args));calls.append(1)
        if len(calls)>1: values[0]['ledger_sha256']='changed'
        return values
    monkeypatch.setattr(subject,'basis',changed)
    with pytest.raises(subject.CapacityReadError,match='SOURCE_CHANGED'): read()


def test_missing_structure_not_granted(readers,monkeypatch):
    original=subject.basis
    def missing(*args):
        values=list(original(*args));values[0]['news_error']='RELEASE_MISSING';values[0]['style_error']='STYLE_SCOPE_MISSING';values[-2:]=[None,None];return values
    monkeypatch.setattr(subject,'basis',missing)
    assert all(s['structure_status']=='blocked' for s in read()['structure_qualification'])


@pytest.mark.parametrize('target',[True,-1,41,1.2])
def test_target_contract(target):
    with pytest.raises(subject.CapacityReadError,match='TARGET_INVALID'):
        subject.read_inventory(pipeline_root='.',business_id='customer_a',speaker_id='speaker_a',novel_target=target,authorization_scope_sha256='a'*64)
