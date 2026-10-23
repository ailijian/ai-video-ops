"""Explicit historical presentation sources; Native semantic/presentation owners."""
import shutil,subprocess
from unittest.mock import patch
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from creation_batch_golden_support import mixed_runtime,PROJECT
from test_creation_batch_native_v1 import config
from publish_copy_native_support import post,mix_reviewed
from test_news_qualification_complete_v1_2 import native_task
from test_creation_batch_orchestration_v1 import external_boundaries
from test_creation_batch_post_human_v1 import human
from app.main import build_app
from app.creation_batch_gateway import advance,state
from app.creation_batch_delivery_gateway import owner
from app.background_task_service import BackgroundTaskRunner
from app.task_service import get_task
from human_review_operations_v1 import read
from content_intent_reservations_v1 import events
import native_batch_v1 as native


def historical_source(client,headers,runtime,business):
    rid=mix_reviewed(client,headers,runtime,business,'original_qualified_historical_price')
    native_task(runtime,client.post('/api/create/'+rid+'/export-mix',headers=headers))
    preview=post(client,'/api/create/news/preview',headers,{k:business[k] for k in ('business_id','speaker_id')})['preview']
    assert preview['eligible_sources'],preview
    return rid,preview['eligible_sources'][0]['source_content_id']


def test_explicit_repurpose_batch_retains_native_request_source_and_semantic_zero(node):
    runtime,business=mixed_runtime(node,pricing_facts=['午餐套餐29元，仅限到店自取，不含配送',
        '儿童小份餐15元，仅限周末店内点单，不参与工作日午餐套餐']);root=runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login['csrf_token']}
        seed,source_id=historical_source(client,headers,runtime,business)
        ledger_path=root/'data/content_ledgers'/business['business_id']/'content_ledger_v1.json'
        original=read(ledger_path)
        configuration={**config(repurpose=1),'repurposeEnabled':True,'repurposeSourceIds':[source_id]}
        body={**{k:business[k] for k in ('business_id','speaker_id')},'configuration':configuration,'operation_id':'explicit_presentation_source'}
        pre=post(client,'/api/create/batches/preview',headers,body)['preview']
        assert pre['actual_target']==1 and pre['new_content_target']==0
        bid=post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':pre['source_configuration_sha256']})['result']['batch_id']
        groups=native.groups(root,bid);rp=next(g for g in groups if g['source_kind']=='cross_profile_repurpose')
        assert rp['request_id'].startswith('news_') and len(rp['slots'])==1
        runner=BackgroundTaskRunner(runtime)
        try:
            with patch.object(subprocess,'run',external_boundaries):
                for _ in range(1):
                    step=advance(runtime,bid);assert step['advanced'],step
                    runner._run(step['task']['task_id'])
                    assert get_task(runtime.database_path,step['task']['task_id'])['status']=='completed',get_task(runtime.database_path,step['task']['task_id'])
                request=read(native.request_path(root,rp['request_id']))
                assert request['schema_version']=='news-delivery-request-v1.2'
                assert request['source_content_id']==source_id and 4<=request['recommended_slot_count']<=8
                assert not (root/'data/generation_requests'/rp['request_id']).exists()
                # The same presentation source is held, never counted as a new
                # semantic selection or silently substituted by a Novel source.
                assert not post(client,'/api/create/news/preview',headers,{k:business[k] for k in ('business_id','speaker_id')})['preview']['eligible_sources']
                assert client.post('/api/create/batches/preview',headers=headers,json={**body,'operation_id':'another_batch_same_source'}).status_code!=200
                context=read(native.directory(root,bid)/'permission.json')
                pre=client.get('/api/create/batches/'+bid+'/human-options?scope=native_content_review').json()['preview']
                assert len(pre['items'])==1 and pre['items'][0]['native_kind']=='cross_profile_repurpose',pre
                command={'scope':pre['scope'],'source_sha256':pre['source_sha256'],'operation_id':'explicit_full_command_bounded_parts',
                    'items':[{**{k:v for k,v in i.items() if k!='display'},'decision':'approve'} for i in pre['items']]}
                first=owner(runtime,bid,'execute',context,**command,maximum_mutations=1)
                assert first['all_native_completed'] and not first['continuation_needed'],first
                assert state(runtime,bid,context)['counts']['approved']==1
                second=owner(runtime,bid,'execute',context,**command,maximum_mutations=1)
                assert second['all_native_completed'] and not second['continuation_needed'],second
                for _ in range(1):
                    step=advance(runtime,bid);assert step['advanced'],step
                    runner._run(step['task']['task_id'])
                    assert get_task(runtime.database_path,step['task']['task_id'])['status']=='completed',get_task(runtime.database_path,step['task']['task_id'])
                human(client,headers,bid,'publish_copy_confirmation','explicit_mixed_publish_confirmation')
                template=root/'output/素材混剪&数字人口播混剪文案导入模板.xlsx'
                template.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PROJECT/'ops-pipeline/output'/template.name,template)
                for _ in range(1):
                    step=advance(runtime,bid);assert step['advanced'],step
                    runner._run(step['task']['task_id'])
                    assert get_task(runtime.database_path,step['task']['task_id'])['status']=='completed',get_task(runtime.database_path,step['task']['task_id'])
                assert native.groups(root,bid)==groups
                now=read(ledger_path)
                assert len(now['entries'])==len(original['entries'])
                assert now['entries'][:len(original['entries'])]==original['entries']
                from news_delivery_v1 import _news_presentation_history_for_source
                assert len(_news_presentation_history_for_source(now,source_id))==len(_news_presentation_history_for_source(original,source_id))+1
                slots=[s['slot_id'] for g in groups for s in g['slots']]
                scope={'scope':'complete_target','slot_ids':slots}
                pre=post(client,'/api/create/batches/'+bid+'/delivery-preview',headers,scope)['preview']
                assert {v['profile']:v['rows'] for v in pre['files']}=={'news':1}
                protected=ledger_path.read_bytes()
                payload={**scope,'source_sha256':pre['source_sha256'],'operation_id':'explicit_rp_and_mix_files'}
                task=post(client,'/api/create/batches/'+bid+'/delivery-export',headers,payload)['task']
                runner._run(task['task_id']);assert get_task(runtime.database_path,task['task_id'])['status']=='completed'
                assert not post(client,'/api/create/batches/'+bid+'/delivery-export',headers,payload)['accepted']
                actual=state(runtime,bid,context)
                assert actual['completion_proven'] and actual['counts']['delivered']==1 and actual['counts']['new_semantic_count']==0,actual
                assert actual['counts']['repurpose_presentation_count']==1
                assert ledger_path.read_bytes()==protected
                native.settle(root,bid)
                assert events(root,business['business_id'],rp['request_id'])[-1][1]['event']=='consumed_by_native_closure'
                from app.creation_batch_gateway import admit_group
                preserved=native.request_path(root,rp['request_id']).read_bytes()
                assert admit_group(runtime,bid,rp['group_id'],context)['recovered']
                assert native.request_path(root,rp['request_id']).read_bytes()==preserved and ledger_path.read_bytes()==protected
        finally:runner.close()


def test_repurpose_pending_source_end_and_new_explicit_selection_preserve_history(node):
    runtime,business=mixed_runtime(node,pricing_facts=['午餐套餐29元，仅限到店自取，不含配送',
        '儿童小份餐15元，仅限周末店内点单，不参与工作日午餐套餐']);root=runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login['csrf_token']}
        _,source_id=historical_source(client,headers,runtime,business)
        ledger=root/'data/content_ledgers'/business['business_id']/'content_ledger_v1.json';protected=ledger.read_bytes()
        configuration={**config(repurpose=1),'repurposeEnabled':True,'repurposeSourceIds':[source_id]}
        body={**{k:business[k] for k in ('business_id','speaker_id')},'configuration':configuration,'operation_id':'end_unissued_presentation'}
        for changed in ({**configuration,'repurposeSourceIds':[]},
                        {**configuration,'quantities':{**configuration['quantities'],'repurpose':2},'repurposeSourceIds':[source_id,source_id]},
                        {**configuration,'repurposeSourceIds':['gen_foreign_source-C001']}):
            assert client.post('/api/create/batches/preview',headers=headers,json={**body,'configuration':changed}).status_code!=200
        assert not list(root.glob('data/creation_batches/*/intent.json'))
        pre=post(client,'/api/create/batches/preview',headers,body)['preview']
        bid=post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':pre['source_configuration_sha256']})['result']['batch_id']
        queued=advance(runtime,bid)['task'];group=native.groups(root,bid)[0];rid=group['request_id']
        assert client.post('/api/create/news/request',headers=headers,json={**{k:business[k] for k in ('business_id','speaker_id')},
            'source_content_id':source_id,'idempotency_key':'legacy_cannot_take_held_presentation'}).status_code!=200
        stopped=post(client,'/api/create/batches/'+bid+'/control',headers,{'action':'end','operation_id':'explicit_end_before_deterministic_plan'})['result']
        assert any(v['kind']=='cancelled_unissued' and v['event']=='safely_released' for v in stopped['settlements']),stopped
        assert get_task(runtime.database_path,queued['task_id'])['status']=='failed'
        assert events(root,business['business_id'],rid)[-1][1]['event']=='safely_released'
        request=native.request_path(root,rid);assert request.with_name('news_delivery_cancellation_v1.json').is_file()
        assert not request.with_name('news_delivery_plan_v1.json').exists()
        assert client.post('/api/create/news/'+rid+'/resolve-plan',headers=headers).status_code!=200
        actual=client.get('/api/create/batches/'+bid).json()['state']
        assert actual['control']=='end' and actual['counts']['generated']==actual['counts']['approved']==actual['counts']['delivered']==0
        assert not actual['completion_proven'] and not actual['execution_needs_attention']
        again=post(client,'/api/create/batches/preview',headers,{**body,'operation_id':'new_explicit_source_after_safe_end'})['preview']
        assert again['actual_target']==1 and again['new_content_target']==0
        assert ledger.read_bytes()==protected
