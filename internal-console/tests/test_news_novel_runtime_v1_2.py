"""Actual isolated News qualification using Native sources and Human gates."""
import uuid
from pathlib import Path
from dataclasses import replace
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from news_golden_support_v1_2 import prepare_news_compatibility,prepare_news_business
from test_profile_compatibility_release_v1_1 import committed_source_snapshot
from profile_compatibility_release_v1_1 import configure_runtime
from profile_compatibility_decisions_v1_1 import read
from app.main import build_app
from app.background_task_service import BackgroundTaskRunner
from app.task_service import get_task


def native_news_runtime(node,*,mixed=False):
    if mixed:
        from compatibility_golden_support import prepare_native_golden
        prepare_native_golden(node)
    news=prepare_news_compatibility(node)
    business=prepare_news_business(node)
    settings,accounts,storage=node;root=settings.pipeline_root
    project=Path(__file__).resolve().parents[2]
    repo,owner=committed_source_snapshot(project,storage/'s',complete=True)
    configure_runtime(root,root,purpose='isolated-validation',contract_version='1.2',
        profiles=['mix','news'] if mixed else ['news'])
    package=owner.build_release(root,storage/'p',repo,contract_version='1.2',purpose='isolated-validation')
    owner.verify_release(package,repo)
    staged=owner.stage_release_v1_1(package,root,repo)
    owner.activate_release_v1_1(root,repo,staged,uuid.uuid4().hex)
    runtime=replace(settings,pipeline_python_executable=str(project/'ops-pipeline/.venv/Scripts/python.exe'),
        novel_news_rollout='validation',novel_news_validation_phones=('13900000001',))
    return runtime,business,news,repo,owner


def test_native_novel_qualification_request_review_export_closure(node,monkeypatch):
    import subprocess
    original_run=subprocess.run
    def observe(*args,**kwargs):
        result=original_run(*args,**kwargs)
        if result.returncode:print('NATIVE CHILD FAILURE:',result.stderr,result.stdout)
        return result
    monkeypatch.setattr(subprocess,'run',observe)
    from novel_news_v1 import generate_novel_news_plan,validate_novel_news_export
    from news_qualification_transport import novel_transport
    runtime,business,news,repo,owner=native_news_runtime(node)
    root=runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login=client.post('/api/auth/login',json={'phone':'13900000001','password':'SyntheticCase2026!'})
        assert login.status_code==200,login.text
        headers={'X-CSRF-Token':login.json()['csrf_token']}
        response=client.post('/api/create/novel-news/preview',headers=headers,json={
            'business_id':business['business_id'],'speaker_id':business['speaker_id']})
        assert response.status_code==200,response.text
        opportunity=response.json()['projection']['opportunities'][0]
        assert opportunity['production_feasibility']['status']=='supported'
        response=client.post('/api/create/confirm',headers=headers,json={
            'business_id':business['business_id'],'speaker_id':business['speaker_id'],'profile':'news',
            'requested_quantity':1,'confirmed_quantity':1,'idempotency_key':'native_news_novel_once',
            'selected_opportunity_id':opportunity['concept_id']})
        assert response.status_code==200,response.text
        rid=response.json()['result']['request_id']
        response=client.post('/api/create/'+rid+'/resolve-sources',headers=headers)
        assert response.status_code==200,response.text
        # Actual authenticated attempt/Task admission; substitute only the
        # external transport in its real worker process.
        response=client.post('/api/create/novel-news/'+rid+'/generate',headers=headers)
        assert response.status_code==200,response.text
        from test_news_generation_recovery_v1 import worker
        generated=worker(runtime,response.json()['task']['task_id'],'success')
        assert generated.returncode==0,(generated.stdout,generated.stderr)
        plan=read(root/'data/generation_batches'/rid/'novel_news_beat_plan_v1.json')
        assert len(plan['micro_information_beats'])==4
        response=client.post('/api/create/novel-news/'+rid+'/review',headers=headers,json={
            'decisions':[{'beat_id':b['beat_id'],'decision':'approved'} for b in plan['micro_information_beats']]})
        assert response.status_code==200,response.text
        response=client.post('/api/create/novel-news/'+rid+'/export',headers=headers)
        assert response.status_code==200,response.text
        task=response.json()['task']['task_id']
        BackgroundTaskRunner(runtime)._run(task)
        completed=get_task(runtime.database_path,task)
        assert completed['status']=='completed',completed
        receipt=validate_novel_news_export(pipeline_root=root,request_id=rid)
        assert Path(receipt['output_path']).is_file()
        assert client.get('/api/create/novel-news/'+rid+'/excel').status_code==200
        ledger=read(root/'data/content_ledgers'/business['business_id']/'content_ledger_v1.json')
        assert len(ledger['entries'])==1
        from news_qualification_v1_2 import create_evidence,validate_evidence
        from profile_compatibility_release_v1_2 import eligibility
        from profile_compatibility_contract_v1_2 import FOUNDER
        from profile_compatibility_contract_v1_1 import CompatibilityError
        import pytest
        evidence=create_evidence(root,rid,'novel_content')
        assert validate_evidence(root,evidence)['reuse_intent']=='novel_content'
        with pytest.raises(CompatibilityError):eligibility(root,[evidence],FOUNDER)
        assert create_evidence(root,rid,'novel_content')==evidence
