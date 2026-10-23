"""NEWS_SOURCE_UX_1 HTTP/Native source and draft regressions, synthetic providers."""
import copy
import hashlib
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from creation_batch_golden_support import mixed_runtime
from news_source_ux_support import PRICES, qualified_history
from test_creation_batch_native_v1 import config
from test_creation_batch_orchestration_v1 import external_boundaries
from test_creation_batch_post_human_v1 import human
from publish_copy_native_support import post
from human_review_operations_v1 import read
from app.main import build_app
from app.creation_batch_gateway import advance, state
from app.background_task_service import BackgroundTaskRunner
from app.task_service import get_task
from app.database import connect
import native_batch_v1 as native

def login(client):
    value=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
    return {'X-CSRF-Token':value['csrf_token']}

def task_rows(runtime):
    with connect(runtime.database_path) as db:
        return [tuple(row) for row in db.execute('SELECT task_id,task_type,status,payload_json FROM tasks ORDER BY rowid')]

def result_artifact(name, value):
    if os.environ.get('AIVO_VERIFICATION_ARTIFACTS'):
        target=Path(os.environ['AIVO_VERIFICATION_ARTIFACTS']);target.mkdir(parents=True,exist_ok=True)
        (target/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def test_stage_defaults_and_two_novel_do_not_admit_repurpose_and_capacity_is_not_silently_reduced(node):
    runtime,business=mixed_runtime(node,pricing_facts=PRICES[:4]);root=runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        headers=login(client)
        cfg={**config(novel=10,persona=4,story=6),'mode':'stage','stage':'launch','combinedTarget':10}
        payload=native.configuration(cfg)
        assert payload['operating_stage']=='launch' and payload['quantities']['novel']==10 and payload['quantities']['repurpose']==0
        assert 'repurpose_source_ids' not in payload
        body={**{k:business[k] for k in ('business_id','speaker_id')},'configuration':cfg,'operation_id':'ux_stage_default'}
        # The preset cannot manufacture ten qualified topics from four facts.
        rejected=client.post('/api/create/batches/preview',headers=headers,json={**body,'configuration':config(novel=5)})
        assert rejected.status_code==409,rejected.text
        assert rejected.json()['detail']['code']=='CREATION_BATCH_SOURCE_CAPACITY'
        assert '仅有 4 个' in rejected.json()['detail']['message'] and '填写 5 条' in rejected.json()['detail']['message']
        assert not list(root.glob('data/creation_batches/*/intent.json'))
        body={**body,'configuration':config(novel=2),'operation_id':'ux_two_novel'}
        preview=post(client,'/api/create/batches/preview',headers,body)['preview']
        assert preview['actual_target']==preview['new_content_target']==2
        assert all(s['source_kind']=='novel_content' for s in preview['snapshot']['slots'])
        bid=post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':preview['source_configuration_sha256']})['result']['batch_id']
        groups=native.groups(root,bid);assert len(groups)==2 and all(g['profile']=='news' and g['source_kind']=='novel_content' for g in groups)
        advance(runtime,bid)
        assert not list(root.glob('data/news_deliveries/*/news_delivery_request_v1.json'))
        assert not any(json.loads(row[3]).get('operation','').startswith('news_') for row in task_rows(runtime))
        result_artifact('NOVEL_ONLY_HTTP.json',{'batch_id':bid,'operating_stage_default':'launch','default_novel':10,
            'default_repurpose':0,'target':2,'new_semantic_target':2,'repurpose_requests':0,'insufficient_capacity':'4 available / 5 requested / blocked'})

@pytest.mark.parametrize('novel_count,repurpose_count',[(0,2),(2,1)])
def test_selected_history_is_bound_per_native_slot_and_legacy_drafts_do_not_migrate(novel_count,repurpose_count,node):
    runtime,business,seed_batch=qualified_history(node);root=runtime.pipeline_root;business_id=business['business_id']
    with TestClient(build_app(runtime)) as client:
        headers=login(client);identity={k:business[k] for k in ('business_id','speaker_id')}
        available=post(client,'/api/create/news/preview',headers,identity)['preview']
        assert available['schema_version']=='news-delivery-preview-v1.0' and len(available['eligible_sources'])==2,available
        selected=[s['source_content_id'] for s in available['eligible_sources']][:repurpose_count]
        ledger_path=root/'data/content_ledgers'/business_id/'content_ledger_v1.json'
        original_ledger=read(ledger_path);original_ledger_bytes=ledger_path.read_bytes()
        protected={p:p.read_bytes() for g in native.groups(root,seed_batch)
                   for p in (root/'data/generation_batches'/g['request_id']).glob('*.json')}
        cfg={**config(novel=novel_count,repurpose=repurpose_count),'repurposeSourceIds':selected}
        body={**identity,'configuration':cfg,'operation_id':f'ux_origins_{novel_count}_{repurpose_count}'}
        initial_tasks=task_rows(runtime)
        for invalid in ({**cfg,'quantities':{**cfg['quantities'],'repurpose':3}},
                        {**cfg,'repurposeSourceIds':['foreign_business-C001']},
                        {**config(repurpose=2),'repurposeSourceIds':[selected[0],selected[0]]}):
            denied=client.post('/api/create/batches/preview',headers=headers,json={**body,'configuration':invalid})
            assert denied.status_code==409,denied.text
        assert task_rows(runtime)==initial_tasks and ledger_path.read_bytes()==original_ledger_bytes
        route='/api/create/configuration/'+business_id
        old={**cfg,'repurposeEnabled':False}
        saved=client.put(route,headers=headers,json={'revision':0,'payload':{'speaker_id':business['speaker_id'],'configuration':old}})
        assert saved.status_code==200,saved.text
        assert client.get(route).json()['draft']['configuration']==old
        assert client.post('/api/create/batches/preview',headers=headers,json={**body,'configuration':old}).status_code==409
        # An explicit current edit changes only this operator's draft, never old batches.
        cfg={**cfg,'revision':1};saved=saved.json()
        current=client.put(route,headers=headers,json={'revision':saved['revision'],'payload':{'speaker_id':business['speaker_id'],'configuration':cfg}})
        assert current.status_code==200,current.text
        stored=current.json();body={**body,'configuration':cfg,'operation_id':stored['operation_id']}
        for unknown in ({**cfg,'schema_version':'unknown-v99'},{**cfg,'invented_source_mode':'automatic'}):
            denied=client.put(route,headers=headers,json={'revision':stored['revision'],'payload':{'speaker_id':business['speaker_id'],'configuration':unknown}})
            assert denied.status_code==409 and denied.json()['detail']['code']=='CREATIVE_STYLE_DRAFT_INVALID',denied.text
        post(client,'/api/auth/logout',headers)
        denied=client.post('/api/create/news/preview',headers=headers,json=identity)
        assert denied.status_code==401 and 'source_title' not in denied.text,denied.text
        headers=login(client);assert client.get(route).json()['draft']['configuration']==cfg
        checked=post(client,'/api/create/batches/preview',headers,body)['preview']
        assert checked['actual_target']==novel_count+repurpose_count and checked['new_content_target']==novel_count
        source_refs=[r for s in checked['snapshot']['slots'] for r in s['source_refs'] if r['owner']=='native-repurpose-source']
        assert [r['id'] for r in source_refs]==selected and all(len(r['sha256'])==64 for r in source_refs)
        source_ids_before={p.parent.name for p in root.glob('data/creation_batches/*/intent.json')}
        # Disposable fault injection changes the exact source bytes. It never
        # creates an approval and is restored before normal Native execution.
        broken=copy.deepcopy(original_ledger);broken['entries'][0]['title']='故障注入：来源字节变化，不能当作批准'
        ledger_path.write_text(json.dumps(broken,ensure_ascii=False),encoding='utf-8')
        try:
            stale=client.post('/api/create/batches/confirm',headers=headers,json={**body,'preflight_sha256':checked['source_configuration_sha256']})
            assert stale.status_code in (409,503),stale.text
            assert stale.json()['detail']['code'] in {'CREATION_BATCH_PREFLIGHT_STALE','CONTENT_SETTLEMENT_INVALID'},stale.text
            assert {p.parent.name for p in root.glob('data/creation_batches/*/intent.json')}==source_ids_before
        finally:ledger_path.write_bytes(original_ledger_bytes)
        created=post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':checked['source_configuration_sha256']})['result']
        bid=created['batch_id'];groups=native.groups(root,bid)
        assert len(groups)==novel_count+repurpose_count
        assert sum(g['source_kind']=='novel_content' for g in groups)==novel_count
        assert sum(g['source_kind']=='cross_profile_repurpose' for g in groups)==repurpose_count
        replay=post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':checked['source_configuration_sha256']})['result']
        assert replay['recovered'] and replay['batch_id']==bid
        runner=BackgroundTaskRunner(runtime)
        try:
            with patch.object(subprocess,'run',external_boundaries):
                for group in groups:
                    step=advance(runtime,bid);assert step['advanced'],step
                    task=step['task'];runner._run(task['task_id'])
                    assert get_task(runtime.database_path,task['task_id'])['status']=='completed',get_task(runtime.database_path,task['task_id'])
                rp_groups=[g for g in groups if g['source_kind']=='cross_profile_repurpose']
                requests=[read(native.request_path(root,g['request_id'])) for g in rp_groups]
                assert [r['source_content_id'] for r in requests]==selected
                assert all(r['schema_version']=='news-delivery-request-v1.2' and r['business_id']==business_id for r in requests)
                actual=state(runtime,bid,native.current_context(root,bid))
                assert actual['counts']['generated']==novel_count+repurpose_count and actual['counts']['approved']==actual['counts']['delivered']==0
                if not novel_count:
                    human(client,headers,bid,'native_content_review','ux_explicit_rp_content')
                    for _ in groups:
                        task=advance(runtime,bid)['task'];runner._run(task['task_id'])
                        assert get_task(runtime.database_path,task['task_id'])['status']=='completed'
                    human(client,headers,bid,'publish_copy_confirmation','ux_explicit_rp_publish')
                    for _ in groups:
                        task=advance(runtime,bid)['task'];runner._run(task['task_id'])
                        assert get_task(runtime.database_path,task['task_id'])['status']=='completed'
                    after=read(ledger_path);assert after['entries']==original_ledger['entries']
                    from news_delivery_v1 import _news_presentation_history_for_source
                    assert all(len(_news_presentation_history_for_source(after,s))==len(_news_presentation_history_for_source(original_ledger,s))+1 for s in selected)
                    actual=state(runtime,bid,native.current_context(root,bid))
                    assert actual['counts']['new_semantic_count']==0 and actual['counts']['repurpose_presentation_count']==2
                else:assert ledger_path.read_bytes()==original_ledger_bytes
                before_replay=task_rows(runtime);preserved_ledger=ledger_path.read_bytes()
                post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':checked['source_configuration_sha256']})
                assert task_rows(runtime)==before_replay and ledger_path.read_bytes()==preserved_ledger
                assert all(p.read_bytes()==value for p,value in protected.items())
                result_artifact(f'NEWS_ORIGINS_{novel_count}_{repurpose_count}.json',{'batch_id':bid,'native_request_ids':[g['request_id'] for g in groups],
                    'target':novel_count+repurpose_count,'novel':novel_count,'repurpose':repurpose_count,'selected_sources':selected,'source_refs':source_refs,
                    'source_sha_change':'BLOCKED','old_draft':'preserved, ambiguity blocked, explicit edit required','unknown_fields':'rejected',
                    'relogin':'same draft recovered','completed_confirm_replay':'zero extra Task/Ledger','original_receipts_unchanged':True,
                    'native_generated':actual['counts']['generated'],'new_semantic_count':actual['counts']['new_semantic_count'],
                    'repurpose_presentation_count':actual['counts']['repurpose_presentation_count']})
        finally:runner.close()
