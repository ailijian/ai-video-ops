"""Policy v2: genuine K=2/K=1 Native groups, synthetic provider boundary only."""
import subprocess
from unittest.mock import patch
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from test_creative_style_native_v1 import style_runtime
from test_creation_batch_native_v1 import config
from test_creation_batch_orchestration_v1 import external_boundaries
from publish_copy_native_support import post
from app.main import build_app
from app.creation_batch_gateway import advance,state
from app.background_task_service import BackgroundTaskRunner
from app.task_service import get_task
from human_review_operations_v1 import read,io_path
import json
import pytest
import native_batch_v1 as native

EVENTS = [
    '有一次顾客下单时注明不吃香菜，店主小周核对备注后按单配菜，制作后标记餐盒。',
    '曾经顾客来店询问蔬菜是否当天清洗，店主小周当场说明清洗安排并带顾客查看操作台。',
    '有一次顾客在取餐时发现汤盒盖子未盖紧，店主小周重新封好汤盒并让顾客核对。',
    '曾经邻居提前来店询问周末营业安排，店主小周出示门口营业时间表供邻居查看。',
    '有一次顾客反馈午餐米饭份量需求较少，店主小周按该次顾客要求减少米饭并说明餐盒内容。',
]


def test_policy_two_five_same_style_slots_use_three_native_groups_without_semantic_reuse(node):
    runtime,business=style_runtime(node,'story',story_events=EVENTS)
    root=runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login['csrf_token']}
        body={**{k:business[k] for k in ('business_id','speaker_id')},
            'configuration':config(story=5),'operation_id':'five_distinct_story_events'}
        preview=post(client,'/api/create/batches/preview',headers,body)['preview']
        bid=post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':preview['source_configuration_sha256']})['result']['batch_id']
        context=read(native.directory(root,bid)/'permission.json')
        groups=native.groups(root,bid)
        assert [len(g['slots']) for g in groups]==[2,2,1],groups
        assert len({g['request_id'] for g in groups})==3
        original_slots=[s['slot_id'] for g in groups for s in g['slots']]
        assert native.batch_policy(root,bid)['policy_version']=='2'
        runner=BackgroundTaskRunner(runtime)
        try:
            with patch.object(subprocess,'run',external_boundaries):
                for _ in range(6):
                    next_step=advance(runtime,bid)
                    tid=next_step['task']['task_id'];runner._run(tid)
                    assert get_task(runtime.database_path,tid)['status']=='completed',get_task(runtime.database_path,tid)
            actual=state(runtime,bid,context)
            assert actual['counts']['generated']==5 and actual['counts']['approved']==0,actual
            plans=[read(root/'data/content_plans'/g['request_id']/'content_plan_v1_1_1.json') for g in groups]
            claims=[v['central_claim'] for p in plans for v in p['selected_concepts']]
            assert len(claims)==len(set(claims))==5,claims
            assert all(p['pending_selection_ref'] for p in plans)
            from creative_style_v1 import pinned
            assert [len(pinned(p['pending_selection_ref'])['concepts']) for p in plans]==[0,2,4]
            # The real persisted egress audit/prompt must distinguish these
            # reserved intentions from the still-empty communicated Ledger.
            calls=[json.loads((root/'data/metrics/generation_requests'/g['request_id']/'style_synthetic_planning_calls.jsonl').read_text('utf-8').splitlines()[0]) for g in groups]
            assert [v['pending_count'] for v in calls]==[0,2,4]
            assert all(v['communicated_count']==0 for v in calls)
            assert [s['slot_id'] for g in native.groups(root,bid) for s in g['slots']]==original_slots
            assert not (root/'data/content_ledgers'/business['business_id']/'content_ledger_v1.json').exists()
            assert not advance(runtime,bid)['advanced']
        finally:runner.close()


def test_policy_one_batch_keeps_its_original_groups_and_rejects_policy_rebinding(node):
    runtime,business=style_runtime(node,'story',story_events=EVENTS[:2]);root=runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login['csrf_token']}
        old_config={**config(story=2),'mode':'stage','stage':'steady','cycles':6,'cyclesConfirmed':True}
        body={**{k:business[k] for k in ('business_id','speaker_id')},'configuration':old_config,'operation_id':'original_policy_one'}
        with patch.object(native,'POLICY',native.LEGACY_POLICY):
            preview=post(client,'/api/create/batches/preview',headers,body)['preview']
            bid=post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':preview['source_configuration_sha256']})['result']['batch_id']
            original=native.groups(root,bid)
        assert native.batch_policy(root,bid)['policy_version']=='1'
        assert native.groups(root,bid)==original
        recovered=post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':preview['source_configuration_sha256']})['result']
        assert recovered['recovered'] and recovered['batch_id']==bid
        denied=client.post('/api/create/batches/preview',headers=headers,json={**body,'operation_id':'new_policy_two_rejects_six'})
        assert denied.status_code!=200
        configuration=native.directory(root,bid)/'configuration.json'
        before=io_path(configuration).read_bytes()
        changed=read(configuration)
        changed['source_snapshot']['admission_policy']=read(native.POLICY)
        io_path(configuration).write_text(json.dumps(changed),encoding='utf-8')
        with pytest.raises(native.BatchError):native.groups(root,bid)
        io_path(configuration).write_bytes(before)
        assert native.groups(root,bid)==original
