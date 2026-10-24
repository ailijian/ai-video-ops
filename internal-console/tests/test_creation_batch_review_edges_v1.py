"""Actual Native regressions for independent findings CR026..028."""
import subprocess
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from test_creative_style_native_v1 import style_runtime
from test_creation_batch_native_v1 import config,EVENTS
from test_creation_batch_orchestration_v1 import external_boundaries
from publish_copy_native_support import post,generation,worker,confirm
from app.main import build_app
from app.creation_batch_gateway import advance,state
from app.background_task_service import BackgroundTaskRunner
from app.task_service import get_task
from human_review_operations_v1 import read
from operation_lock_v1 import operation_lock,scoped_lock_key
import native_batch_v1 as native


@pytest.mark.parametrize('finding',['CR026','CR027','CR028','CR032'])
def test_original_native_review_replay_partial_publish_and_failed_task_status(node,finding):
    runtime,business=style_runtime(node,'story',story_events=EVENTS);root=runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login['csrf_token']}
        body={**{k:business[k] for k in ('business_id','speaker_id')},'configuration':config(story=2),'operation_id':'edge_'+finding}
        pre=post(client,'/api/create/batches/preview',headers,body)['preview']
        bid=post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':pre['source_configuration_sha256']})['result']['batch_id']
        context=read(native.directory(root,bid)/'permission.json');group=native.groups(root,bid)[0];rid=group['request_id']
        runner=BackgroundTaskRunner(runtime)
        try:
            first=advance(runtime,bid)['task']['task_id']
            if finding=='CR028':
                with operation_lock(root,scoped_lock_key('request',rid),timeout_seconds=0):runner._run(first)
                assert get_task(runtime.database_path,first)['status']=='failed'
                actual=state(runtime,bid,context)
                assert actual['counts']['unknown']==actual['counts']['failed']==0,actual
                assert actual['status']=='needs_attention',actual
                assert not actual['completion_proven']
                return
            with patch.object(subprocess,'run',external_boundaries):
                runner._run(first)
                assert get_task(runtime.database_path,first)['status']=='completed'
                second=advance(runtime,bid)['task']['task_id'];runner._run(second)
                assert get_task(runtime.database_path,second)['status']=='completed'
            pre=client.get('/api/create/batches/'+bid+'/human-options?scope=native_content_review').json()['preview']
            ordered=list(reversed(pre['items'])) if finding=='CR026' else pre['items']
            command={'scope':pre['scope'],'source_sha256':pre['source_sha256'],'operation_id':'explicit_'+finding,
                'items':[{**{k:v for k,v in i.items() if k!='display'},'decision':'approve'} for i in ordered]}
            first=post(client,'/api/create/batches/'+bid+'/human-command',headers,command)['result']
            assert first['all_native_completed'],first
            if finding=='CR026':
                replay=post(client,'/api/create/batches/'+bid+'/human-command',headers,command)['result']
                assert replay['all_native_completed'],replay
                assert first['command_ref']==replay['command_ref']
            else:
                raw=read(root/'data/generation_batches'/rid/'approved_generation_batch_v1.json')
                task=generation(client,headers,rid,targets=[raw['contents'][0]['content_id']] if finding=='CR027' else None)['task']['task_id']
                result=worker(runtime,task);assert result.returncode==0,result.stdout+result.stderr
                assert get_task(runtime.database_path,task)['status']=='completed'
                if finding=='CR032':
                    confirm(client,headers,rid)
                    exported=post(client,'/api/create/'+rid+'/publish-copy/export',headers)['task']['task_id']
                    worker(runtime,exported)
                    assert get_task(runtime.database_path,exported)['status']=='failed'
                    actual=state(runtime,bid,context)
                    assert actual['counts']['approved']==2 and actual['counts']['failed']==actual['counts']['unknown']==0,actual
                    assert actual['execution_needs_attention'] and actual['status']=='needs_attention',actual
                    from test_publish_copy_native_v1 import install_templates
                    import shutil
                    project=Path(__file__).resolve().parents[2]
                    install_templates(root)
                    template=root/'output/素材混剪&数字人口播混剪文案导入模板.xlsx'
                    template.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(project/'ops-pipeline/output'/template.name,template)
                    retried=post(client,'/api/create/'+rid+'/publish-copy/export',headers)['task']['task_id']
                    assert retried==exported
                    worker(runtime,retried,'selection_response_failure')
                    assert get_task(runtime.database_path,retried)['status']=='failed'
                    actual=state(runtime,bid,context)
                    assert not actual['execution_needs_attention'] and actual['status']=='ready_for_delivery',actual
                    assert actual['counts']['approved']==2 and actual['counts']['delivered']==0
                    assert not actual['completion_proven']
                    return
                preview=client.get('/api/create/batches/'+bid+'/human-options?scope=publish_copy_confirmation')
                assert preview.status_code==200,preview.text
                assert preview.json()['preview']['items']==[]
                assert preview.json()['preview']['excluded'][0]['code']=='CREATION_BATCH_PUBLISH_DRAFT_INCOMPLETE'
        finally:runner.close()
