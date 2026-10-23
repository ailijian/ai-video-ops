"""Original post-Human owners advance; explicit decisions and recovery remain."""
import subprocess,shutil
from unittest.mock import patch
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from creation_batch_golden_support import mixed_runtime,PROJECT
from test_creation_batch_native_v1 import config
from test_creation_batch_orchestration_v1 import external_boundaries
from publish_copy_native_support import post,calls
from app.main import build_app
from app.creation_batch_gateway import advance,state
from app.background_task_service import BackgroundTaskRunner
from app.task_service import get_task
from human_review_operations_v1 import read
import native_batch_v1 as native
import pytest


def human(client,headers,bid,scope,operation):
    options=client.get('/api/create/batches/'+bid+'/human-options?scope='+scope).json()['preview']
    assert options['items'],options
    command={'scope':scope,'source_sha256':options['source_sha256'],'operation_id':operation,
        'items':[{**{k:v for k,v in item.items() if k!='display'},
                  **({'decision':'approve'} if scope=='native_content_review' else {'action':'confirm'})} for item in options['items']]}
    assert post(client,'/api/create/batches/'+bid+'/human-command',headers,command)['result']['all_native_completed']


def test_original_batch_advances_publish_and_parent_only_after_explicit_human_gates(node):
    runtime,business=mixed_runtime(node);root=runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login['csrf_token']}
        body={**{k:business[k] for k in ('business_id','speaker_id')},'configuration':config(story=2,novel=1),
              'operation_id':'post_human_native_owners'}
        pre=post(client,'/api/create/batches/preview',headers,body)['preview']
        bid=post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':pre['source_configuration_sha256']})['result']['batch_id']
        context=read(native.directory(root,bid)/'permission.json')
        runner=BackgroundTaskRunner(runtime)
        try:
            with patch.object(subprocess,'run',external_boundaries):
                for _ in range(3):
                    step=advance(runtime,bid);assert step['advanced'],step
                    tid=step['task']['task_id'];runner._run(tid)
                    assert get_task(runtime.database_path,tid)['status']=='completed',get_task(runtime.database_path,tid)
                assert advance(runtime,bid)['reason']=='native_human_review_required'
                assert not list(root.glob('data/**/publish_copy_v1/attempts/*/dispatch.json'))
                original_permission=(native.directory(root,bid)/'permission.json').read_bytes()
                post(client,'/api/auth/logout',headers)
                login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
                headers={'X-CSRF-Token':login['csrf_token']}
                human(client,headers,bid,'native_content_review','explicit_content_human')
                context=native.current_context(root,bid)
                assert (native.directory(root,bid)/'permission.json').read_bytes()==original_permission
                assert not native.controls(root,bid)  # No artificial resume required.
                for _ in range(2):
                    step=advance(runtime,bid);assert step['advanced'] and step['phase']=='publish_copy',step
                    task=step['task'];rid=task['subject_ref']
                    before=advance(runtime,bid);assert not before['advanced']
                    runner._run(task['task_id'])
                    assert get_task(runtime.database_path,task['task_id'])['status']=='completed',get_task(runtime.database_path,task['task_id'])
                    assert len(calls(root,rid))==1
                assert advance(runtime,bid)['reason']=='publish_confirmation_required'
                assert not list(root.glob('data/content_ledgers/**/*.json'))
                human(client,headers,bid,'publish_copy_confirmation','explicit_publish_human')
                template=root/'output/素材混剪&数字人口播混剪文案导入模板.xlsx'
                template.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PROJECT/'ops-pipeline/output'/template.name,template)
                for _ in range(2):
                    step=advance(runtime,bid);assert step['advanced'] and step['phase']=='native_parent_delivery',step
                    runner._run(step['task']['task_id'])
                    assert get_task(runtime.database_path,step['task']['task_id'])['status']=='completed',get_task(runtime.database_path,step['task']['task_id'])
                assert advance(runtime,bid)['reason']=='ready_for_delivery'
                actual=state(runtime,bid,context)
                assert actual['counts']['approved']==actual['counts']['native_exported']==3 and actual['counts']['delivered']==0
                assert not actual['completion_proven'] and actual['status']=='ready_for_delivery'
                protected={p:p.read_bytes() for p in root.glob('data/content_ledgers/**/*.json')}
                for _ in range(2):assert not advance(runtime,bid)['advanced']
                assert all(p.read_bytes()==data for p,data in protected.items())
                assert len(list(native.directory(root,bid).glob('local_delivery_dispatch/*/dispatch.json')))==2
                journals={p:p.read_bytes() for p in native.directory(root,bid).glob('human_commands/**/*.json')}
                post(client,'/api/auth/logout',headers)
                login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
                headers={'X-CSRF-Token':login['csrf_token']}
                recovered=client.get('/api/create/batches/'+bid+'/human-commands')
                assert recovered.status_code==200,recovered.text
                history=recovered.json()['history']
                assert history['read_only'] and len(history['commands'])==2 and not history['blocked']
                assert all(v['review_state']=='command_saved_not_approval' for v in history['commands'])
                saved=next(v for v in history['commands'] if v['scope']=='native_content_review')
                command={k:saved[k] for k in ('scope','items','operation_id','source_sha256')}
                assert post(client,'/api/create/batches/'+bid+'/human-command',headers,command)['result']['all_native_completed']
                assert all(p.read_bytes()==data for p,data in journals.items())
                assert all(p.read_bytes()==data for p,data in protected.items())
        finally:runner.close()


@pytest.mark.parametrize('action',['pause','end'])
def test_unissued_automatic_publish_stops_at_native_fence_and_explicit_recovery_is_preserved(node,action):
    runtime,business=mixed_runtime(node);root=runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login['csrf_token']}
        body={**{k:business[k] for k in ('business_id','speaker_id')},'configuration':config(story=2),
              'operation_id':'stop_unissued_publish_'+action}
        pre=post(client,'/api/create/batches/preview',headers,body)['preview']
        bid=post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':pre['source_configuration_sha256']})['result']['batch_id']
        runner=BackgroundTaskRunner(runtime)
        try:
            with patch.object(subprocess,'run',external_boundaries):
                for _ in range(2):
                    tid=advance(runtime,bid)['task']['task_id'];runner._run(tid)
                    assert get_task(runtime.database_path,tid)['status']=='completed'
                human(client,headers,bid,'native_content_review','approve_before_'+action)
                task=advance(runtime,bid)['task'];rid=task['subject_ref']
                url='/api/create/batches/'+bid+'/control'
                post(client,url,headers,{'action':action,'operation_id':action+'_before_publish_dispatch'})
                runner._run(task['task_id'])
                assert get_task(runtime.database_path,task['task_id'])['status']=='failed'
                assert not calls(root,rid)
                assert not list((root/'data/generation_batches'/rid/'publish_copy_v1').glob('attempts/*/dispatch.json'))
                assert not advance(runtime,bid)['advanced']
                if action=='pause':
                    resumed=post(client,url,headers,{'action':'resume','operation_id':'explicit_resume_publish'})['result']
                    assert resumed['local_continuations'][0]['task']['task_id']==task['task_id'],resumed
                    runner._run(task['task_id'])
                    assert get_task(runtime.database_path,task['task_id'])['status']=='completed'
                else:
                    # An ended batch stays ended. Its legitimate approved
                    # source can still use the original explicit Native retry.
                    from publish_copy_native_support import generation
                    manual=generation(client,headers,rid,retry=True)['task']
                    assert manual['task_id']!=task['task_id']
                    runner._run(manual['task_id'])
                    assert get_task(runtime.database_path,manual['task_id'])['status']=='completed',get_task(runtime.database_path,manual['task_id'])
                    assert native.controls(root,bid)[-1]['action']=='end'
                assert len(calls(root,rid))==1
                assert not list(root.glob('data/content_ledgers/**/*.json'))
        finally:runner.close()


def test_manual_publish_resume_keeps_identity_and_foreign_confirmation_cannot_write_core_history(node):
    runtime,business=mixed_runtime(node);root=runtime.pipeline_root
    from app.publish_copy_gateway import project
    from publish_copy_native_support import generation
    from operation_lock_v1 import operation_lock
    from profile_compatibility_decisions_v1_1 import resolve_ref
    with TestClient(build_app(runtime)) as client:
        login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login['csrf_token']}
        body={**{k:business[k] for k in ('business_id','speaker_id')},'configuration':config(story=2),'operation_id':'manual_publish_preserved'}
        pre=post(client,'/api/create/batches/preview',headers,body)['preview']
        bid=post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':pre['source_configuration_sha256']})['result']['batch_id']
        runner=BackgroundTaskRunner(runtime)
        try:
            with patch.object(subprocess,'run',external_boundaries):
                for _ in range(2):
                    tid=advance(runtime,bid)['task']['task_id'];runner._run(tid)
                    assert get_task(runtime.database_path,tid)['status']=='completed'
                human(client,headers,bid,'native_content_review','explicit_original_human')
                task=advance(runtime,bid)['task'];rid=task['subject_ref'];runner._run(task['task_id'])
                assert get_task(runtime.database_path,task['task_id'])['status']=='completed'
                manual=generation(client,headers,rid,retry=True)['task']
                operation=manual['payload']['publish_copy']['operation_id']
                with operation_lock(root,'publish-copy-executor:'+operation,timeout_seconds=0):runner._run(manual['task_id'])
                assert get_task(runtime.database_path,manual['task_id'])['status']=='failed'
                actual=project(runtime,rid)
                original=read(resolve_ref(root,actual['attempt_ref']))
                assert actual['state']=='not_dispatched' and original['schema_version']=='publish-copy-generation-intent-v1.0'
                assert 'batch_intent_ref' not in original
                url='/api/create/batches/'+bid+'/control'
                post(client,url,headers,{'action':'pause','operation_id':'pause_manual_operation'})
                resumed=post(client,url,headers,{'action':'resume','operation_id':'resume_does_not_rebind_manual'})['result']
                assert not resumed['local_continuations']
                assert get_task(runtime.database_path,manual['task_id'])['status']=='failed'
                assert read(resolve_ref(root,actual['attempt_ref']))==original
                retry=generation(client,headers,rid)['task'];assert retry['task_id']==manual['task_id']
                runner._run(retry['task_id']);assert get_task(runtime.database_path,retry['task_id'])['status']=='completed'
                assert len(calls(root,rid))==2
                current=project(runtime,rid)
                with TestClient(build_app(runtime)) as second:
                    login=post(second,'/api/auth/login',{}, {'phone':'13900000002','password':'SyntheticCase2026!'})
                    post(second,'/api/create/'+rid+'/publish-copy/confirm',{'X-CSRF-Token':login['csrf_token']},
                        {'draft_ref':current['draft']['ref']})
                dispatched=advance(runtime,bid)['task'];runner._run(dispatched['task_id'])
                assert get_task(runtime.database_path,dispatched['task_id'])['status']=='failed'
                assert not list(root.glob('data/content_ledgers/**/*.json'))
                assert not (root/'data/generation_batches'/rid/'generation_export_closure_v1.json').exists()
                assert not list(native.directory(root,bid).glob('local_delivery_dispatch/*/dispatch.json'))
                # The direct original delegation must reject before ensure_core
                # as well, even when the Publish CLI entry is not the caller.
                from export_mix_excel_v1 import export_supplemental_delivery
                context=native.current_context(root,bid)
                with pytest.raises(RuntimeError):
                    export_supplemental_delivery(pipeline_root=root,request_id=rid,authorization_context=context,
                        expected_draft_ref=current['draft']['ref'])
                assert not list(root.glob('data/content_ledgers/**/*.json'))
        finally:runner.close()
