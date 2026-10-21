"""Shared isolated test driver. Only provider transport is synthetic."""
import json
import os
import subprocess
import sys
import shutil
from unittest.mock import patch
from dataclasses import asdict
from pathlib import Path
from test_news_qualification_complete_v1_2 import native_task
from test_profile_compatibility_golden_v1_1 import exercise_creation_tasks

PROJECT=Path(__file__).resolve().parents[2]

def worker(runtime,tid,mode='success',*,wait=True):
    config=runtime.pipeline_root/'publish_copy_worker.json'
    value=asdict(runtime);value['executing_project']=str(PROJECT)
    config.write_text(json.dumps(value,default=str),encoding='utf-8')
    command=[sys.executable,str(PROJECT/'internal-console/tests/publish_copy_process_worker.py'),str(config),tid,mode]
    options={'stdout':subprocess.PIPE,'stderr':subprocess.PIPE,'text':True,'encoding':'utf-8',
             'env':{**os.environ,'PYTHONIOENCODING':'utf-8'}}
    if not wait:return subprocess.Popen(command,**options)
    return subprocess.run(command,timeout=75,**options)

def calls(root,rid):
    path=root/'data/metrics'/rid/'publish_copy_calls.jsonl'
    return [json.loads(v) for v in path.read_text('utf-8').splitlines()] if path.is_file() else []

def mix_flow(client,headers,runtime,business,key):
    response=client.post('/api/create/confirm',headers=headers,json={'business_id':business['business_id'],
        'speaker_id':business['speaker_id'],'profile':'mix','requested_quantity':1,'confirmed_quantity':1,'idempotency_key':key})
    assert response.status_code==200,response.text
    rid=response.json()['result']['request_id']
    response=client.post('/api/create/'+rid+'/resolve-sources',headers=headers)
    assert response.status_code==200,response.text
    exercise_creation_tasks(client,headers,runtime,rid,PROJECT,
        transport_operations={'resolve_generation_content_plan_v1.py':'plan-news-history',
                              'resolve_generation_batch_v1.py':'generate-news-history'})
    return rid

def mix_reviewed(client,headers,runtime,business,key,*,quantity=1,many=False):
    """Stop before export so Native crash windows can be exercised."""
    from app.background_task_service import BackgroundTaskRunner
    from app.task_service import get_task
    result=post(client,'/api/create/confirm',headers,{'business_id':business['business_id'],
        'speaker_id':business['speaker_id'],'profile':'mix','requested_quantity':quantity,'confirmed_quantity':quantity,'idempotency_key':key})
    rid=result['result']['request_id'];post(client,'/api/create/'+rid+'/resolve-sources',headers)
    original=subprocess.run
    def transport(command,*args,**kwargs):
        mappings={'resolve_generation_content_plan_v1.py':'plan-news-history','resolve_generation_batch_v1.py':'generate-news-history'}
        if len(command)>1 and Path(command[1]).name in mappings:
            script=PROJECT/('internal-console/tests/publish_copy_multi_transport.py' if many else 'ops-pipeline/tests/compatibility_creation_synthetic.py')
            command=[command[0],str(script),
                     mappings[Path(command[1]).name],str(runtime.pipeline_root),rid]
        return original(command,*args,**kwargs)
    with patch.object(subprocess,'run',transport):
        runner=BackgroundTaskRunner(runtime)
        try:
            for operation in ['resolve-content-plan','generate-scripts']:
                tid=post(client,'/api/create/'+rid+'/'+operation,headers)['task']['task_id'];runner._run(tid)
                assert get_task(runtime.database_path,tid)['status']=='completed',get_task(runtime.database_path,tid)
        finally:runner.close()
    batch=json.loads((runtime.pipeline_root/'data/generation_batches'/rid/'generation_batch_v1.json').read_text('utf-8'))
    post(client,'/api/create/'+rid+'/review',headers,{'items':[{'content_id':v['content_id'],'decision':'approved'} for v in batch['contents']]})
    template=runtime.pipeline_root/'output/素材混剪&数字人口播混剪文案导入模板.xlsx'
    template.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PROJECT/'ops-pipeline/output'/template.name,template)
    return rid

def novel_complete(client,headers,runtime,business,key):
    """Normal Native flow after Founder eligibility; no qualification evidence."""
    from test_news_generation_recovery_v1 import create,worker as news_worker
    from app.task_service import get_task
    rid,tid=create(client,headers,business,key)
    result=news_worker(runtime,tid,'success');assert result.returncode==0,(result.stdout,result.stderr)
    assert get_task(runtime.database_path,tid)['status']=='completed'
    plan=json.loads((runtime.pipeline_root/'data/generation_batches'/rid/'novel_news_beat_plan_v1.json').read_text('utf-8'))
    post(client,'/api/create/novel-news/'+rid+'/review',headers,{'decisions':[
        {'beat_id':v['beat_id'],'decision':'approved'} for v in plan['micro_information_beats']]})
    native_task(runtime,client.post('/api/create/novel-news/'+rid+'/export',headers=headers))
    assert client.get('/api/create/novel-news/'+rid+'/excel').status_code==200
    return rid

def repurpose_existing(client,headers,runtime,business,key):
    rid=repurpose_reviewed(client,headers,runtime,business,key)
    native_task(runtime,client.post('/api/create/news/'+rid+'/export',headers=headers))
    return rid

def repurpose_reviewed(client,headers,runtime,business,key):
    response=client.post('/api/create/news/preview',headers=headers,json=business_payload(business))
    assert response.status_code==200,response.text
    source=response.json()['preview']['eligible_sources'][0]['source_content_id']
    response=client.post('/api/create/news/request',headers=headers,json={**business_payload(business),
        'source_content_id':source,'idempotency_key':key})
    assert response.status_code==200,response.text
    rid=response.json()['result']['request']['request_id'];url='/api/create/news/'+rid
    native_task(runtime,client.post(url+'/resolve-plan',headers=headers))
    slots=client.get(url+'/delivery').json()['state']['plan']['slots']
    response=client.post(url+'/review',headers=headers,json={'items':[{'slot_id':s['slot_id'],'decision':'approved'} for s in slots]})
    assert response.status_code==200,response.text
    return rid

def business_payload(b):return {'business_id':b['business_id'],'speaker_id':b['speaker_id']}

def post(client,path,headers,body=None):
    result=client.post(path,headers=headers,**({'json':body} if body is not None else {}))
    assert result.status_code==200,result.text
    return result.json()

def current(client,rid):
    result=client.get('/api/create/'+rid+'/publish-copy')
    assert result.status_code==200,result.text
    return result.json()['state']

def generation(client,headers,rid,*,retry=False,targets=None):
    value={}
    if retry:value.update(expected_parent=current(client,rid)['attempt_ref'],retry_confirmation='explicit_retry_possible_additional_cost')
    if targets:value['target_ids']=targets
    return post(client,'/api/create/'+rid+'/publish-copy/generate',headers,value)

def confirm(client,headers,rid):
    return post(client,'/api/create/'+rid+'/publish-copy/confirm',headers,{'draft_ref':current(client,rid)['draft']['ref']})
