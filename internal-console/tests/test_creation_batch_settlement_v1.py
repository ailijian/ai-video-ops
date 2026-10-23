"""Native-safe terminal reservations; no TTL, fabricated approval or Ledger."""
from pathlib import Path
import shutil
import subprocess
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from test_creative_style_native_v1 import style_runtime
from test_news_novel_runtime_v1_2 import native_news_runtime
from test_creation_batch_native_v1 import EVENTS,config
from test_creation_batch_orchestration_v1 import external_boundaries
from app.main import build_app
from app.creation_batch_gateway import advance,state,admit_group
from app.background_task_service import BackgroundTaskRunner
from app.task_service import get_task
from publish_copy_native_support import post
from human_review_operations_v1 import read,io_path
from operation_lock_v1 import operation_lock
from creative_style_v1 import file_sha
import native_batch_v1 as native
import content_intent_reservations_v1 as quality

PROJECT=Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('scenario',['journal_novel','queued_mix','unknown_mix','rejected_mix','closed_mix'])
def test_original_native_evidence_controls_safe_settlement(node,scenario):
    if scenario=='journal_novel':runtime,business,_,_,_=native_news_runtime(node)
    else:runtime,business=style_runtime(node,'story',story_events=EVENTS)
    root=runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login['csrf_token']}
        body={**{k:business[k] for k in ('business_id','speaker_id')},
            'configuration':config(**({'novel':1} if scenario=='journal_novel' else {'story':2})),
            'operation_id':'safe_settlement_'+scenario}
        pre=post(client,'/api/create/batches/preview',headers,body)['preview']
        bid=post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':pre['source_configuration_sha256']})['result']['batch_id']
        context=read(native.directory(root,bid)/'permission.json')
        group=native.groups(root,bid)[0];rid=group['request_id']
        runner=BackgroundTaskRunner(runtime)
        try:
            if scenario=='journal_novel':
                from generation_request_handoff_v1 import _business_generation_lock
                with _business_generation_lock(root,business['business_id']):native.admission(root,bid,group['group_id'],context)
                assert quality.pending(root,business['business_id'])
                assert not list(root.glob('data/generation_requests/*/generation_request_v1.json'))
            else:
                task=advance(runtime,bid)['task']['task_id']
                if scenario=='unknown_mix':
                    def lose_response(command,*args,**kwargs):
                        if len(command)>1 and Path(command[1]).name=='resolve_generation_content_plan_v1.py':
                            command=[command[0],str(PROJECT/'internal-console/tests/batch_provider_fault.py'),
                                'before-response',str(PROJECT/'ops-pipeline/tests/creative_style_synthetic.py'),
                                'plan',str(root),rid]
                        return external_boundaries(command,*args,**kwargs)
                    with patch.object(subprocess,'run',lose_response):runner._run(task)
                    assert get_task(runtime.database_path,task)['status']=='failed'
                elif scenario!='queued_mix':
                    with patch.object(subprocess,'run',external_boundaries):
                        runner._run(task)
                        task=advance(runtime,bid)['task']['task_id'];runner._run(task)
                    assert get_task(runtime.database_path,task)['status']=='completed'
                    batch=read(root/'data/generation_batches'/rid/'generation_batch_v1.json')
                    post(client,'/api/create/'+rid+'/review',headers,{'items':[
                        {'content_id':c['content_id'],'decision':'approved' if scenario=='closed_mix' and i==0 else 'rejected'}
                        for i,c in enumerate(batch['contents'])]})
                    if scenario=='closed_mix':
                        template=root/'output/素材混剪&数字人口播混剪文案导入模板.xlsx'
                        template.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copyfile(PROJECT/'ops-pipeline/output'/template.name,template)
                        export_task=post(client,'/api/create/'+rid+'/export-mix',headers)['task']['task_id']
                        runner._run(export_task)
                        assert get_task(runtime.database_path,export_task)['status']=='completed',get_task(runtime.database_path,export_task)
            before={p:p.read_bytes() for p,_ in quality.events(root,business['business_id'],rid)}
            request=root/'data/generation_requests'/rid/'generation_request_v1.json'
            request_bytes=request.read_bytes() if request.is_file() else None
            if scenario in ('journal_novel','queued_mix','unknown_mix'):
                ended=post(client,'/api/create/batches/'+bid+'/control',headers,{'action':'end','operation_id':'end_known_scope'})
                settlements=ended['result']['settlements']
            else:
                advance(runtime,bid)
                settlements=native.settle(root,bid)
            chain=quality.events(root,business['business_id'],rid)
            if scenario=='unknown_mix':
                assert chain[-1][1]['event']=='reserved',settlements
                assert not request.with_name('generation_request_resolution_v1.json').is_file()
                assert state(runtime,bid,context)['counts']['unknown']==2
                calls=root/'data/metrics/generation_requests'/rid/'style_synthetic_planning_calls.jsonl'
                assert len(calls.read_text().splitlines())==1
            else:
                expected='consumed_by_native_closure' if scenario=='closed_mix' else 'safely_released'
                assert chain[-1][1]['event']==expected,settlements
                assert quality.pending(root,business['business_id'])==[]
                for _ in range(2):native.settle(root,bid)
                assert len(quality.events(root,business['business_id'],rid))==len(chain)
                with pytest.raises(RuntimeError) as error:
                    quality.reserve_concepts(root,business['business_id'],rid,[],chain[0][1]['source_refs'][0])
                assert error.value.code=='CONTENT_INTENT_SETTLED'
            if scenario=='queued_mix':
                assert get_task(runtime.database_path,task)['status']=='failed'
                assert get_task(runtime.database_path,task)['error_code']=='CREATION_BATCH_ENDED'
                runner._run(task)
                assert not list(root.glob('data/metrics/generation_requests/*/style_synthetic_planning_calls.jsonl'))
            if scenario=='journal_novel':
                preview=post(client,'/api/create/novel-news/preview',headers,{k:business[k] for k in ('business_id','speaker_id')})['projection']
                opportunity=next(c for c in preview['opportunities'] if c['novelty_status']=='novel')
                created=post(client,'/api/create/confirm',headers,{**{k:business[k] for k in ('business_id','speaker_id')},
                    'profile':'news','requested_quantity':1,'confirmed_quantity':1,'idempotency_key':'new_after_explicit_end',
                    'selected_opportunity_id':opportunity['concept_id']})
                assert created['result']['request_id']!=rid
                assert not request.exists()
            if request_bytes is not None:assert request.read_bytes()==request_bytes
            assert all(path.read_bytes()==data for path,data in before.items())
            ledger=root/'data/content_ledgers'/business['business_id']/'content_ledger_v1.json'
            if scenario=='closed_mix':
                saved=file_sha(ledger)
                assert len(read(ledger)['entries'])==1
                replay=post(client,'/api/create/'+rid+'/export-mix',headers)
                assert replay['task']['task_id']==export_task and file_sha(ledger)==saved
                proof_ref=next(r for r in chain[-1][1]['native_evidence_refs'] if r['owner']=='native-quality-settlement')
                proof_path=io_path(Path(proof_ref['path']));original=proof_path.read_bytes()
                try:
                    proof_path.write_bytes(original+b'\n')
                    with pytest.raises(RuntimeError):quality.pending(root,business['business_id'])
                finally:proof_path.write_bytes(original)
                assert quality.pending(root,business['business_id'])==[] and file_sha(ledger)==saved
            else:assert not ledger.exists()
        finally:runner.close()
