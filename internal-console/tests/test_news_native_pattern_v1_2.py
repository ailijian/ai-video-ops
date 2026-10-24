from test_case_evidence_revision_v1 import node
from news_golden_support_v1_2 import prepare_news_pattern
from profile_compatibility_decisions_v1_1 import read
from news_golden_support_v1_2 import prepare_news_compatibility


def test_new_native_case_research_candidate_and_trusted_pattern(node):
    result=prepare_news_pattern(node);root=node[0].pipeline_root
    receipt=read(root/result['pattern_approval_ref']['path'])
    assert receipt['schema_version']=='pattern-approval-receipt-v1.1'
    assert receipt['actor']==result['actor'] and receipt['authorization']['capability']=='news_pattern_reviewer'
    assert sorted(x['case_id'] for x in receipt['supporting_cases'])==result['case_ids']
    assert read(root/result['research_ref']['path'])['decision']=='approve_research_comparison'
    assert not list(root.glob('data/production_profiles/compatibility_v1_1/decisions/*.json'))


def test_independent_native_news_compatibility_decision_and_withdrawal(node):
    import uuid
    from profile_compatibility_decisions_v1_1 import decision_graph,target_id,preview,decide
    from profile_compatibility_contract_v1_1 import CompatibilityError
    import pytest
    result=prepare_news_compatibility(node);settings=node[0];root=settings.pipeline_root
    receipt=result['compatibility']['receipt']
    assert receipt['schema_version']=='production-profile-compatibility-approval-v1.2'
    assert receipt['authorization']['capability']=='news_profile_compatibility_reviewer'
    graph=decision_graph(root,check_sources=True)
    assert len(graph['heads'])==3 and all(x['effective'] for x in graph['heads'].values())
    target=result['targets'][0];tid=target_id(target);head=graph['heads'][tid]
    decisions=[{'target_id':tid,'target':target,'action':'withdraw','parent':head['head'],
        'withdraws':head['effective'],'reason':'Explicit native withdrawal test'}]
    operation=uuid.uuid4().hex
    p=preview(root,settings.database_path,result['actor'],operation,decisions)
    withdrawn=decide(root,settings.database_path,result['actor'],operation,p['preview_ref']['sha256'])
    graph=decision_graph(root)
    assert graph['heads'][tid]['effective'] is None
    assert sum(x['effective'] is not None for x in graph['heads'].values())==2
    original=result['compatibility']['receipt']
    with pytest.raises(CompatibilityError):
        decide(root,settings.database_path,result['actor'],original['operation_id'],original['preview_ref']['sha256'])
