"""Native mixed reader integration, with independent profile Human decisions."""
import uuid
from pathlib import Path
from test_case_evidence_revision_v1 import node
from news_golden_support_v1_2 import prepare_news_compatibility,prepare_news_business
from compatibility_golden_support import prepare_native_golden
from test_profile_compatibility_release_v1_1 import committed_source_snapshot
from profile_compatibility_release_v1_1 import configure_runtime,effective_runtime
from profile_compatibility_release_v1_2 import binding


def test_independent_profiles_and_existing_mix_creation_in_new_isolated_root(node):
    from dataclasses import replace
    from fastapi.testclient import TestClient
    from app.main import build_app
    from test_profile_compatibility_golden_v1_1 import exercise_creation_tasks
    mix=prepare_native_golden(node)
    news=prepare_news_compatibility(node)
    business=prepare_news_business(node)
    settings,accounts,storage=node;root=settings.pipeline_root
    project=Path(__file__).resolve().parents[2]
    repo,owner=committed_source_snapshot(project,storage/'s',complete=True)
    configure_runtime(root,root,purpose='isolated-validation',contract_version='1.2',profiles=['mix','news'])
    package=owner.build_release(root,storage/'p',repo,contract_version='1.2',purpose='isolated-validation')
    assert owner.verify_release(package,repo)['approved_cases']==6
    staged=owner.stage_release_v1_1(package,root,repo)
    owner.activate_release_v1_1(root,repo,staged,uuid.uuid4().hex)
    active=effective_runtime(root)
    assert active['manifest']['profiles']==['mix','news']
    assert len(binding(active,'novel_content')['structural_sources'])==3
    assert {s['case_id'] for s in binding(active,'novel_content')['structural_sources']}==set(news['case_ids'])
    runtime=replace(settings,pipeline_python_executable=str(project/'ops-pipeline/.venv/Scripts/python.exe'))
    with TestClient(build_app(runtime)) as client:
        response=client.post('/api/auth/login',json={'phone':'13900000001','password':'SyntheticCase2026!'})
        assert response.status_code==200,response.text
        headers={'X-CSRF-Token':response.json()['csrf_token']}
        response=client.post('/api/create/confirm',headers=headers,json={
            'business_id':business['business_id'],'speaker_id':business['speaker_id'],'profile':'mix',
            'requested_quantity':1,'confirmed_quantity':1,'idempotency_key':'native_mixed_reader_once'})
        assert response.status_code==200,response.text
        rid=response.json()['result']['request_id']
        response=client.post('/api/create/'+rid+'/resolve-sources',headers=headers)
        assert response.status_code==200,response.text
        exercise_creation_tasks(client,headers,runtime,rid,project)
