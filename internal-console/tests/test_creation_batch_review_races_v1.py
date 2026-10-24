"""Real original Human and delivery writers, with deterministic race scheduling."""
import json,subprocess,shutil
from unittest.mock import patch
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from creation_batch_golden_support import mixed_runtime,PROJECT
from test_creation_batch_native_v1 import config
from test_creation_batch_orchestration_v1 import external_boundaries
from test_creation_batch_post_human_v1 import human
from publish_copy_native_support import post,generation,worker,confirm,current
from app.main import build_app
from app.creation_batch_gateway import advance
from app.background_task_service import BackgroundTaskRunner
from app.task_service import get_task
import native_batch_v1 as native
import creation_batch_review_v1 as reviews


def test_newer_session_control_wins_and_publish_edit_waits_for_native_core_delivery(node):
    runtime,business=mixed_runtime(node);root=runtime.pipeline_root
    with TestClient(build_app(runtime)) as first,TestClient(build_app(runtime)) as second:
        def login(client):
            value=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
            return {'X-CSRF-Token':value['csrf_token']}
        headers=login(first);other=login(second)
        body={**{k:business[k] for k in ('business_id','speaker_id')},'configuration':config(story=1),'operation_id':'review_export_causal_races'}
        preview=post(first,'/api/create/batches/preview',headers,body)['preview']
        bid=post(first,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':preview['source_configuration_sha256']})['result']['batch_id']
        original_context=native.current_context(root,bid);runner=BackgroundTaskRunner(runtime)
        try:
            with patch.object(subprocess,'run',external_boundaries):
                for _ in range(2):
                    task=advance(runtime,bid)['task'];runner._run(task['task_id'])
                    assert get_task(runtime.database_path,task['task_id'])['status']=='completed'
            options=reviews.options(root,bid,original_context,'native_content_review')
            command={'scope':options['scope'],'source_sha256':options['source_sha256'],'operation_id':'human_before_newer_control',
                'items':[{**{k:v for k,v in i.items() if k!='display'},'decision':'approve'} for i in options['items']]}
            original_refresh=native.refresh_execution_context;newer=[]
            def after_control(*args,**kwargs):
                post(second,'/api/create/batches/'+bid+'/control',other,{'action':'pause','operation_id':'other_session_pause'})
                post(second,'/api/create/batches/'+bid+'/control',other,{'action':'resume','operation_id':'other_session_resume'})
                newer.append(native.current_context(root,bid))
                return original_refresh(*args,**kwargs)
            with patch.object(native,'refresh_execution_context',after_control):
                assert reviews.execute(root,bid,original_context,**command)['all_native_completed']
            assert native.current_context(root,bid)==newer[0]
            assert native.execution_contexts(root,bid)[-1]['control_head_ref'] is None
            post(first,'/api/auth/logout',headers)
            assert native.current_context(root,bid)==newer[0]  # S1 logout cannot invalidate S2's explicit resume.
            rid=native.groups(root,bid)[0]['request_id']
            tid=generation(second,other,rid)['task']['task_id']
            result=worker(runtime,tid);assert result.returncode==0,result.stdout+result.stderr
            confirm(second,other,rid)
            draft=current(second,rid)['draft']['ref'];context=native.current_context(root,bid)
            template=root/'output/素材混剪&数字人口播混剪文案导入模板.xlsx'
            template.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PROJECT/'ops-pipeline/output'/template.name,template)
            result=subprocess.run([runtime.pipeline_python_executable,str(PROJECT/'internal-console/tests/creation_batch_publish_race.py'),str(root),rid],
                input=json.dumps({'context':context,'draft_ref':draft,'business_id':business['business_id']}),
                capture_output=True,text=True,encoding='utf-8',timeout=60)
            assert result.returncode==0,result.stdout+result.stderr
            assert json.loads(result.stdout)['competing_edit_serialized']
        finally:runner.close()
