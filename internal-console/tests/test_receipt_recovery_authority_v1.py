import json,subprocess,uuid,hashlib,importlib.util
from pathlib import Path
from receipt_recovery_support import native_flow,node,PROJECT
from compatibility_golden_support import prepare_native_business
from profile_compatibility_decisions_v1_1 import decision_graph,read
from profile_compatibility_release_v1_1 import effective_runtime
from test_profile_compatibility_v1_1 import request as decision_request
from app.database import connect

def inventory(directory):
    return {p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}

def test_withdraw_reapprove_and_reactivate_cannot_revive_old_open_operations(node):
    with native_flow(node) as flow:
        root=flow['root'];client=flow['client'];headers=flow['headers'];settings=flow['settings']
        human=flow['request']();flow['review'](human,'approved')
        second=prepare_native_business(node,customer_name='明禾版本核对（全虚构）')
        export=flow['request'](second);flow['review'](export)
        flow['faults']['export_mix_excel_v1.py']='export_receipt'
        failed=flow['run'](export['prefix'],'/export-mix');assert failed['status']=='failed'
        intent=read(export['directory']/'generation_export_intent_v1.json');excel=root/intent['output_path']
        assert excel.with_suffix('.export_receipt.json').is_file()
        assert not (export['directory']/'generation_export_closure_v1.json').exists()
        before={**inventory(human['directory']),**inventory(export['directory'])}
        original_binding=effective_runtime(root)['binding']
        target=next(v['target'] for v in decision_graph(root)['heads'].values())
        reviewer,review_headers,_=node[1]['C']
        def decide(action):
            op=uuid.uuid4().hex
            preview=reviewer.post('/api/profile-compatibility/preview',headers=review_headers,json={
                'operation_id':op,'decisions':[decision_request(target,decision_graph(root),action)]})
            assert preview.status_code==200,preview.text
            result=reviewer.post('/api/profile-compatibility/confirm',headers=review_headers,json={
                'operation_id':op,'preview_sha256':preview.json()['preview_ref']['sha256']})
            assert result.status_code==200,result.text
        db=connect(settings.database_path)
        try:count=db.execute('SELECT count(*) FROM tasks').fetchone()[0]
        finally:db.close()
        traces=[]
        def blocked(phase):
            outputs={}
            for stage,url,body in [('generation',human['prefix']+'/generation-recovery/confirm',human['retry_body']),
                                   ('review',human['prefix']+'/review',human['human_body']),
                                   ('export',export['prefix']+'/export-mix',None)]:
                response=client.post(url,headers=headers,**({'json':body} if body else {}))
                assert response.status_code in {409,503},response.text
                outputs[stage]={'http':response.status_code,'code':response.json()['detail']['code']}
            command=[settings.pipeline_python_executable,str(root/'scripts/close_generation_export_v1.py'),
                '--pipeline-root',str(root),'--request-id',export['rid'],'--excel',str(excel)]
            closure=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',env=flow['environment'])
            # The Native CLI now emits its bounded machine error rather than
            # exposing an internal Compatibility traceback on stderr.
            rejected=json.loads(closure.stdout)
            assert closure.returncode!=0 and rejected['ok'] is False,closure.stdout+closure.stderr
            assert rejected['code']=='PROFILE_COMPATIBILITY_BLOCKED',rejected
            assert {**inventory(human['directory']),**inventory(export['directory'])}==before
            db=connect(settings.database_path)
            try:assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==count
            finally:db.close()
            assert not (root/'data/content_ledgers'/second['business_id']/'content_ledger_v1.json').exists()
            traces.append({'phase':phase,'writers':outputs,'closure_returncode':closure.returncode,'tasks_unchanged':True})
        decide('withdraw');blocked('withdrawn')
        decide('approve');blocked('reapproved_not_published')
        spec=importlib.util.spec_from_file_location('receipt_release_owner',PROJECT/'deploy/creative-authority/authority_release.py')
        owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)
        repo=node[2]/'s'
        package=owner.build_release(root,node[2]/'new-package',repo,contract_version='1.1',purpose='isolated-validation',parent_release=original_binding['release_ref'])
        owner.verify_release(package,repo)
        staged=owner.stage_release_v1_1(package,root,repo);owner.activate_release_v1_1(root,repo,staged,uuid.uuid4().hex)
        owner.preflight(root,repo)
        assert effective_runtime(root)['binding']!=original_binding
        blocked('new_release_active_old_request_still_pinned')
        (root.parent/'receipt-authority-fences.json').write_text(json.dumps(traces,indent=2),encoding='utf-8')

def test_independent_memory_change_during_transport_and_private_business_scope(node):
    with native_flow(node) as flow:
        value=flow['request'](retry=False);root=flow['root'];flow['memory_race'].add(value['rid'])
        result=flow['run'](value['prefix'],'/generation-recovery/confirm',value['retry_body'])
        assert result['status']=='failed'
        directory=value['directory'];op=directory/'recovery'/value['retry_body']['operation_id']
        assert read(op/'result.json')['outcome']=='blocked'
        state=flow['client'].get(value['prefix']+'/delivery').json()['state']
        assert not state['generation']['ready_for_human_review']
        assert not (directory/'generation_batch_approval_receipt.json').exists()
        ledger=root/'data/content_ledgers'/flow['business']['business_id']/'content_ledger_v1.json'
        assert read(ledger)['entries']==[]  # Negative disturbance grants no exposure or approval.
        second=prepare_native_business(node,customer_name='独立客户资料核对（全虚构）')
        response=flow['client'].post('/api/create/confirm',headers=flow['headers'],json={
            'business_id':second['business_id'],'speaker_id':second['speaker_id'],'profile':'mix',
            'requested_quantity':1,'confirmed_quantity':1,'idempotency_key':'private_business_boundary'})
        assert response.status_code==200,response.text
        rid=response.json()['result']['request_id'];request=read(root/'data/generation_requests'/rid/'generation_request_v1.json')
        assert request['persona_id']==second['business_id'] and request['speaker_persona']==second['speaker_id']
        assert flow['client'].post('/api/create/'+rid+'/resolve-sources',headers=flow['headers']).status_code==200
        plan=read(root/'data/production_plans'/rid/'generation_source_plan_v1.json')
        assert flow['business']['business_id'] not in json.dumps(plan,ensure_ascii=False)
        assert not (root/'data/content_ledgers'/second['business_id']/'content_ledger_v1.json').exists()
        context=flow['client'].get('/api/create/request-context',params={'request_id':rid,'business_id':flow['business']['business_id'],'mode':'mix'})
        assert context.status_code==503 and context.json()['detail']['code']=='REQUEST_BUSINESS_MISMATCH',context.text
        (root.parent/'receipt-memory-private-business.json').write_text(json.dumps({'request':value['rid'],
            'during_transport_memory_mutation':'independent negative fixture, not an approved Ledger event',
            'ready':False,'approval_created':False,'private_business_request':rid,'private_sources_separate':True,
            'mismatched_business_http':context.status_code},indent=2),encoding='utf-8')
