"""B2 Native integration: fictional data; original qualification/HTTP/owners."""
from pathlib import Path
from dataclasses import replace
import subprocess
from unittest.mock import patch
import json
import pytest

from fastapi.testclient import TestClient

from app.main import build_app
from app.creation_batch_gateway import admit_group
from test_case_evidence_revision_v1 import node
from test_creative_style_native_v1 import style_runtime
from publish_copy_native_support import post
from human_review_operations_v1 import read
from creative_style_v1 import pinned, artifact
from operation_lock_v1 import operation_lock
import native_batch_v1 as native
from app.background_task_service import BackgroundTaskRunner
from app.task_service import get_task

PROJECT = Path(__file__).resolve().parents[2]
EVENTS = ['有一次顾客下单时注明不吃香菜，店主小周核对备注后按单配菜，制作后标记餐盒。',
          '曾经顾客来店询问蔬菜是否当天清洗，店主小周当场说明清洗安排并带顾客查看操作台。']


@pytest.mark.parametrize('point', ['before-response', 'after-response'])
def test_native_planning_response_crash_never_repeats_external_call(node, point):
    runtime, business = style_runtime(node)
    root = runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login = post(client, '/api/auth/login', {}, {'phone': '13900000001', 'password': 'SyntheticCase2026!'})
        headers = {'X-CSRF-Token': login['csrf_token']}
        body = {'business_id': business['business_id'], 'speaker_id': business['speaker_id'],
                'configuration': config(persona=1), 'operation_id': 'native_response_crash'}
        checked = post(client, '/api/create/batches/preview', headers, body)['preview']
        bid = post(client, '/api/create/batches/confirm', headers,
                   {**body, 'preflight_sha256': checked['source_configuration_sha256']})['result']['batch_id']
        context = read(native.directory(root, bid) / 'permission.json')
        group = native.groups(root, bid)[0]
        rid = admit_group(runtime, bid, group['group_id'], context)['request_id']
        post(client, '/api/create/' + rid + '/resolve-sources', headers)
        python = str(PROJECT / 'internal-console/.venv/Scripts/python.exe')
        helper = str(PROJECT / 'ops-pipeline/tests/creative_style_synthetic.py')
        fault = subprocess.run([python, str(PROJECT / 'internal-console/tests/batch_provider_fault.py'),
            point, helper, 'plan', str(root), rid], text=True, capture_output=True, timeout=90)
        assert fault.returncode == (91 if point == 'before-response' else 92), fault.stdout + fault.stderr
        calls = root / 'data/metrics/generation_requests' / rid / 'style_synthetic_planning_calls.jsonl'
        assert len(calls.read_text().splitlines()) == 1
        recovered = subprocess.run([python, helper, 'plan', str(root), rid], text=True,
                                   capture_output=True, timeout=90)
        if point == 'before-response':
            assert recovered.returncode == 2, recovered.stdout + recovered.stderr
            assert json.loads(recovered.stdout.splitlines()[-1])['code'] == 'CREATION_BATCH_OUTCOME_UNKNOWN'
            assert not (root / 'data/content_plans' / rid / 'content_plan_v1_1_1.json').exists()
        else:
            assert recovered.returncode == 0, recovered.stdout + recovered.stderr
            assert json.loads(recovered.stdout.splitlines()[-1])['remote_model_called'] is False
            assert list(native.directory(root, bid).glob('provider_stages/*/content_plan/*/response_saved.json'))
        assert len(calls.read_text().splitlines()) == 1


def config(**counts):
    return {'mode': 'free', 'stage': 'launch', 'quantities': {
        k: counts.get(k, 0) for k in native.TYPES}, 'revision': 0,
        'repurposeEnabled': bool(counts.get('repurpose')), 'cycles': 1,
        'cyclesConfirmed': False, 'combinedTarget': None, 'previewRevision': None}


def test_legacy_mix_pending_price_is_reserved_before_novel_admission(node):
    from test_news_novel_runtime_v1_2 import native_news_runtime
    from content_intent_reservations_v1 import pending
    runtime, business, _, _, _ = native_news_runtime(node, mixed=True)
    root = runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login = post(client, '/api/auth/login', {}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers = {'X-CSRF-Token':login['csrf_token']}
        initial = post(client, '/api/create/novel-news/preview', headers,
                       {k:business[k] for k in ('business_id','speaker_id')})['projection']
        assert initial['available_novel_count'] == 1
        rid = post(client, '/api/create/confirm', headers, {
            **{k:business[k] for k in ('business_id','speaker_id')}, 'profile':'mix',
            'requested_quantity':1, 'confirmed_quantity':1, 'idempotency_key':'legacy_pending_price'})['result']['request_id']
        post(client, '/api/create/'+rid+'/resolve-sources', headers)
        helper = str(PROJECT / 'internal-console/tests/batch_legacy_price_synthetic.py')
        for operation in ('plan', 'generate'):
            result = subprocess.run([str(PROJECT/'internal-console/.venv/Scripts/python.exe'), helper,
                operation, str(root), rid], text=True, capture_output=True, timeout=90)
            assert result.returncode == 0, result.stdout + result.stderr
        assert not list(root.glob('data/content_intent_reservations/*/*/events/*.json'))
        final = read(root/'data/content_plans'/rid/'content_plan_v1_1_1.json')['selected_concepts'][0]
        assert final['primary_fact_atom_refs'] == ['external-provider-invalid-primary-atom']
        held = pending(root, business['business_id'])
        assert len(held) == 1 and held[0]['primary_fact_atom_refs'] == final['material_information_gain_v1_1_1']['primary_fact_atom_refs']
        generated = read(root/'data/generation_batches'/rid/'generation_batch_v1.json')
        post(client, '/api/create/'+rid+'/review', headers, {'items':[
            {'content_id':item['content_id'], 'decision':'approved'} for item in generated['contents']]})
        # Completed Human source reads the pinned final plan, never a new
        # planning-memory snapshot or the provider's conflicting atom list.
        held = pending(root, business['business_id'])
        assert held[0]['primary_fact_atom_refs'] == final['material_information_gain_v1_1_1']['primary_fact_atom_refs']
        projected = post(client, '/api/create/novel-news/preview', headers,
                         {k:business[k] for k in ('business_id','speaker_id')})['projection']
        assert projected['available_novel_count'] == 0
        assert {v['novelty_status'] for v in projected['opportunities']} == {'reserved'}
        denied = client.post('/api/create/batches/preview', headers=headers, json={
            **{k:business[k] for k in ('business_id','speaker_id')}, 'configuration':config(novel=1),
            'operation_id':'must_not_reuse_legacy_pending'})
        assert denied.status_code == 409 and denied.json()['detail']['code'] == 'CREATION_BATCH_SOURCE_CAPACITY', denied.text
        assert not (root/'data/content_ledgers'/business['business_id']/'content_ledger_v1.json').exists()


@pytest.mark.parametrize('price_count', [1, 2])
def test_legacy_novel_selection_blocks_competing_hold_without_stranding_original(node, price_count):
    from test_news_novel_runtime_v1_2 import native_news_runtime
    from test_news_generation_recovery_v1 import create, worker
    from content_intent_reservations_v1 import pending
    prices = ['午餐套餐29元，仅限工作日到店自取，不含配送',
              '儿童小份餐15元，仅限周末店内点单，不参与工作日午餐套餐']
    runtime, business, _, _, _ = native_news_runtime(node, pricing_facts=prices[:price_count])
    root = runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login = post(client, '/api/auth/login', {}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers = {'X-CSRF-Token':login['csrf_token']}
        rid, task = create(client, headers, business, 'legacy_novel_pending')
        generated = worker(runtime, task, 'success')
        assert generated.returncode == 0, generated.stdout + generated.stderr
        assert get_task(runtime.database_path, task)['status'] == 'completed'
        assert len(pending(root, business['business_id'])) == 1
        body = {
            **{k:business[k] for k in ('business_id','speaker_id')}, 'configuration':config(novel=1),
            'operation_id':'cannot_claim_legacy_novel'}
        blocked = client.post('/api/create/batches/preview', headers=headers, json=body)
        if price_count == 1:
            assert blocked.status_code == 409 and blocked.json()['detail']['code'] == 'CREATION_BATCH_SOURCE_CAPACITY', blocked.text
        else:
            assert blocked.status_code == 200, blocked.text
            bid = post(client, '/api/create/batches/confirm', headers,
                {**body, 'preflight_sha256':blocked.json()['preview']['source_configuration_sha256']})['result']['batch_id']
            context = read(native.directory(root, bid) / 'permission.json')
            with pytest.raises(RuntimeError) as error:
                admit_group(runtime, bid, native.groups(root, bid)[0]['group_id'], context)
            assert error.value.code == 'CREATION_BATCH_ACTIVE_REQUEST_CONFLICT'
        assert not list(root.glob('data/content_intent_reservations/*/*/events/*.json'))
        state = client.get('/api/create/novel-news/'+rid+'/state')
        assert state.status_code == 200 and state.json()['state']['stage'] == 'review', state.text
        plan = read(root/'data/generation_batches'/rid/'novel_news_beat_plan_v1.json')
        post(client, '/api/create/novel-news/'+rid+'/review', headers, {'decisions':[
            {'beat_id':b['beat_id'], 'decision':'approved'} for b in plan['micro_information_beats']]})
        exported = post(client, '/api/create/novel-news/'+rid+'/export', headers)['task']['task_id']
        runner = BackgroundTaskRunner(runtime)
        try:
            runner._run(exported)
            assert get_task(runtime.database_path, exported)['status'] == 'completed', get_task(runtime.database_path, exported)
        finally:
            runner.close()
        assert pending(root, business['business_id']) == []


def test_confirmed_batch_style_k2_native_admission_identity_and_legacy_exclusion(node):
    runtime, business = style_runtime(node)
    root = runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login = post(client, '/api/auth/login', {}, {'phone': '13900000001', 'password': 'SyntheticCase2026!'})
        headers = {'X-CSRF-Token': login['csrf_token']}
        body = {'business_id': business['business_id'], 'speaker_id': business['speaker_id'],
                'configuration': config(persona=2), 'operation_id': 'native_batch_k_two'}
        preview = post(client, '/api/create/batches/preview', headers, body)['preview']
        assert preview['actual_target'] == 2 and preview['no_mutation']
        assert not list(root.glob('data/creation_batches/*/intent.json'))
        assert not list(root.glob('data/creative_style_catalogs/*/catalog.json'))
        body['preflight_sha256'] = preview['source_configuration_sha256']
        with operation_lock(root, 'authority_backup_gate'):
            blocked = client.post('/api/create/batches/confirm', headers=headers, json=body)
            assert blocked.status_code == 409 and blocked.json()['detail']['code'] == 'OPERATION_IN_PROGRESS', blocked.text
            assert not list(root.glob('data/creation_batches/*/intent.json'))
            assert not list(root.glob('data/creative_style_catalogs/*/catalog.json'))
        result = post(client, '/api/create/batches/confirm', headers, body)['result']
        bid = result['batch_id']
        assert post(client, '/api/create/batches/confirm', headers, body)['result'] == {'batch_id': bid, 'recovered': True}
        context = read(native.directory(root, bid) / 'permission.json')
        group = native.groups(root, bid)[0]
        from generation_request_handoff_v1 import _business_generation_lock
        with _business_generation_lock(root, business['business_id']):
            native.admission(root, bid, group['group_id'], context)
        # Crash window: canonical C04/hold exist, Native Request does not.
        assert not list(root.glob('data/generation_requests/*/generation_request_v1.json'))
        raced = client.post('/api/create/confirm', headers=headers, json={
            'business_id':business['business_id'], 'speaker_id':business['speaker_id'], 'profile':'mix',
            'requested_quantity':2, 'confirmed_quantity':2, 'idempotency_key':'must_not_overtake_admission'})
        assert raced.status_code == 409 and raced.json()['detail']['code'] == 'CREATION_BATCH_ADMISSION_IN_FLIGHT', raced.text
        import generation_request_handoff_v1 as owner
        original_create = owner.create_generation_request_handoff
        def crash_after_request(**kwargs):
            original_create(**kwargs)
            raise RuntimeError('Synthetic coordinator crash after real Native publication')
        with patch.object(owner, 'create_generation_request_handoff', crash_after_request):
            with pytest.raises(RuntimeError):
                admit_group(runtime, bid, group['group_id'], context)
        first = admit_group(runtime, bid, group['group_id'], context)
        second = admit_group(runtime, bid, group['group_id'], context)
        assert first['request_id'] == second['request_id'] == group['request_id']
        request = read(root / 'data/generation_requests' / first['request_id'] / 'generation_request_v1.json')
        assert request['schema_version'] == native.REQUEST_VERSION and request['quantity'] == 2
        outer = native.intent(root, bid)[1]
        expected_slots = [s['slot_id'] for s in outer['slots']]
        assert pinned(request['style_intent_ref'])['ordered_slots'] == expected_slots
        assert native.validate_admission(request['batch_admission_ref'], root=root, request=request)['ordered_slots'] == expected_slots
        admission_path = Path(request['batch_admission_ref']['path'])
        clone = root / 'copied-admission-negative.json'
        clone.write_bytes(admission_path.read_bytes())
        with pytest.raises(RuntimeError) as error:
            native.validate_admission(artifact(clone, 'native-request-admission', group['request_id'], 'native-batch-admission-v1.1'), root=root)
        assert error.value.code == 'CREATION_BATCH_IDENTITY_INVALID'
        # Corruption negatives in this disposable fixture exercise the real
        # reader; no approval or qualification writer is replaced.
        original_admission = admission_path.read_bytes()
        for field in ('source_refs', 'reservation_intent_ref'):
            forged = json.loads(original_admission)
            forged[field] = [forged['source_refs'][0]] if field == 'source_refs' else forged['source_refs'][0]
            admission_path.write_text(json.dumps(forged), encoding='utf-8')
            try:
                with pytest.raises(RuntimeError) as error:
                    native.validate_admission(artifact(admission_path, 'native-request-admission', group['request_id'], forged['schema_version']), root=root)
                assert error.value.code == 'CREATION_BATCH_IDENTITY_INVALID'
            finally:
                admission_path.write_bytes(original_admission)
        state = client.get('/api/create/batches/' + bid)
        assert state.status_code == 200, state.text
        assert not state.json()['state']['completion_proven']
        invalid = client.post('/api/create/batches/confirm', headers=headers,
            json={**body, 'configuration': config(persona=1)})
        assert invalid.status_code == 409 and invalid.json()['detail']['code'] == 'CREATION_BATCH_IDEMPOTENCY_CONFLICT'
        # A new legacy operation cannot adopt the styled batch Request.
        legacy = client.post('/api/create/confirm', headers=headers, json={
            'business_id': business['business_id'], 'speaker_id': business['speaker_id'],
            'profile': 'mix', 'requested_quantity': 2, 'confirmed_quantity': 2, 'idempotency_key': 'legacy_must_not_adopt'})
        assert legacy.status_code == 503 and legacy.json()['detail']['code'] == 'CONTENT_GENERATION_IN_FLIGHT', legacy.text
        assert len(list(root.glob('data/generation_requests/*/generation_request_v1.json'))) == 1
        post(client, '/api/auth/login', {}, {'phone': '13900000002', 'password': 'SyntheticCase2026!'})
        assert client.get('/api/create/batches/' + bid).status_code == 409


def test_story_k2_generation_native_partial_human_review_keeps_slot_identity(node):
    runtime,business=style_runtime(node,'story',story_events=EVENTS)
    root=runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login['csrf_token']}
        body={'business_id':business['business_id'],'speaker_id':business['speaker_id'],
              'configuration':config(story=2),'operation_id':'native_story_k_two'}
        checked=post(client,'/api/create/batches/preview',headers,body)['preview']
        result=post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':checked['source_configuration_sha256']})['result']
        bid=result['batch_id'];context=read(native.directory(root,bid)/'permission.json')
        group=native.groups(root,bid)[0]
        rid=admit_group(runtime,bid,group['group_id'],context)['request_id']
        post(client,'/api/create/'+rid+'/resolve-sources',headers)
        original=subprocess.run
        def transport(command,*args,**kwargs):
            mapping={'resolve_generation_content_plan_v1.py':'plan','resolve_generation_batch_v1.py':'generate'}
            if len(command)>1 and Path(command[1]).name in mapping:
                command=[command[0],str(PROJECT/'ops-pipeline/tests/creative_style_synthetic.py'),mapping[Path(command[1]).name],str(root),rid]
            return original(command,*args,**kwargs)
        runner=BackgroundTaskRunner(runtime)
        try:
            with patch.object(subprocess,'run',transport):
                for operation in ['resolve-content-plan','generate-scripts']:
                    task=post(client,'/api/create/'+rid+'/'+operation,headers)['task']['task_id']
                    runner._run(task)
                    assert get_task(runtime.database_path,task)['status']=='completed',get_task(runtime.database_path,task)
            batch=read(root/'data/generation_batches'/rid/'generation_batch_v1.json')
            assert len(batch['contents'])==2
            slots=[s['slot_id'] for s in native.intent(root,bid)[1]['slots']]
            assert [i['logical_slot_id'] for i in batch['contents']]==slots
            assert {i['central_claim'] for i in batch['contents']}==set(EVENTS)
            post(client,'/api/create/'+rid+'/review',headers,{'items':[
                {'content_id':batch['contents'][0]['content_id'],'decision':'approved'},
                {'content_id':batch['contents'][1]['content_id'],'decision':'rejected'}]})
            approved=read(root/'data/generation_batches'/rid/'approved_generation_batch_v1.json')
            assert len(approved['contents'])==1 and approved['contents'][0]['logical_slot_id']==slots[0]
            assert not (root/'data/content_ledgers'/business['business_id']/'content_ledger_v1.json').exists()
        finally:runner.close()


def test_two_distinct_novel_requests_accumulate_pending_without_semantic_ledger(node):
    from test_news_novel_runtime_v1_2 import native_news_runtime
    from test_news_generation_recovery_v1 import worker, calls
    prices=['午餐套餐29元，仅限工作日到店自取，不含配送',
            '儿童小份餐15元，仅限周末店内点单，不参与工作日午餐套餐']
    runtime,business,_,_,_=native_news_runtime(node,pricing_facts=prices)
    root=runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login['csrf_token']}
        body={'business_id':business['business_id'],'speaker_id':business['speaker_id'],
              'configuration':config(novel=2),'operation_id':'two_distinct_novel_once'}
        checked=post(client,'/api/create/batches/preview',headers,body)['preview']
        assert checked['actual_target']==2
        result=post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':checked['source_configuration_sha256']})['result']
        bid=result['batch_id'];context=read(native.directory(root,bid)/'permission.json')
        groups=native.groups(root,bid)
        assert len(groups)==2
        request_ids=[]
        for index,group in enumerate(groups):
            rid=admit_group(runtime,bid,group['group_id'],context)['request_id']
            request_ids.append(rid)
            if index == 1:
                # An already-generated sibling remains exactly replayable
                # while the next admitted Native Request has no outcome yet.
                replayed = admit_group(runtime, bid, groups[0]['group_id'], context)
                assert replayed['request_id'] == request_ids[0] and replayed['recovered']
            post(client,'/api/create/'+rid+'/resolve-sources',headers)
            from novel_news_v1 import _source_context
            source = _source_context(root, rid)
            selected_price = next(p for p in prices if p in source['selected']['central_claim'])
            assert {a['original_known_fact'] for a in source['usable_atoms'].values()
                    if a['field'] == 'pricing_facts'} == {selected_price}
            response=post(client,'/api/create/novel-news/'+rid+'/generate',headers)
            generated=worker(runtime,response['task']['task_id'],'success')
            assert generated.returncode==0,generated.stdout+generated.stderr
            actual=client.get('/api/create/novel-news/'+rid+'/state')
            assert actual.status_code == 200 and actual.json()['state']['stage'] == 'review', actual.text
            state=client.get('/api/create/batches/'+bid)
            assert state.status_code==200,state.text
            assert len(calls(root,rid))==1
            replay=post(client,'/api/create/novel-news/'+rid+'/generate',headers)
            assert replay['accepted'] is False and replay['task']['task_id']==response['task']['task_id']
        assert len(set(request_ids))==2
        assert not (root/'data/content_ledgers'/business['business_id']/'content_ledger_v1.json').exists()
        projected=post(client,'/api/create/novel-news/preview',headers,{
            'business_id':business['business_id'],'speaker_id':business['speaker_id']})['projection']
        assert projected['available_novel_count']==0
        assert {c['novelty_status'] for c in projected['opportunities']}=={'reserved'}
        assert len(list(root.glob('data/generation_requests/*/generation_request_v1.json')))==2
        review=client.get('/api/create/batches/'+bid+'/human-options?scope=native_content_review').json()['preview']
        assert len(review['items'])==2
    with TestClient(build_app(replace(runtime, novel_news_rollout='off'))) as revoked:
        post(revoked, '/api/auth/login', {}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        hidden = revoked.get('/api/create/batches/' + bid)
        # A mixed batch must retain its other legal results when News rollout
        # is withdrawn. Its safe status projection is not access to Native News.
        assert hidden.status_code==200,hidden.text
        blocked=hidden.json()['state']
        assert blocked['status']=='needs_attention' and not blocked['completion_proven']
        assert blocked['counts']['generated']==blocked['counts']['approved']==blocked['counts']['delivered']==0
        assert len(blocked['groups'])==2
        assert all(g['native'] is None and g['error_code']=='NOVEL_NEWS_NOT_AVAILABLE' and g['verification_pending'] for g in blocked['groups'])
        assert 'micro_information_beats' not in hidden.text
        offered=revoked.get('/api/create/batches/'+bid+'/human-options?scope=native_content_review')
        assert offered.status_code==200 and offered.json()['preview']['items']==[],offered.text
        login=post(revoked,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        denied=revoked.post('/api/create/batches/'+bid+'/human-command',headers={'X-CSRF-Token':login['csrf_token']},json={
            'scope':review['scope'],'source_sha256':review['source_sha256'],'operation_id':'revoked_human_denied',
            'items':[{**{k:v for k,v in i.items() if k!='display'},'decision':'approve'} for i in review['items']]})
        assert denied.status_code!=200 and denied.json()['detail']['code']=='NOVEL_NEWS_NOT_AVAILABLE',denied.text
        from novel_news_v1 import _paths
        assert all(not _paths(root,rid)['review'].is_file() and not _paths(root,rid)['approved'].is_file() for rid in request_ids)
        assert not list(native.directory(root,bid).glob('human_commands/*/command.json'))
