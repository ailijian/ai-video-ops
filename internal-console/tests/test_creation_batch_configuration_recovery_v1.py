"""Saved draft is never confirmation; recover an actual C03 after login loss."""
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from creation_batch_golden_support import mixed_runtime
from test_creation_batch_native_v1 import config
from publish_copy_native_support import post
from app.main import build_app
from app.creation_batch_gateway import advance
from app.database import connect
from human_review_operations_v1 import read
import native_batch_v1 as native


def test_confirmed_configuration_and_history_recover_original_novel_batch_without_reallocation(node):
    runtime,business=mixed_runtime(node);root=runtime.pipeline_root;business_id=business['business_id']
    route='/api/create/configuration/'+business_id
    with TestClient(build_app(runtime)) as client:
        login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login['csrf_token']}
        payload={'speaker_id':business['speaker_id'],'configuration':config(novel=1)}
        saved=client.put(route,headers=headers,json={'revision':0,'payload':payload})
        assert saved.status_code==200,saved.text
        saved=saved.json();operation=saved['operation_id']
        assert client.get(route).json().get('confirmed_batch') is None
        body={'business_id':business_id,**payload,'operation_id':operation}
        pre=post(client,'/api/create/batches/preview',headers,body)['preview']
        bid=post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':pre['source_configuration_sha256']})['result']['batch_id']
        tid=advance(runtime,bid)['task']['task_id']  # Canonical opportunity is now reserved; no model runs.
        intent_path=native.directory(root,bid)/'intent.json';before=intent_path.read_bytes()
        post(client,'/api/auth/logout',headers)
        login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login['csrf_token']}
        actual=client.get(route)
        assert actual.status_code==200,actual.text
        assert actual.json()['confirmed_batch']['batch_id']==bid
        assert actual.json()['confirmed_batch']['intent_ref']==native.batch_ref(root,bid)
        history=client.get('/api/create/batches',params={'business_id':business_id})
        assert history.status_code==200,history.text
        assert [v['batch_id'] for v in history.json()['batches']]==[bid]
        replay=post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':pre['source_configuration_sha256']})['result']
        assert replay['recovered'] and replay['batch_id']==bid
        assert intent_path.read_bytes()==before
        with connect(runtime.database_path) as db:
            assert db.execute("SELECT count(*) FROM tasks WHERE json_extract(payload_json,'$.operation')='novel_news_generate'").fetchone()[0]==1
        assert not (root/'data/content_ledgers'/business_id/'content_ledger_v1.json').exists()
        assert not list(root.glob('data/metrics/*/batch_novel_calls.jsonl'))
        # An explicit new draft receives a new operation, without reopening an
        # opportunity owned by the existing Request or switching it to Repurpose.
        fresh={**payload,'configuration':{**payload['configuration'],'revision':1}}
        changed=client.put(route,headers=headers,json={'revision':saved['revision'],'payload':fresh})
        assert changed.status_code==200,changed.text
        assert changed.json()['operation_id']!=operation
        assert client.get(route).json().get('confirmed_batch') is None
        next_preview=client.post('/api/create/batches/preview',headers=headers,json={
            'business_id':business_id,**fresh,'operation_id':changed.json()['operation_id']})
        assert next_preview.status_code==200,next_preview.text
        original_choice=next(r['id'] for r in native.intent(root,bid)[1]['slots'][0]['source_refs'] if r['owner']=='native-novel-opportunity')
        next_slots=next_preview.json()['preview']['snapshot']['slots']
        assert all(s['source_kind']=='novel_content' for s in next_slots)
        assert all(r['id']!=original_choice for s in next_slots for r in s['source_refs'] if r['owner']=='native-novel-opportunity')
        assert len(list((root/'data/creation_batches').glob('*/intent.json')))==1
    with TestClient(build_app(runtime)) as other:
        login=post(other,'/api/auth/login',{}, {'phone':'13900000002','password':'SyntheticCase2026!'})
        denied=other.get('/api/create/batches',params={'business_id':business_id})
        assert denied.status_code==200 and denied.json()['batches']==[],denied.text


def test_changed_existing_account_state_blocks_old_confirmation_but_preserves_editable_draft(node):
    runtime,business=mixed_runtime(node);root=runtime.pipeline_root;bid=business['business_id']
    route='/api/create/configuration/'+bid
    with TestClient(build_app(runtime)) as client:
        login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login['csrf_token']}
        payload={'speaker_id':business['speaker_id'],'configuration':config(novel=1)}
        saved=client.put(route,headers=headers,json={'revision':0,'payload':payload})
        assert saved.status_code==200;saved=saved.json()
        body={'business_id':bid,**payload,'operation_id':saved['operation_id']}
        preview=post(client,'/api/create/batches/preview',headers,body)['preview']
        batch=post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':preview['source_configuration_sha256']})['result']['batch_id']
        intent_path=native.directory(root,batch)/'intent.json';original=intent_path.read_bytes()
        post(client,'/api/auth/change-password',headers,{'current_password':'SyntheticCase2026!',
            'new_password':'SyntheticChanged2026!','confirm_password':'SyntheticChanged2026!'})
        login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticChanged2026!'})
        headers={'X-CSRF-Token':login['csrf_token']}
        current=client.get(route);assert current.status_code==200,current.text
        current=current.json()
        assert current['draft']==payload and current['confirmed_batch'] is None
        assert current['confirmation_blocked']['code']=='CREATION_BATCH_ACTOR_CONFLICT'
        assert client.get('/api/create/batches/'+batch).status_code!=200
        fresh={**payload,'configuration':{**payload['configuration'],'revision':1}}
        result=client.put(route,headers=headers,json={'revision':saved['revision'],'payload':fresh})
        assert result.status_code==200,result.text
        assert result.json()['operation_id']!=saved['operation_id']
        assert not client.get(route).json().get('confirmation_blocked')
        assert intent_path.read_bytes()==original
        assert not list(root.glob('data/generation_requests/*/generation_request_v1.json'))
