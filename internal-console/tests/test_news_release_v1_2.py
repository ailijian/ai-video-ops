import uuid
import pytest
from test_case_evidence_revision_v1 import node
from news_golden_support_v1_2 import prepare_news_compatibility
from test_profile_compatibility_release_v1_1 import committed_source_snapshot
from profile_compatibility_release_v1_1 import configure_runtime,effective_runtime
from profile_compatibility_release_v1_2 import binding
from profile_compatibility_contract_v1_1 import CompatibilityError
from profile_compatibility_decisions_v1_1 import decision_graph,preview,decide,target_id


def test_native_news_only_pack_verify_preflight_activate_and_withdrawal_fence(node):
    from pathlib import Path
    result=prepare_news_compatibility(node);settings,accounts,storage=node;source=settings.pipeline_root
    project=Path(__file__).resolve().parents[2]
    repo,owner=committed_source_snapshot(project,storage/'s',complete=True)
    runtime=storage/'runtime';runtime.mkdir()
    configure_runtime(runtime,source,purpose='isolated-validation',contract_version='1.2')
    package=owner.build_release(source,storage/'releases',repo,contract_version='1.2',purpose='isolated-validation')
    assert owner.verify_release(package,repo)['approved_cases']==3
    staged=owner.stage_release_v1_1(package,runtime,repo)
    activation=owner.activate_release_v1_1(runtime,repo,staged,uuid.uuid4().hex)
    active=effective_runtime(runtime)
    assert active['manifest']['profiles']==['news']
    assert active['registry']['profiles']['news']['status']=='validation_pending'
    assert active['registry']['profiles']['news']['production_eligible'] is False
    pinned=binding(active,'novel_content')
    assert effective_runtime(runtime,pinned=pinned)['binding']['activation_ref']==activation['activation_ref']
    assert owner.preflight(runtime,repo)['binding']['activation_ref']==activation['activation_ref']
    graph=decision_graph(source);target=result['targets'][0];tid=target_id(target);head=graph['heads'][tid]
    operation=uuid.uuid4().hex
    p=preview(source,settings.database_path,result['actor'],operation,[{'target_id':tid,'target':target,
        'action':'withdraw','parent':head['head'],'withdraws':head['effective'],'reason':'Native live withdrawal'}])
    decide(source,settings.database_path,result['actor'],operation,p['preview_ref']['sha256'])
    with pytest.raises(CompatibilityError):effective_runtime(runtime,pinned=pinned)
    with pytest.raises(CompatibilityError):owner.stage_release_v1_1(package,runtime,repo)
    with pytest.raises(CompatibilityError):owner.activate_release_v1_1(runtime,repo,staged,uuid.uuid4().hex)
    production=storage/'production';production.mkdir()
    with pytest.raises(CompatibilityError):configure_runtime(production,source,purpose='production',contract_version='1.2')
