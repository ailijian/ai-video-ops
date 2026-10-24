"""Repurpose takes its own native Request and exact exported Mix history."""
from test_case_evidence_revision_v1 import node
from test_news_novel_runtime_v1_2 import native_news_runtime
from test_profile_compatibility_golden_v1_1 import exercise_creation_tasks
from fastapi.testclient import TestClient
from app.main import build_app
from app.background_task_service import BackgroundTaskRunner
from app.task_service import get_task
from profile_compatibility_decisions_v1_1 import read
from pathlib import Path


def test_native_repurpose_from_formal_mix_source_no_semantic_ledger_increment(node,monkeypatch):
    import subprocess
    original=subprocess.run
    def observe(*args,**kwargs):
        value=original(*args,**kwargs)
        if value.returncode:print('NATIVE CHILD FAILURE:',value.stderr,value.stdout)
        return value
    monkeypatch.setattr(subprocess,'run',observe)
    runtime,business,news,repo,owner=native_news_runtime(node,mixed=True)
    root=runtime.pipeline_root;project=Path(__file__).resolve().parents[2]
    with TestClient(build_app(runtime)) as client:
        login=client.post('/api/auth/login',json={'phone':'13900000001','password':'SyntheticCase2026!'})
        assert login.status_code==200,login.text
        headers={'X-CSRF-Token':login.json()['csrf_token']}
        created=client.post('/api/create/confirm',headers=headers,json={
            'business_id':business['business_id'],'speaker_id':business['speaker_id'],'profile':'mix',
            'requested_quantity':1,'confirmed_quantity':1,'idempotency_key':'formal_repurpose_mix_history'})
        assert created.status_code==200,created.text
        rid=created.json()['result']['request_id']
        resolved=client.post('/api/create/'+rid+'/resolve-sources',headers=headers)
        assert resolved.status_code==200,resolved.text
        exercise_creation_tasks(client,headers,runtime,rid,project,transport_operations={
            'resolve_generation_content_plan_v1.py':'plan-news-history',
            'resolve_generation_batch_v1.py':'generate-news-history'})
        ledger_path=root/'data/content_ledgers'/business['business_id']/'content_ledger_v1.json'
        before=read(ledger_path)['entries']
        response=client.post('/api/create/news/preview',headers=headers,json={
            'business_id':business['business_id'],'speaker_id':business['speaker_id']})
        assert response.status_code==200,response.text
        preview=response.json()['preview']
        assert preview['available'],preview
        source=preview['eligible_sources'][0]['source_content_id']
        response=client.post('/api/create/news/request',headers=headers,json={
            'business_id':business['business_id'],'speaker_id':business['speaker_id'],
            'source_content_id':source,'idempotency_key':'native_repurpose_qualification_once'})
        assert response.status_code==200,response.text
        nrid=response.json()['result']['request']['request_id'];url='/api/create/news/'+nrid
        assert not (root/'data/generation_requests'/nrid).exists()
        response=client.post(url+'/resolve-plan',headers=headers)
        assert response.status_code==200,response.text
        runner=BackgroundTaskRunner(runtime)
        task_id=response.json()['task']['task_id'];runner._run(task_id)
        assert get_task(runtime.database_path,task_id)['status']=='completed',get_task(runtime.database_path,task_id)
        state=client.get(url+'/delivery');assert state.status_code==200,state.text
        slots=state.json()['state']['plan']['slots']
        response=client.post(url+'/review',headers=headers,json={'items':[
            {'slot_id':s['slot_id'],'decision':'approved'} for s in slots]})
        assert response.status_code==200,response.text
        response=client.post(url+'/export',headers=headers)
        assert response.status_code==200,response.text
        task_id=response.json()['task']['task_id'];runner._run(task_id)
        assert get_task(runtime.database_path,task_id)['status']=='completed',get_task(runtime.database_path,task_id)
        assert client.get(url+'/excel').status_code==200
        assert read(ledger_path)['entries']==before
        from news_qualification_v1_2 import create_evidence,validate_evidence
        proof=create_evidence(root,nrid,'cross_profile_repurpose')
        assert validate_evidence(root,proof)['reuse_intent']=='cross_profile_repurpose'
        runner.close()
