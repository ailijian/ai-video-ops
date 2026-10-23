"""An explicitly confirmed four-day cycle, through all original owners."""
import shutil,subprocess
from unittest.mock import patch
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from creation_batch_golden_support import mixed_runtime,PROJECT
from test_creation_batch_native_v1 import config
from test_creation_batch_orchestration_v1 import external_boundaries
from publish_copy_native_support import post,generation,worker
from app.main import build_app
from app.creation_batch_gateway import advance,state
from app.background_task_service import BackgroundTaskRunner
from app.task_service import get_task
from human_review_operations_v1 import read
import native_batch_v1 as native

PRACTICES=['我亲自每天核对餐盒库存，按当天备餐安排登记需要补充的餐盒数量',
           '我本人负责张贴门口营业时间表，营业安排有变化时由我更新纸质告示',
           '我亲自整理当日纸质菜单，按门店当天实际可供应的菜品逐项列出']


def complete_human(client,headers,bid,scope):
    value=client.get('/api/create/batches/'+bid+'/human-options',params={'scope':scope}).json()['preview']
    assert len(value['items'])==8,value
    command={'scope':scope,'source_sha256':value['source_sha256'],'operation_id':'steady_'+scope,
        'items':[{**{k:v for k,v in i.items() if k!='display'},
            **({'decision':'approve'} if scope=='native_content_review' else {'action':'confirm'})} for i in value['items']]}
    previous=-1
    for _ in range(12):
        result=post(client,'/api/create/batches/'+bid+'/human-command',headers,command)['result']
        if result['all_native_completed']:return command
        assert result['continuation_needed'] and not any(v.get('blocked') for v in result['results']),result
        completed=sum(not v.get('deferred') for v in result['results'])
        assert completed>previous,result
        previous=completed
    raise AssertionError('The original bounded command did not finish')


def test_one_explicit_cycle_preserves_three_styles_and_two_profile_delivery(node):
    runtime,business=mixed_runtime(node,personal_practices=PRACTICES,pricing_facts=[
        '午餐套餐29元，仅限工作日到店自取，不含配送',
        '儿童小份餐15元，仅限周末店内点单，不参与工作日午餐套餐',
        '线上预订菌菇午餐35元，周三营业时段可自取，每单仅限一份套餐']);root=runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login['csrf_token']}
        configuration={**config(novel=1,persona=3,story=2,conversion=2),'mode':'stage','stage':'steady','cycles':1,'cyclesConfirmed':True}
        body={**{k:business[k] for k in ('business_id','speaker_id')},'configuration':configuration,'operation_id':'one_finite_cycle'}
        pre=post(client,'/api/create/batches/preview',headers,body)['preview']
        assert pre['actual_target']==8
        bid=post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':pre['source_configuration_sha256']})['result']['batch_id']
        groups=native.groups(root,bid);assert len(groups)==5
        runner=BackgroundTaskRunner(runtime)
        try:
            with patch.object(subprocess,'run',external_boundaries):
                for _ in range(9):
                    step=advance(runtime,bid);assert step['advanced'],step
                    runner._run(step['task']['task_id'])
                    assert get_task(runtime.database_path,step['task']['task_id'])['status']=='completed'
            actual=state(runtime,bid,native.current_context(root,bid))
            assert actual['counts']['generated']==8,actual
            complete_human(client,headers,bid,'native_content_review')
            for group in groups:
                tid=generation(client,headers,group['request_id'])['task']['task_id']
                completed=worker(runtime,tid);assert completed.returncode==0,completed.stdout+completed.stderr
                assert get_task(runtime.database_path,tid)['status']=='completed',get_task(runtime.database_path,tid)
            complete_human(client,headers,bid,'publish_copy_confirmation')
            template=root/'output/素材混剪&数字人口播混剪文案导入模板.xlsx'
            template.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PROJECT/'ops-pipeline/output'/template.name,template)
            for group in groups:
                tid=post(client,'/api/create/'+group['request_id']+'/publish-copy/export',headers)['task']['task_id']
                completed=worker(runtime,tid);assert completed.returncode==0,completed.stdout+completed.stderr
            protected={p:p.read_bytes() for p in root.glob('data/content_ledgers/**/*.json')}
            scope={'scope':'complete_target','slot_ids':[s['slot_id'] for g in groups for s in g['slots']]}
            pre=post(client,'/api/create/batches/'+bid+'/delivery-preview',headers,scope)['preview']
            assert {f['profile']:f['rows'] for f in pre['files']}=={'news':1,'mix':7}
            command={**scope,'source_sha256':pre['source_sha256'],'operation_id':'steady_two_files'}
            result=post(client,'/api/create/batches/'+bid+'/delivery-export',headers,command)
            runner._run(result['task']['task_id'])
            assert get_task(runtime.database_path,result['task']['task_id'])['status']=='completed'
            replay=post(client,'/api/create/batches/'+bid+'/delivery-export',headers,command)
            assert not replay['accepted'] and replay['task']['task_id']==result['task']['task_id']
            actual=state(runtime,bid,native.current_context(root,bid))
            assert actual['completion_proven'] and actual['counts']['delivered']==8,actual
            assert all(p.read_bytes()==b for p,b in protected.items())
            contents=[c for g in groups if g['profile']=='mix' for c in read(root/'data/generation_batches'/g['request_id']/'approved_generation_batch_v1.json')['contents']]
            assert {style:sum(c['creative_style']['style_id']==style for c in contents) for style in ('persona','story','conversion')}=={'persona':3,'story':2,'conversion':2}
            assert len({c['central_claim'] for c in contents})==7
            assert len(native.groups(root,bid))==5 and not advance(runtime,bid)['advanced']
        finally:runner.close()
