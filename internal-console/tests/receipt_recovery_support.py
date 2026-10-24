"""Real native flows for receipt/authority negative tests; only provider transport substituted."""
import json,os,subprocess,uuid,shutil
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
from fastapi.testclient import TestClient
from test_generation_recovery_golden_v1 import native_node,login,node
from app.main import build_app
from app.background_task_service import BackgroundTaskRunner
from app.task_service import get_task

PROJECT=Path(__file__).resolve().parents[2]

@contextmanager
def native_flow(node):
    settings,business=native_node(node);root=settings.pipeline_root;real_run=subprocess.run
    faults={};memory_race=set()
    environment={k:v for k,v in os.environ.items() if not k.startswith(('DEEPSEEK_','QYAPI_','AIVO_'))}
    environment.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
    def boundary(command,*a,**kw):
        name=Path(command[1]).name if len(command)>1 else ''
        if name in {'resolve_generation_content_plan_v1.py','resolve_generation_batch_v1.py'}:
            rid=command[command.index('--request-id')+1]
            extra=[command[command.index('--operation-id')+1],command[command.index('--intent-sha256')+1]] if '--operation-id' in command else []
            operation='plan' if name.startswith('resolve_generation_content') else 'generate-fail' if not extra else 'generate-memory-race' if rid in memory_race else 'generate'
            command=[command[0],str(PROJECT/'ops-pipeline/tests/compatibility_creation_synthetic.py'),operation,str(root),rid,*extra];kw['env']=environment
        elif name in faults:
            point=faults.pop(name)
            command=[command[0],str(PROJECT/'ops-pipeline/tests/delivery_receipt_crash.py'),point,*command[1:]]
        return real_run(command,*a,**kw)
    with TestClient(build_app(settings)) as client,patch.object(subprocess,'run',boundary):
        headers=login(client);runner=BackgroundTaskRunner(settings)
        def run(prefix,endpoint,body=None):
            response=client.post(prefix+endpoint,headers=headers,**({'json':body} if body is not None else {}))
            assert response.status_code==200,response.text
            if response.json().get('canonical_result'):return response.json()
            task=response.json()['task'];runner._run(task['task_id'])
            return get_task(settings.database_path,task['task_id'])
        def request(customer=business, *, retry=True):
            response=client.post('/api/create/confirm',headers=headers,json={'business_id':customer['business_id'],
                'speaker_id':customer['speaker_id'],'profile':'mix','requested_quantity':1,'confirmed_quantity':1,
                'idempotency_key':'c305_fictional_recovery'})
            assert response.status_code==200,response.text
            rid=response.json()['result']['request_id'];prefix='/api/create/'+rid
            assert client.post(prefix+'/resolve-sources',headers=headers).status_code==200
            assert run(prefix,'/resolve-content-plan')['status']=='completed'
            assert run(prefix,'/generate-scripts')['status']=='failed'
            op=uuid.uuid4().hex
            preview=client.post(prefix+'/generation-recovery/preview',headers=headers,json={'operation_id':op})
            assert preview.status_code==200,preview.text
            body={'operation_id':op,'preview_sha256':preview.json()['preview_sha256']}
            value={'rid':rid,'prefix':prefix,'directory':root/'data/generation_batches'/rid,'retry_body':body}
            if retry:assert run(prefix,'/generation-recovery/confirm',body)['status']=='completed'
            return value
        def review(value,point=None):
            if point:faults['review_generation_batch_v2.py']=point
            state=client.get(value['prefix']+'/delivery').json()['state'];item=state['generation']['contents'][0]
            body={'items':[{'content_id':item['content_id'],'decision':'approved','note':'Explicit fictional human review'}],'note':'No new facts'}
            result=client.post(value['prefix']+'/review',headers=headers,json=body)
            assert result.status_code==(503 if point else 200),result.text
            value['human_body']=body
        template=root/'output/素材混剪&数字人口播混剪文案导入模板.xlsx';template.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PROJECT/'ops-pipeline/output'/template.name,template)
        try:yield {'settings':settings,'root':root,'business':business,'client':client,'headers':headers,'runner':runner,
            'request':request,'run':run,'review':review,'faults':faults,'memory_race':memory_race,'environment':environment}
        finally:runner.close()
