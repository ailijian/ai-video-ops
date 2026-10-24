"""C07/C08 through authenticated HTTP and original Task/Native owners."""
import shutil,subprocess
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from creation_batch_golden_support import mixed_runtime,PROJECT
from test_creation_batch_orchestration_v1 import external_boundaries
from test_creation_batch_native_v1 import config
from publish_copy_native_support import post,generation,worker,confirm
from app.main import build_app
from app.creation_batch_gateway import advance,state
from app.background_task_service import BackgroundTaskRunner
from app.task_service import get_task
from app.database import connect
from human_review_operations_v1 import read,io_path
from creative_style_v1 import file_sha
import native_batch_v1 as native


def human(client,headers,bid,scope):
    preview=client.get('/api/create/batches/'+bid+'/human-options',params={'scope':scope})
    assert preview.status_code==200,preview.text
    value=preview.json()['preview']
    assert len(value['items'])==5,value
    items=[{**{k:v for k,v in item.items() if k!='display'},
        **({'decision':'approve'} if scope=='native_content_review' else {'action':'confirm'})} for item in value['items']]
    body={'scope':scope,'items':items,'operation_id':'explicit_'+scope,'source_sha256':value['source_sha256']}
    route='/api/create/batches/'+bid+'/human-command'
    denied=client.post(route,json=body);assert denied.status_code==403
    stale=client.post(route,headers=headers,json={**body,'source_sha256':'f'*64});assert stale.status_code!=200
    if scope=='native_content_review':
        omitted=client.post(route,headers=headers,json={**body,'items':items[:-1]})
        assert omitted.status_code!=200,omitted.text  # K=2 Native Request cannot receive half a review.
    first=post(client,route,headers,body)['result']
    assert first['all_native_completed'],first
    replay=post(client,route,headers,body)['result']
    assert replay['all_native_completed'] and replay['command_ref']==first['command_ref'],replay
    return body


def test_five_native_slots_concentrated_human_publish_and_two_profile_delivery(node):
    runtime,business=mixed_runtime(node);root=runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login['csrf_token']}
        body={**{k:business[k] for k in ('business_id','speaker_id')},'configuration':config(novel=2,persona=1,story=2),'operation_id':'full_c07_c08_once'}
        preview=post(client,'/api/create/batches/preview',headers,body)['preview']
        bid=post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':preview['source_configuration_sha256']})['result']['batch_id']
        context=read(native.directory(root,bid)/'permission.json');runner=BackgroundTaskRunner(runtime)
        try:
            with patch.object(subprocess,'run',external_boundaries):
                for _ in range(6):
                    advanced=advance(runtime,bid);task=advanced['task']['task_id'];runner._run(task)
                    assert get_task(runtime.database_path,task)['status']=='completed',get_task(runtime.database_path,task)
            content_command=human(client,headers,bid,'native_content_review')
            actual=state(runtime,bid,context)
            assert actual['counts']['generated']==actual['counts']['approved']==5 and not actual['completion_proven']
            assert not (root/'data/content_ledgers'/business['business_id']/'content_ledger_v1.json').exists()
            for group in native.groups(root,bid):
                rid=group['request_id'];task=generation(client,headers,rid)['task']['task_id']
                result=worker(runtime,task);assert result.returncode==0,result.stdout+result.stderr
                assert get_task(runtime.database_path,task)['status']=='completed',get_task(runtime.database_path,task)
            publish_command=human(client,headers,bid,'publish_copy_confirmation')
            template=root/'output/素材混剪&数字人口播混剪文案导入模板.xlsx'
            template.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PROJECT/'ops-pipeline/output'/template.name,template)
            for group in native.groups(root,bid):
                rid=group['request_id'];task=post(client,'/api/create/'+rid+'/publish-copy/export',headers)['task']['task_id']
                result=worker(runtime,task);assert result.returncode==0,result.stdout+result.stderr
                assert get_task(runtime.database_path,task)['status']=='completed',get_task(runtime.database_path,task)
            slots=[s['slot_id'] for s in native.intent(root,bid)[1]['slots']]
            immutable={p:p.read_bytes() for p in root.glob('data/content_ledgers/**/*.json')}
            for scope,selected in [('explicit_legal_subset',slots[2:3]),('complete_target',slots)]:
                target={'scope':scope,'slot_ids':selected}
                pre=post(client,'/api/create/batches/'+bid+'/delivery-preview',headers,target)['preview']
                submitted={**target,'source_sha256':pre['source_sha256'],'operation_id':'exact_'+scope}
                response=post(client,'/api/create/batches/'+bid+'/delivery-export',headers,submitted)
                tid=response['task']['task_id'];runner._run(tid)
                assert get_task(runtime.database_path,tid)['status']=='completed',get_task(runtime.database_path,tid)
                replay=post(client,'/api/create/batches/'+bid+'/delivery-export',headers,submitted)
                assert replay['task']['task_id']==tid and replay['accepted'] is False,replay
                duplicate=post(client,'/api/create/batches/'+bid+'/delivery-export',headers,{**submitted,'operation_id':'second_tab_'+scope})
                assert duplicate['task']['task_id']==tid and duplicate['accepted'] is False,duplicate
                result=replay['canonical_result'];assert result['delivered']==len(selected) and result['shortfall']==5-len(selected)
                assert len(result['files'])==(2 if scope=='complete_target' else 1)
                for item in result['files']:
                    downloaded=client.get('/api/create/batches/'+bid+'/deliveries/'+result['delivery_id']+'/'+item['profile'])
                    assert downloaded.status_code==200 and downloaded.content==io_path(Path(item['path'])).read_bytes()
                if scope=='complete_target':
                    corrupted=io_path(Path(result['files'][0]['path']));saved_bytes=corrupted.read_bytes()
                    try:
                        corrupted.write_bytes(saved_bytes+b'isolated-integrity-negative')
                        for item in result['files']:
                            denied=client.get('/api/create/batches/'+bid+'/deliveries/'+result['delivery_id']+'/'+item['profile'])
                            assert denied.status_code!=200  # Whole set must fail even if requested other profile is intact.
                    finally:corrupted.write_bytes(saved_bytes)
                wrong={**submitted,'slot_ids':slots[:1] if scope=='complete_target' else slots[3:4]}
                denied=client.post('/api/create/batches/'+bid+'/delivery-export',headers=headers,json=wrong)
                assert denied.status_code!=200,denied.text
            original_run=subprocess.run
            for point in ('prepared','receipt','complete'):
                selected={'prepared':slots[:1],'receipt':[slots[0],slots[2]],'complete':[slots[1],slots[2]]}[point]
                target={'scope':'explicit_legal_subset','slot_ids':selected}
                pre=post(client,'/api/create/batches/'+bid+'/delivery-preview',headers,target)['preview']
                submitted={**target,'source_sha256':pre['source_sha256'],'operation_id':'interrupted_'+point}
                first=post(client,'/api/create/batches/'+bid+'/delivery-export',headers,submitted)
                tid=first['task']['task_id']
                def death(command,*args,**kwargs):
                    if len(command)>2 and Path(command[1]).name=='creation_delivery_v1.py' and command[2]=='composite-export':
                        command=[command[0],str(PROJECT/'internal-console/tests/creation_batch_delivery_fault.py'),point,*command[1:]]
                    return original_run(command,*args,**kwargs)
                with patch.object(subprocess,'run',death):runner._run(tid)
                assert get_task(runtime.database_path,tid)['status']=='failed'
                if point!='complete':
                    operation=next(p for p in (native.directory(root,bid)/'deliveries/operations').glob('*/binding.json') if read(p)['operation_id']==submitted['operation_id'])
                    did=read(operation)['delivery_id']
                    unavailable=client.get('/api/create/batches/'+bid+'/deliveries/'+did+'/news')
                    assert unavailable.status_code!=200,unavailable.text
                post(client,'/api/auth/logout',headers)
                login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
                headers={'X-CSRF-Token':login['csrf_token']}
                resumed=post(client,'/api/create/batches/'+bid+'/delivery-export',headers,submitted)
                assert resumed['task']['task_id']==tid
                if resumed['accepted']:runner._run(tid)
                assert get_task(runtime.database_path,tid)['status']=='completed',get_task(runtime.database_path,tid)
                replay=post(client,'/api/create/batches/'+bid+'/delivery-export',headers,submitted)
                assert not replay['accepted'] and replay['task']['task_id']==tid
            for command in (content_command,publish_command):
                replay=post(client,'/api/create/batches/'+bid+'/human-command',headers,command)['result']
                assert replay['all_native_completed'],replay
            from compatibility_golden_support import prepare_native_business
            from test_creation_batch_native_v1 import EVENTS
            other=prepare_native_business(node,customer_name='另一全虚构隔离客户',story_events=EVENTS,speaker_type='owner_founder')
            other_body={**{k:other[k] for k in ('business_id','speaker_id')},'configuration':config(persona=1),'operation_id':'isolated_other_customer'}
            other_pre=post(client,'/api/create/batches/preview',headers,other_body)['preview']
            other_bid=post(client,'/api/create/batches/confirm',headers,{**other_body,'preflight_sha256':other_pre['source_configuration_sha256']})['result']['batch_id']
            foreign=client.post('/api/create/batches/'+other_bid+'/delivery-preview',headers=headers,json={'scope':'complete_target','slot_ids':slots})
            assert foreign.status_code!=200,foreign.text
            foreign=client.get('/api/create/batches/'+other_bid+'/deliveries/'+result['delivery_id']+'/mix')
            assert foreign.status_code!=200,foreign.text
            assert not (native.directory(root,other_bid)/'deliveries').exists()
            assert all(p.read_bytes()==old for p,old in immutable.items())
            projected=client.get('/api/create/batches/'+bid)
            assert projected.status_code==200,projected.text
            projected=projected.json()['state']
            assert projected['counts']['generated']==projected['counts']['approved']==projected['counts']['delivered']==5,projected
            assert projected['counts']['new_semantic_count']==5 and projected['completion_proven']
            assert len(projected['deliveries']['completed'])==5,projected
            with connect(runtime.database_path) as db:
                assert db.execute("SELECT count(*) FROM tasks WHERE json_extract(payload_json,'$.operation')='creation_batch_export'").fetchone()[0]==5
            # CR029: a historic parent must not stand in for a newly confirmed
            # Publish version; historical aggregate downloads remain immutable.
            from publish_copy_native_support import current
            import copy
            persona=next(g for g in native.groups(root,bid) if (g['creative_style'] or {}).get('style_id')=='persona')
            rid=persona['request_id'];publish=current(client,rid)
            payload=copy.deepcopy(publish['draft']['payload'])
            payload['items'][0]['publish_title']='本期介绍'+payload['items'][0]['publish_title']
            post(client,'/api/create/'+rid+'/publish-copy/edit',headers,{'draft_ref':publish['draft']['ref'],'payload':payload})
            confirm(client,headers,rid)
            changed=client.get('/api/create/batches/'+bid).json()['state']
            assert changed['status']=='preparing_delivery' and not changed['completion_proven'],changed
            assert changed['counts']['historically_delivered']==5 and changed['counts']['delivered']<5
            old_full=next(v for v in changed['deliveries']['completed'] if v['scope']=='complete_target')
            assert not old_full['is_current']
            for item in old_full['files']:
                assert client.get('/api/create/batches/'+bid+'/deliveries/'+old_full['delivery_id']+'/'+item['profile']).status_code==200
            parent=post(client,'/api/create/'+rid+'/publish-copy/export',headers)['task']['task_id']
            completed=worker(runtime,parent);assert completed.returncode==0,completed.stdout+completed.stderr
            target={'scope':'complete_target','slot_ids':slots}
            pre=post(client,'/api/create/batches/'+bid+'/delivery-preview',headers,target)['preview']
            new=post(client,'/api/create/batches/'+bid+'/delivery-export',headers,{**target,
                'source_sha256':pre['source_sha256'],'operation_id':'new_confirmed_publish_version'})
            runner._run(new['task']['task_id'])
            assert get_task(runtime.database_path,new['task']['task_id'])['status']=='completed'
            final=client.get('/api/create/batches/'+bid).json()['state']
            assert final['completion_proven'] and final['counts']['delivered']==5,final
            assert all(p.read_bytes()==old for p,old in immutable.items())
        finally:runner.close()
