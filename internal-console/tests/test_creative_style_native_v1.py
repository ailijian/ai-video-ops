"""B1: original Native owners and authentic isolated approvals; synthetic provider only."""
import json
import shutil
import subprocess
import uuid
import pytest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from compatibility_golden_support import prepare_native_golden, prepare_native_business
from test_profile_compatibility_release_v1_1 import committed_source_snapshot
from profile_compatibility_release_v1_1 import configure_runtime
from profile_compatibility_decisions_v1_1 import read, file_sha
from app.main import build_app
from app.background_task_service import BackgroundTaskRunner
from app.task_service import get_task
from publish_copy_native_support import post, generation, confirm, worker, current
from test_publish_copy_native_v1 import install_templates

PROJECT = Path(__file__).resolve().parents[2]


EVENT='有一次顾客下单时注明不吃香菜，店主小周核对备注后按单配菜，制作后标记餐盒。'


def style_runtime(node,style_name='persona',*,story_events=None):
    prepare_native_golden(node)
    if style_name=='conversion':
        from news_golden_support_v1_2 import prepare_news_business
        business=prepare_news_business(node)
    elif style_name=='story':
        business=prepare_native_business(node,story_event=None if story_events else EVENT,story_events=story_events,speaker_type='owner_founder')
    else:business = prepare_native_business(node)
    settings, _, storage = node
    root = settings.pipeline_root
    # A ready native Business/Speaker cannot grant an activated Style scope.
    rejected = business['client'].post('/api/create/confirm', headers=business['headers'], json={
        'business_id':business['business_id'], 'speaker_id':business['speaker_id'], 'profile':'mix',
        'requested_quantity':1, 'confirmed_quantity':1, 'idempotency_key':'style_before_release', 'creative_style_id':'persona'})
    assert rejected.status_code==409 and rejected.json()['detail']['code']=='CREATIVE_STYLE_QUALIFICATION_REQUIRED',rejected.text
    assert not list(root.glob('data/generation_requests/*/generation_request_v1.json'))
    approved_product = settings.repo_root / 'docs/deliveries/creation-batch-ux-1/BASELINE.md'
    approved_product.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PROJECT/'docs/deliveries/creation-batch-ux-1/BASELINE.md', approved_product)
    repo, owner = committed_source_snapshot(PROJECT, storage / 's', complete=True)
    configure_runtime(root, root, purpose='isolated-validation')
    package = owner.build_release(root, storage / 'p', repo, contract_version='1.1', purpose='isolated-validation')
    owner.verify_release(package, repo)
    staged = owner.stage_release_v1_1(package, root, repo)
    owner.activate_release_v1_1(root, repo, staged, uuid.uuid4().hex)
    runtime = replace(settings, publish_copy_enabled=True, pipeline_python_executable=str(PROJECT / 'ops-pipeline/.venv/Scripts/python.exe'))
    return runtime, business


@pytest.mark.parametrize('provider_failure',[False,True])
@pytest.mark.parametrize('style_name',['persona','story','conversion'])
def test_persona_native_request_review_publish_delivery_and_negative(node,provider_failure,style_name):
    runtime, business = style_runtime(node,style_name)
    root = runtime.pipeline_root
    install_templates(root)
    with TestClient(build_app(runtime)) as client:
        login = post(client, '/api/auth/login', {}, {'phone':'13900000001', 'password':'SyntheticCase2026!'})
        headers = {'X-CSRF-Token': login['csrf_token']}
        body = {k: business[k] for k in ['business_id','speaker_id']}
        body.update(profile='mix', requested_quantity=1, confirmed_quantity=1, idempotency_key='persona_native_once', creative_style_id=style_name)
        if style_name=='persona':
            rejected=client.post('/api/create/confirm',headers=headers,json={**body,'creative_style_id':'story'})
            assert rejected.status_code==409 and rejected.json()['detail']['code']=='CREATIVE_STYLE_EVENT_REQUIRED',rejected.text
        refused = client.post('/api/create/confirm', headers=headers, json={**body,'creative_style_id':'unknown'})
        assert refused.status_code == 409 and refused.json()['detail']['code'] == 'CREATIVE_STYLE_UNKNOWN', refused.text
        assert not list(root.glob('data/generation_requests/*/generation_request_v1.json'))
        configuration={'mode':'free','stage':'launch','quantities':{k:int(k==style_name) for k in ['novel','repurpose','persona','story','conversion']},
            'combinedTarget':None,'cycles':1,'cyclesConfirmed':False,'repurposeEnabled':False,'revision':0,'previewRevision':None}
        path='/api/create/configuration/'+business['business_id']
        assert client.get(path).json()=={'draft':None,'revision':0}
        saved=client.put(path,headers=headers,json={'revision':0,'payload':{'speaker_id':business['speaker_id'],'configuration':configuration}})
        assert saved.status_code==200,saved.text
        saved=saved.json()
        assert client.get(path).json()==saved
        assert client.put(path,headers=headers,json={'revision':0,'payload':saved['draft']}).json()['operation_id']==saved['operation_id']
        conflict=client.put(path,headers=headers,json={'revision':0,'payload':{**saved['draft'],'configuration':{**configuration,'revision':1}}})
        assert conflict.status_code==409 and conflict.json()['detail']['code']=='CREATIVE_STYLE_DRAFT_CONFLICT',conflict.text
        other=post(client,'/api/auth/login',{}, {'phone':'13900000002','password':'SyntheticCase2026!'})
        assert client.get(path).json()=={'draft':None,'revision':0}
        login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login['csrf_token']}
        assert client.get(path).json()==saved
        preview=post(client,'/api/create/capacity-preview',headers,{'business_id':business['business_id'],'speaker_id':business['speaker_id'],
            'profile':'mix','quantity':1,'creative_style_id':style_name,'configuration':configuration})['preview']['creative_style_preflight']
        assert preview['can_confirm'] and preview['no_mutation']
        assert not list(root.glob('data/creative_style_catalogs/*/catalog.json'))
        assert not list(root.glob('data/creation_batch_intents/*/*.json'))
        body.update(idempotency_key=saved['operation_id'],configuration=configuration,style_preflight_sha256=preview['source_configuration_sha256'])
        stale=client.post('/api/create/confirm',headers=headers,json={**body,'configuration':{**configuration,'revision':1}})
        assert stale.status_code==409 and stale.json()['detail']['code']=='CREATIVE_STYLE_PREFLIGHT_STALE',stale.text
        assert not list(root.glob('data/generation_requests/*/generation_request_v1.json'))
        rid = post(client, '/api/create/confirm', headers, body)['result']['request_id']
        displayed=client.get('/api/create/'+rid+'/delivery').json()['state']['creative_style']
        assert displayed['style_id']==style_name and displayed['style_version']=='1' and len(displayed['definition_sha256'])==64
        request = read(root / 'data/generation_requests' / rid / 'generation_request_v1.json')
        assert request['schema_version']=='generation-request-v1.1' and request['creative_style']['style_id']==style_name
        from creative_style_v1 import check, pinned
        intent=check(pinned(request['style_intent_ref']),'C02')
        confirmed=check(pinned(intent['batch_intent_ref']),'C03')
        assert intent['ordered_slots']==[rid+'-S001']==[v['slot_id'] for v in confirmed['slots']]
        assert confirmed['actual_target']==1 and confirmed['actor_intent']['actor_id']=='1'
        assert intent['business_id']==business['business_id']
        assert post(client, '/api/create/confirm', headers, body)['result']['request_id']==rid
        conflict = client.post('/api/create/confirm', headers=headers, json={**body,'creative_style_id':None})
        assert conflict.status_code==409, conflict.text
        post(client, '/api/create/'+rid+'/resolve-sources', headers)
        original = subprocess.run
        def transport(command,*args,**kwargs):
            mapping={'resolve_generation_content_plan_v1.py':'plan','resolve_generation_batch_v1.py':'generate'}
            if provider_failure:mapping['resolve_generation_batch_v1.py']='generate-invalid-persona'
            if len(command)>1 and Path(command[1]).name in mapping:
                command=[command[0], str(PROJECT/'ops-pipeline/tests/creative_style_synthetic.py'), mapping[Path(command[1]).name], str(root), rid]
            return original(command,*args,**kwargs)
        runner=BackgroundTaskRunner(runtime)
        try:
            with patch.object(subprocess,'run',transport):
                for operation in ['resolve-content-plan','generate-scripts']:
                    tid=post(client,'/api/create/'+rid+'/'+operation,headers)['task']['task_id']
                    runner._run(tid)
                    if provider_failure and operation=='generate-scripts':
                        task=get_task(runtime.database_path,tid)
                        expected={'persona':'CREATIVE_STYLE_FIRST_PERSON_UNSUPPORTED','story':'CREATIVE_STYLE_EVENT_REQUIRED','conversion':'CREATIVE_STYLE_CTA_SCOPE_INVALID'}[style_name]
                        assert task['status']=='failed' and task['error_code']==expected,task
                        assert not list(root.glob('data/generation_batches/*/generation_human_review_v2.json'))
                        calls=root/'data/metrics/generation_requests'/rid/'style_synthetic_provider_calls.jsonl'
                        assert len(calls.read_text('utf-8').splitlines())==1
                        candidate=root/'data/metrics/generation_requests'/rid/'script_generation_candidate_batch_v1.json'
                        assert candidate.is_file()
                        cached_sha=file_sha(candidate)
                        no_network="import socket,runpy,sys,pathlib; socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('External network forbidden')); sys.argv=sys.argv[1:]; sys.path.insert(0,str(pathlib.Path(sys.argv[0]).parent)); runpy.run_path(sys.argv[0],run_name='__main__')"
                        result=original([runtime.pipeline_python_executable,'-c',no_network,str(root/'scripts/resolve_generation_batch_v1.py'),
                            '--pipeline-root',str(root),'--request-id',rid],capture_output=True,text=True,encoding='utf-8')
                        output=json.loads(result.stdout.splitlines()[-1])
                        assert result.returncode==2 and output['code']==expected,result.stdout+result.stderr
                        assert len(calls.read_text('utf-8').splitlines())==1 and file_sha(candidate)==cached_sha
                        return
                    assert get_task(runtime.database_path,tid)['status']=='completed', get_task(runtime.database_path,tid)
            directory=root/'data/generation_batches'/rid
            batch=read(directory/'generation_batch_v1.json'); item=batch['contents'][0]
            assert batch['creative_style']==request['creative_style']==item['creative_style']
            slot=item['logical_slot_id']; assert slot==rid+'-S001'
            if style_name=='persona':assert '我亲自负责' in item['narration']
            elif style_name=='story':assert EVENT in item['narration']
            else:assert item['cta']['present'] is True and '不含配送' in item['narration']
            assert client.post('/api/create/'+rid+'/export-mix',headers=headers).status_code==409
            refused=client.post('/api/create/'+rid+'/review',headers=headers,json={'items':[{
                'content_id':item['content_id'],'decision':'revised','revised_title':item['title'],
                'revised_narration':'门店核对忌口，再按单配菜，制作后标记餐盒。'}]})
            assert refused.status_code!=200
            assert not (directory/'generation_human_review_v2.json').exists()
            post(client,'/api/create/'+rid+'/review',headers,{'items':[{'content_id':item['content_id'],'decision':'approved'}]})
            approved=read(directory/'approved_generation_batch_v1.json')
            assert approved['contents'][0]['logical_slot_id']==slot and approved['contents'][0]['creative_style']==request['creative_style']
            template=root/'output/素材混剪&数字人口播混剪文案导入模板.xlsx'; template.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(PROJECT/'ops-pipeline/output'/template.name,template)
            etid=post(client,'/api/create/'+rid+'/export-mix',headers)['task']['task_id']; runner._run(etid)
            assert get_task(runtime.database_path,etid)['status']=='completed',get_task(runtime.database_path,etid)
            ledger=root/'data/content_ledgers'/business['business_id']/'content_ledger_v1.json'
            ledger_sha=file_sha(ledger); assert len(read(ledger)['entries'])==1
            task=generation(client,headers,rid)['task']['task_id']; result=worker(runtime,task)
            assert result.returncode==0,(result.stdout,result.stderr)
            assert get_task(runtime.database_path,task)['status']=='completed',get_task(runtime.database_path,task)
            assert client.post('/api/create/'+rid+'/publish-copy/export',headers=headers).status_code!=200
            confirm(client,headers,rid)
            etid=post(client,'/api/create/'+rid+'/publish-copy/export',headers)['task']['task_id'];runner._run(etid)
            assert get_task(runtime.database_path,etid)['status']=='completed',get_task(runtime.database_path,etid)
            state=current(client,rid); assert state['delivery']['state']=='completed'
            assert client.get('/api/create/'+rid+'/publish-copy/excel/'+state['delivery']['delivery_id']).status_code==200
            assert post(client,'/api/create/'+rid+'/publish-copy/export',headers)['accepted'] is False
            assert file_sha(ledger)==ledger_sha
            rejected=client.post('/api/create/confirm',headers=headers,json={**body,'configuration':{'mode':'free','quantities':1}})
            assert rejected.status_code==409 and rejected.json()['detail']['code']=='CREATIVE_STYLE_CONFIGURATION_INVALID',rejected.text
            assert file_sha(ledger)==ledger_sha
        finally:runner.close()


@pytest.mark.parametrize('point',['permission_snapshot.json','confirmed_intent.json'])
def test_partial_confirmation_recovers_after_relogin_without_rewriting_history(node,point):
    runtime,business=style_runtime(node);root=runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        def login():
            value=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
            return {'X-CSRF-Token':value['csrf_token']}
        headers=login()
        body={'business_id':business['business_id'],'speaker_id':business['speaker_id'],'profile':'mix',
              'requested_quantity':1,'confirmed_quantity':1,'idempotency_key':'partial_native_once','creative_style_id':'persona'}
        for value in [1,['novel','repurpose','persona','story','conversion']]:
            response=client.post('/api/create/confirm',headers=headers,json={**body,'configuration':{'mode':'free','quantities':value}})
            assert response.status_code==409 and response.json()['detail']['code']=='CREATIVE_STYLE_CONFIGURATION_INVALID',response.text
        original=subprocess.run
        def fault(command,*args,**kwargs):
            if len(command)>1 and Path(command[1]).name=='generation_request_handoff_v1.py':
                command=[command[0],str(PROJECT/'internal-console/tests/creative_style_confirmation_fault.py'),point,*command[1:]]
            return original(command,*args,**kwargs)
        with patch.object(subprocess,'run',fault):
            response=client.post('/api/create/confirm',headers=headers,json=body)
        assert response.status_code!=200
        assert not list(root.glob('data/generation_requests/*/generation_request_v1.json'))
        permission=next(root.glob('data/creation_batch_intents/*/permission_snapshot.json'))
        directory=permission.parent
        retained={p.name:file_sha(p) for p in directory.glob('*.json')}
        assert point in retained
        headers=login()  # New session, same stable principal and authorization.
        rid=post(client,'/api/create/confirm',headers,body)['result']['request_id']
        assert rid==directory.name
        assert all(file_sha(directory/name)==sha for name,sha in retained.items())
        assert post(client,'/api/create/confirm',headers,body)['result']['request_id']==rid
        rejected=client.post('/api/create/confirm',headers=headers,json={**body,'configuration':{'mode':'free','quantities':1}})
        assert rejected.status_code==409 and rejected.json()['detail']['code']=='CREATIVE_STYLE_CONFIGURATION_INVALID',rejected.text
        assert len(list(root.glob('data/generation_requests/*/generation_request_v1.json')))==1
        # Reverse legacy->Style replay is rejected before any Style-only access.
        other=prepare_native_business(node,customer_name='反向重放保护（全虚构）')
        legacy={**body,'business_id':other['business_id'],'speaker_id':other['speaker_id'],
                'idempotency_key':'legacy_then_style','creative_style_id':None}
        legacy_rid=post(client,'/api/create/confirm',headers,legacy)['result']['request_id']
        legacy_path=root/'data/generation_requests'/legacy_rid/'generation_request_v1.json'
        legacy_sha=file_sha(legacy_path)
        rejected=client.post('/api/create/confirm',headers=headers,json={**legacy,'creative_style_id':'persona'})
        assert rejected.status_code==409 and rejected.json()['detail']['code']=='GENERATION_IDEMPOTENCY_CONFLICT',rejected.text
        assert file_sha(legacy_path)==legacy_sha
