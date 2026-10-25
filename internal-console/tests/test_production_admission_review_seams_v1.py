"""CR-001/002/003: actual CLI, Native history across release, and K=2 admission.

All data are fictional. Only external generation/analysis transports are
synthetic; approvals, release, Native Requests, review, exports and Ledger are
the real owners. No fixture outcome may be transported as production Authority.
"""
import json,os,subprocess,uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from test_case_library_security_v1 import node as security_node
from test_news_novel_runtime_v1_2 import native_news_runtime
from test_news_qualification_complete_v1_2 import novel_flow,repurpose_flow,native_task
from test_news_generation_recovery_v1 import worker
from test_production_creation_native_v1 import activate_fixture,new_business,PROJECT
from test_production_admission_v1 import scope
from news_golden_support_v1_2 import prepare_news_business
from human_review_operations_v1 import read,file_sha,io_path
from profile_compatibility_release_v1_1 import effective_runtime
from profile_compatibility_release_v1_3 import historical_bundle_root
from app.main import build_app
from app.creation_batch_gateway import admit_group,advance,state
from app.canonical_gateway import CanonicalOperationError
from app.background_task_service import BackgroundTaskRunner
from app.task_service import get_task
from test_creation_batch_orchestration_v1 import external_boundaries
from test_creation_batch_capacity_v2 import EVENTS as FIVE_EVENTS
from app.database import connect
from test_creation_batch_native_v1 import config
import native_batch_v1 as native


def recover_closure_task(client,headers,runtime,response):
    """Real failed Task/HTTP resume; fault only after Native Closure write."""
    assert response.status_code==200,response.text
    tid=response.json()['task']['task_id'];task=get_task(runtime.database_path,tid)
    operation=task['payload']['operation'];novel=operation=='novel_news_export'
    assert operation in ('novel_news_export','news_export')
    rid=task['subject_ref'];kind='novel' if novel else 'repurpose'
    url=('/api/create/novel-news/' if novel else '/api/create/news/')+rid
    real_run=subprocess.run
    def interrupted(command,*args,**kwargs):
        if len(command)>2 and Path(command[1]).name in ('novel_news_v1.py','news_delivery_v1.py') and 'export' in command:
            command=[command[0],str(PROJECT/'internal-console/tests/news_export_process_fault.py'),
                str(runtime.pipeline_root),rid,kind,'closure']
        return real_run(command,*args,**kwargs)
    runner=BackgroundTaskRunner(runtime)
    try:
        with patch.object(subprocess,'run',interrupted):runner._run(tid)
        assert get_task(runtime.database_path,tid)['status']=='failed'
        status=client.get(url+('/state' if novel else '/delivery'))
        assert status.status_code==200,status.text
        projected=status.json()['state']
        assert projected['export_recovery_state']=='ledger_seal_pending' if novel else not projected['stop_point_reached']
        assert client.get(url+'/excel').status_code!=200
        with connect(runtime.database_path) as db:before=db.execute('SELECT count(*) FROM tasks').fetchone()[0]
        replay=client.post(url+'/export',headers=headers)
        assert replay.status_code==200,replay.text
        assert replay.json()['accepted'] and replay.json()['task']['task_id']==tid
        runner._run(tid)
        assert get_task(runtime.database_path,tid)['status']=='completed',get_task(runtime.database_path,tid)
        with connect(runtime.database_path) as db:assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==before
    finally:runner.close()
    return tid


def export_novel(client,headers,runtime,business,key,*,closure_recovery=False):
    preview=client.post('/api/create/novel-news/preview',headers=headers,
        json={k:business[k] for k in ('business_id','speaker_id')})
    assert preview.status_code==200,preview.text
    eligible=[c for c in preview.json()['projection']['opportunities']
        if c['novelty_status']=='novel' and c['production_feasibility']['status']=='supported']
    assert eligible
    body={**{k:business[k] for k in ('business_id','speaker_id')},'profile':'news',
        'requested_quantity':1,'confirmed_quantity':1,'idempotency_key':key,
        'selected_opportunity_id':eligible[0]['concept_id']}
    created=client.post('/api/create/confirm',headers=headers,json=body)
    assert created.status_code==200,created.text
    rid=created.json()['result']['request_id'];url='/api/create/novel-news/'+rid
    assert client.post('/api/create/'+rid+'/resolve-sources',headers=headers).status_code==200
    response=client.post(url+'/generate',headers=headers);assert response.status_code==200,response.text
    task=response.json()['task']['task_id'];run=worker(runtime,task,'success')
    assert run.returncode==0,run.stderr
    plan=read(runtime.pipeline_root/'data/generation_batches'/rid/'novel_news_beat_plan_v1.json')
    assert client.get(url+'/excel').status_code!=200
    reviewed=client.post(url+'/review',headers=headers,json={
        'decisions':[{'beat_id':b['beat_id'],'decision':'approved'} for b in plan['micro_information_beats']]})
    assert reviewed.status_code==200,reviewed.text
    response=client.post(url+'/export',headers=headers)
    if closure_recovery:recover_closure_task(client,headers,runtime,response)
    else:native_task(runtime,response)
    assert client.get(url+'/excel').status_code==200
    return rid


def test_cli_news_refs_historical_ledger_after_successor_and_three_native_groups(node):
    runtime,business,_,repo,owner=native_news_runtime(node,mixed=True)
    source=runtime.pipeline_root;settings,_,storage=node
    with TestClient(build_app(runtime)) as client:
        login=client.post('/api/auth/login',json={'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login.json()['csrf_token']}
        _,nref=novel_flow(client,headers,runtime,business)
        historical=prepare_news_business(node,customer_name='生产命令改编资格（全虚构）')
        _,rref=repurpose_flow(client,headers,runtime,historical)
    refs=storage/'validation-refs.json';refs.write_text(json.dumps([nref,rref]),encoding='utf-8')
    scope_file=storage/'production-scope.json';scope_file.write_text(json.dumps(scope(
        profiles=['mix','news'],creative_styles=['conversion','persona','story'],
        news_reuse_intents=['cross_profile_repurpose','novel_content'])),encoding='utf-8')
    op=uuid.uuid4().hex;cli=PROJECT/'deploy/creative-authority/review_production_admission.py'
    base=['--pipeline-root',str(source),'--database',str(settings.database_path),
        '--repo-root',str(repo),'--user-id','3','--operation-id',op]
    env={k:v for k,v in os.environ.items() if not k.startswith(('DEEPSEEK_','QYAPI_'))}
    def invoke(action,*args):
        run=subprocess.run([str(PROJECT/'internal-console/.venv/Scripts/python.exe'),'-B',str(cli),
            action,*base,*args],capture_output=True,text=True,encoding='utf-8',env=env,timeout=120)
        assert run.returncode==0,run.stdout+run.stderr
        value=json.loads(run.stdout);assert value['ok'];return value
    preview=invoke('preview','--scope',str(scope_file),'--news-validation-refs',str(refs),
        '--reason','Explicit Native production seam review, fictional sources only')
    decision=invoke('confirm','--expected-preview-sha256',preview['preview_ref']['sha256'])
    assert invoke('confirm','--expected-preview-sha256',preview['preview_ref']['sha256'])['recovered']
    package=owner.build_release(source,storage/'seam-pack',repo,contract_version='1.3',purpose='production',
        production_admission_ref=decision['decision_ref'])
    with contextmanager(security_node.__wrapped__)(storage/'seam-runtime') as prod_node:
        production,staged=activate_fixture(prod_node,source,repo,owner,package);root=production.pipeline_root
        b=new_business(prod_node)
        with TestClient(build_app(production)) as client:
            login=client.post('/api/auth/login',json={'phone':'13900000001','password':'SyntheticCase2026!'})
            headers={'X-CSRF-Token':login.json()['csrf_token']}
            first=export_novel(client,headers,production,b,'before_successor',closure_recovery=True)
            rep=prepare_news_business(prod_node,customer_name='历史呈现保留（全虚构）')
            import test_news_qualification_complete_v1_2 as qualification
            original_task=qualification.native_task
            def recovery_task(settings,response):
                task=get_task(settings.database_path,response.json()['task']['task_id'])
                if task['payload']['operation']=='news_export':return recover_closure_task(client,headers,settings,response)
                return original_task(settings,response)
            with patch.object(qualification,'native_task',recovery_task):
                repurpose_id,_=repurpose_flow(client,headers,production,rep,key='before_successor_repurpose',record_isolated_evidence=False)
            frozen=read(root/'data/generation_requests'/first/'generation_request_v1.json')['profile_compatibility_v1_2']
            past_bundle=historical_bundle_root(root,frozen)
            protected={p:io_path(p).read_bytes() for p in root.glob('data/**/*receipt*.json')}
            before=read(root/'data/content_ledgers'/b['business_id']/'content_ledger_v1.json')['entries']
            successor=owner.build_release(source,storage/'successor-pack',repo,contract_version='1.3',purpose='production',
                production_admission_ref=decision['decision_ref'],parent_release=staged)
            next_ref=owner.stage_release_v1_1(successor,root,repo)
            owner.activate_release_v1_1(root,repo,next_ref,uuid.uuid4().hex)
            with pytest.raises(RuntimeError):effective_runtime(root,pinned=frozen)
            from news_export_recovery_v1 import bound_source_paths
            with pytest.raises(RuntimeError):bound_source_paths(root,{'authority_binding':frozen})
            assert historical_bundle_root(root,frozen)==past_bundle
            import ledger_history_v1 as ledger
            for business_id in (b['business_id'],rep['business_id']):
                for path,event in ledger.graph(root,business_id):ledger.validate_sealed_transition(root,path,event)
            # Console's sealed Reader does not import workbook dependencies.
            # The mutating Pipeline still performs the complete XLSX validator.
            def full_history_check():
                program=('import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'
                    'import ledger_history_v1 as h;r=Path(sys.argv[2]);'
                    '[(h.validate_transition(r,p,e)) for b in sys.argv[3:] for p,e in h.graph(r,b)]')
                checked=subprocess.run([str(PROJECT/'ops-pipeline/.venv/Scripts/python.exe'),'-B','-c',program,
                    str(PROJECT/'ops-pipeline/scripts'),str(root),b['business_id'],rep['business_id']],
                    capture_output=True,text=True,encoding='utf-8',env=env,timeout=120)
                assert checked.returncode==0,checked.stderr
            full_history_check()
            from novel_news_v1 import novel_news_status,validate_novel_news_export
            from news_delivery_v1 import status_news_delivery,validate_news_delivery_export
            status=novel_news_status(pipeline_root=root,request_id=first)
            assert status['stage']=='completed'
            assert status['generation']['artifact_present'] and status['generation']['ready_for_human_review']
            assert status['generation']['operation_id'] and status['generation']['intent_sha256']
            relative=os.path.relpath(root,Path.cwd())
            assert novel_news_status(pipeline_root=Path(relative),request_id=first)==status
            assert status_news_delivery(pipeline_root=root,request_id=repurpose_id)['exported']
            assert validate_novel_news_export(pipeline_root=root,request_id=first)['request_id']==first
            assert validate_news_delivery_export(pipeline_root=root,request_id=repurpose_id)['request_id']==repurpose_id
            with connect(production.database_path) as db:tasks_before=db.execute('SELECT count(*) FROM tasks').fetchone()[0]
            for rid,url in ((first,'/api/create/novel-news/'),(repurpose_id,'/api/create/news/')):
                replay=client.post(url+rid+'/export',headers=headers)
                assert replay.status_code==200 and not replay.json()['accepted'],replay.text
                assert client.get(url+rid+'/excel').status_code==200
            with connect(production.database_path) as db:assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==tasks_before
            second=export_novel(client,headers,production,b,'after_successor')
            assert first!=second
            after=read(root/'data/content_ledgers'/b['business_id']/'content_ledger_v1.json')['entries']
            assert after[:len(before)]==before and len(after)==len(before)+1
            mix_source=read(root/'data/content_ledgers'/rep['business_id']/'content_ledger_v1.json')['entries'][0]['batch_ref']
            # A complete Mix workbook/anchor read runs in the declared Pipeline
            # environment, as it does for the production Native consumer.
            program=('import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'
                'from close_generation_export_v1 import verify_generation_export_anchor;'
                'verify_generation_export_anchor(pipeline_root=Path(sys.argv[2]),request_id=sys.argv[3])')
            anchor_check=subprocess.run([str(PROJECT/'ops-pipeline/.venv/Scripts/python.exe'),'-B','-c',program,
                str(PROJECT/'ops-pipeline/scripts'),str(root),mix_source],
                capture_output=True,text=True,encoding='utf-8',env=env,timeout=120)
            assert anchor_check.returncode==0,anchor_check.stderr
            for path,event in ledger.graph(root,rep['business_id']):ledger.validate_sealed_transition(root,path,event)
            full_history_check()
            manifest=root/frozen['release_ref']['path'];old=io_path(manifest).read_bytes()
            try:
                io_path(manifest).write_bytes(old+b' ')
                with pytest.raises(RuntimeError):historical_bundle_root(root,frozen)
            finally:io_path(manifest).write_bytes(old)
            assert all(io_path(p).read_bytes()==value for p,value in protected.items())
            grouped_business=new_business(prod_node,story_events=FIVE_EVENTS)
            body={**{k:grouped_business[k] for k in ('business_id','speaker_id')},
                'operation_id':'production_five_same_style','configuration':config(story=5)}
            response=client.post('/api/create/batches/preview',headers=headers,json=body)
            assert response.status_code==200,response.text
            sha=response.json()['preview']['source_configuration_sha256']
            response=client.post('/api/create/batches/confirm',headers=headers,json={**body,'preflight_sha256':sha})
            assert response.status_code==200,response.text
            bid=response.json()['result']['batch_id'];groups=native.groups(root,bid)
            assert [len(g['slots']) for g in groups]==[2,2,1]
            context=read(native.directory(root,bid)/'permission.json');ids=[]
            first_group=admit_group(production,bid,groups[0]['group_id'],context)
            with pytest.raises(CanonicalOperationError) as blocked:
                admit_group(production,bid,groups[1]['group_id'],context)
            assert blocked.value.code=='CREATION_BATCH_DISPATCH_OCCUPIED'
            runner=BackgroundTaskRunner(production)
            try:
                with patch.object(subprocess,'run',external_boundaries):
                    for _ in range(6):
                        next_step=advance(production,bid)
                        tid=next_step['task']['task_id'];runner._run(tid)
                        assert get_task(production.database_path,tid)['status']=='completed',get_task(production.database_path,tid)
            finally:runner.close()
            actual=state(production,bid,context)
            assert actual['counts']['generated']==5 and actual['counts']['approved']==0
            for group in groups:
                result=admit_group(production,bid,group['group_id'],context);ids.append(result['request_id'])
                assert admit_group(production,bid,group['group_id'],context)['request_id']==result['request_id']
                request=read(native.request_path(root,result['request_id']))
                assert request['quantity']==len(group['slots']) and request['creative_style']['style_id']=='story'
            assert len(set(ids))==3
            # Terminal read is not a recovery writer: missing seals and altered
            # live Ledger bytes cannot be accepted as completed history.
            event_path=next(p for p,v in ledger.graph(root,b['business_id']) if v['request_id']==first)
            seal=event_path.with_name('receipt.json');seal_bytes=io_path(seal).read_bytes()
            try:
                io_path(seal).unlink()
                with pytest.raises((RuntimeError,OSError)):
                    validate_novel_news_export(pipeline_root=root,request_id=first)
            finally:io_path(seal).write_bytes(seal_bytes)
            ledger_path=ledger.ledger_path(root,b['business_id']);ledger_bytes=io_path(ledger_path).read_bytes()
            try:
                io_path(ledger_path).write_bytes(ledger_bytes+b' ')
                with pytest.raises(RuntimeError):validate_novel_news_export(pipeline_root=root,request_id=first)
            finally:io_path(ledger_path).write_bytes(ledger_bytes)
