"""Two distinct approved values through the actual Conversion Native chain."""
import subprocess,shutil
from unittest.mock import patch
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from creation_batch_golden_support import mixed_runtime,PROJECT
from test_creation_batch_native_v1 import config
from test_creation_batch_orchestration_v1 import external_boundaries
from publish_copy_native_support import post,generation,worker,confirm
from test_publish_copy_native_v1 import install_templates
from human_review_operations_v1 import read
from app.main import build_app
from app.creation_batch_gateway import advance,state
from app.background_task_service import BackgroundTaskRunner
from app.task_service import get_task
import native_batch_v1 as native


def conversion_history(node, *, pricing_facts=None, external_boundary=external_boundaries):
    runtime,business=mixed_runtime(node,pricing_facts=pricing_facts);root=runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login['csrf_token']}
        body={**{k:business[k] for k in ('business_id','speaker_id')},'configuration':config(conversion=2),'operation_id':'two_distinct_approved_values'}
        pre=post(client,'/api/create/batches/preview',headers,body)['preview']
        bid=post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':pre['source_configuration_sha256']})['result']['batch_id']
        runner=BackgroundTaskRunner(runtime)
        try:
            with patch.object(subprocess,'run',external_boundary):
                for _ in range(2):
                    tid=advance(runtime,bid)['task']['task_id'];runner._run(tid)
                    assert get_task(runtime.database_path,tid)['status']=='completed',get_task(runtime.database_path,tid)
            actual=client.get('/api/create/batches/'+bid+'/human-options?scope=native_content_review').json()['preview']
            assert len(actual['items'])==2,actual
            command={'scope':actual['scope'],'source_sha256':actual['source_sha256'],'operation_id':'explicit_value_reviews',
                'items':[{**{k:v for k,v in i.items() if k!='display'},'decision':'approve'} for i in actual['items']]}
            assert post(client,'/api/create/batches/'+bid+'/human-command',headers,command)['result']['all_native_completed']
            group=native.groups(root,bid)[0];rid=group['request_id']
            task=generation(client,headers,rid)['task']['task_id']
            completed=worker(runtime,task);assert completed.returncode==0,completed.stdout+completed.stderr
            assert get_task(runtime.database_path,task)['status']=='completed',get_task(runtime.database_path,task)
            confirm(client,headers,rid);install_templates(root)
            template=root/'output/素材混剪&数字人口播混剪文案导入模板.xlsx'
            template.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PROJECT/'ops-pipeline/output'/template.name,template)
            task=post(client,'/api/create/'+rid+'/publish-copy/export',headers)['task']['task_id']
            completed=worker(runtime,task);assert completed.returncode==0,completed.stdout+completed.stderr
            assert get_task(runtime.database_path,task)['status']=='completed',get_task(runtime.database_path,task)
            native.settle(root,bid)
            approved=read(root/'data/generation_batches'/rid/'approved_generation_batch_v1.json')
            assert len({v['central_claim'] for v in approved['contents']})==2
            assert all(v['creative_style']['style_id']=='conversion' for v in approved['contents'])
            ledger=read(root/'data/content_ledgers'/business['business_id']/'content_ledger_v1.json')
            assert len(ledger['entries'])==2
        finally:runner.close()
    return runtime,business,bid


def test_two_conversion_values_preserve_qualified_style_human_publish_and_original_history(node):
    conversion_history(node)
