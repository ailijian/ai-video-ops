"""Native isolated recovery acceptance for every downstream persistence cut."""
import sys, os, json, subprocess, shutil, uuid
from pathlib import Path
from unittest.mock import patch
import pytest
PROJECT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(PROJECT/'internal-console'),str(PROJECT/'internal-console/tests'),str(PROJECT/'ops-pipeline/scripts')]
from test_generation_recovery_golden_v1 import native_node, login, task_count, node, sha
from app.main import build_app
from app.background_task_service import BackgroundTaskRunner
from app.task_service import get_task
from fastapi.testclient import TestClient

@pytest.mark.parametrize('point',['review','approved','human_receipt','export_intent','publication','xlsx','export_receipt','ledger','closure'])
def test_native_partial_persistence(node,point):
    settings,business=native_node(node);root=settings.pipeline_root
    real_run=subprocess.run
    phase={'fail':True,'cut':False,'used':False}
    env={k:v for k,v in os.environ.items() if not k.startswith(('DEEPSEEK_','QYAPI_','AIVO_'))}
    env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
    cut_names={'review':'review_generation_batch_v2.py','approved':'review_generation_batch_v2.py','human_receipt':'review_generation_batch_v2.py',
               'export_intent':'export_mix_excel_v1.py','publication':'export_mix_excel_v1.py',
               'xlsx':'export_mix_excel_v1.py','export_receipt':'export_mix_excel_v1.py','ledger':'close_generation_export_v1.py','closure':'close_generation_export_v1.py'}
    def boundary(command,*a,**kw):
        name=Path(command[1]).name if len(command)>1 else ''
        if name in {'resolve_generation_content_plan_v1.py','resolve_generation_batch_v1.py'}:
            rid=command[command.index('--request-id')+1]
            operation='plan' if name.startswith('resolve_generation_content') else 'generate-fail' if phase['fail'] else 'generate'
            extra=[command[command.index('--operation-id')+1],command[command.index('--intent-sha256')+1]] if '--operation-id' in command else []
            command=[command[0],str(PROJECT/'ops-pipeline/tests/compatibility_creation_synthetic.py'),operation,str(root),rid,*extra];kw['env']=env
        elif phase['cut'] and not phase['used'] and name==cut_names[point]:
            phase['used']=True
            command=[command[0],str(PROJECT/'ops-pipeline/tests/delivery_receipt_crash.py'),point,*command[1:]]
        return real_run(command,*a,**kw)
    with TestClient(build_app(settings)) as client,patch.object(subprocess,'run',boundary):
        headers=login(client)
        response=client.post('/api/create/confirm',headers=headers,json={'business_id':business['business_id'],'speaker_id':business['speaker_id'],
            'profile':'mix','requested_quantity':1,'confirmed_quantity':1,'idempotency_key':'c305_fictional_recovery'})
        assert response.status_code==200,response.text
        rid=response.json()['result']['request_id'];prefix=f'/api/create/{rid}'
        assert client.post(prefix+'/resolve-sources',headers=headers).status_code==200
        runner=BackgroundTaskRunner(settings)
        def execute(endpoint,body=None):
            response=client.post(prefix+endpoint,headers=headers,**({'json':body} if body is not None else {}))
            if response.status_code!=200:return {'http':response.status_code,'body':response.json()}
            task=response.json().get('task')
            if response.json().get('canonical_result'):
                return {'status':'completed','canonical_response':response.json(),'retained_task_status':task['status'] if task else None}
            if task and task['status']=='queued':runner._run(task['task_id'])
            return get_task(settings.database_path,task['task_id']) if task else response.json()
        try:
            assert execute('/resolve-content-plan')['status']=='completed'
            assert execute('/generate-scripts')['status']=='failed'
            phase['fail']=False;op=uuid.uuid4().hex
            preview=client.post(prefix+'/generation-recovery/preview',headers=headers,json={'operation_id':op})
            assert preview.status_code==200,preview.text
            recovered=execute('/generation-recovery/confirm',{'operation_id':op,'preview_sha256':preview.json()['preview_sha256']})
            assert recovered['status']=='completed'
            item=client.get(prefix+'/delivery').json()['state']['generation']['contents'][0]
            human={'items':[{'content_id':item['content_id'],'decision':'approved','note':'Explicit fictional review'}],'note':'No changed facts'}
            phase['cut']=point in {'review','approved','human_receipt'}
            human_task_count=task_count(settings)
            first=client.post(prefix+'/review',headers=headers,json=human)
            directory=root/'data/generation_batches'/rid
            frozen={p.name:sha(p) for p in directory.glob('*.json') if p.name!='generation_batch_v1.json'}
            if point=='approved':
                pending=client.get(prefix+'/delivery').json()['state']
                assert pending['next_action']=='RESUME_HUMAN_REVIEW' and not pending['review']['approved']
                other,other_headers,_=node[1]['B']
                denied=other.post(prefix+'/review',headers=other_headers,json=human)
                assert denied.status_code==403,denied.text
                assert client.post(prefix+'/review',headers=headers,json={**human,'note':'Different original Human decision'}).status_code==409
                changed_paths=[directory/'generation_human_review_v2.json',directory/'approved_generation_batch_v1.json',
                    root/client.get(prefix+'/delivery').json()['state']['generation']['batch_ref']['path'],
                    root/'data/generation_requests'/rid/'generation_request_v1.json']
                for changed_path in changed_paths:
                    original=changed_path.read_bytes()
                    try:
                        changed_path.write_bytes(original+b'\n')
                        if changed_path.name=='approved_generation_batch_v1.json':
                            changed=json.loads(original);changed['approved_export_count']=999
                            changed_path.write_text(json.dumps(changed),encoding='utf-8')
                        denied=client.post(prefix+'/review',headers=headers,json=human)
                        assert denied.status_code in {403,409,503},denied.text
                        assert not (directory/'generation_batch_approval_receipt.json').exists()
                    finally:changed_path.write_bytes(original)
                assert runner._reconcile_business_state(recovered['task_id'])=='completed'
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=2) as pool:
                    responses=list(pool.map(lambda _:client.post(prefix+'/review',headers=headers,json=human),range(2)))
                assert all(r.status_code in {200,409} for r in responses)
            second=client.post(prefix+'/review',headers=headers,json=human) if phase['cut'] else first
            review_result={'first_http':first.status_code,'replay_http':second.status_code,'body':second.json()}
            if second.status_code!=200:
                (root.parent/'partial-probe-result.json').write_text(json.dumps({'point':point,'injected':phase['used'],
                    'review':review_result,'all_existing_artifacts_unchanged':all(sha(directory/name)==value for name,value in frozen.items()),
                    'closure_exists':False,'acceptance':'BLOCKED'},ensure_ascii=False,indent=2),encoding='utf-8')
            assert second.status_code==200,review_result
            assert task_count(settings)==human_task_count
            assert all(sha(directory/name)==value for name,value in frozen.items())
            template=root/'output/素材混剪&数字人口播混剪文案导入模板.xlsx';template.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(PROJECT/'ops-pipeline/output'/template.name,template)
            phase['cut']=point not in {'review','approved','human_receipt'}
            first_export=execute('/export-mix')
            export_task_count=task_count(settings)
            if point=='xlsx':
                partial_state=client.get(prefix+'/delivery').json()['state']
                assert partial_state['export']['state']=='export_receipt_pending' and not partial_state['export']['completed']
                assert client.get(prefix+'/exported-excel').status_code!=200
                other,other_headers,_=node[1]['B']
                assert other.post(prefix+'/export-mix',headers=other_headers).status_code==403
                assert task_count(settings)==export_task_count
                intent=json.loads((directory/'generation_export_intent_v1.json').read_text(encoding='utf-8'))
                output=root/intent['output_path']
                for changed_path in [output,template]:
                    original=changed_path.read_bytes()
                    try:
                        changed_path.write_bytes(original+b'\0')
                        denied=client.post(prefix+'/export-mix',headers=headers)
                        assert denied.status_code in {409,503},denied.text
                        assert task_count(settings)==export_task_count
                        assert not output.with_suffix('.export_receipt.json').exists()
                    finally:changed_path.write_bytes(original)
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=2) as pool:
                    admissions=list(pool.map(lambda _:client.post(prefix+'/export-mix',headers=headers),range(2)))
                assert all(r.status_code in {200,409} for r in admissions)
                assert len({r.json()['task']['task_id'] for r in admissions if r.status_code==200})==1
                assert task_count(settings)==export_task_count
            preserved={p.as_posix():sha(p) for p in root.rglob('*') if p.is_file() and (p.suffix=='.xlsx' or p.name.endswith('export_receipt.json') or p.name=='generation_export_closure_v1.json' or 'content_ledgers' in p.parts)}
            replay=execute('/export-mix') if phase['cut'] else first_export
            assert task_count(settings)==export_task_count
            closure=directory/'generation_export_closure_v1.json'
            # Immutable snapshots/events are evidence, not additional active
            # business Ledgers. Count only the canonical path owned by Reader.
            ledger_files=list((root/'data/content_ledgers').glob('*/content_ledger_v1.json'))
            result={'point':point,'injected':phase['used'],'review':review_result,'first_export_status':first_export.get('status'),
                    'replay_export_status':replay.get('status'),'replay_error':replay.get('error_code') or replay.get('body'),
                    'canonical_completed_response':bool(replay.get('canonical_response')),'retained_task_status':replay.get('retained_task_status'),
                    'task_count_before_resume':export_task_count,'task_count_after_resume':task_count(settings),
                    'closure_exists':closure.is_file(),'all_existing_artifacts_unchanged':all(sha(Path(p))==h for p,h in preserved.items()),
                    'ledger_entry_counts':[len(json.loads(p.read_text(encoding='utf-8')).get('entries',[])) for p in ledger_files]}
            (root.parent/'partial-probe-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            assert result['replay_export_status']=='completed',result
            assert result['closure_exists'] and result['all_existing_artifacts_unchanged'],result
            assert result['ledger_entry_counts']==[1],result
            assert phase['used'], 'Cut point did not actually execute'
            if point=='xlsx':
                # Negative corruption of this isolated fixture only. A legacy
                # Reader must not become a downgrade path for a new bound export.
                receipt_path=output.with_suffix('.export_receipt.json');original=receipt_path.read_bytes()
                try:
                    forged=json.loads(original);forged['schema_version']='mix-excel-export-receipt-v1.0'
                    forged['batch_path']=str(root/'data/missing-foreign-approved.json')
                    receipt_path.write_text(json.dumps(forged),encoding='utf-8')
                    assert client.get(prefix+'/exported-excel').status_code!=200
                    assert client.post(prefix+'/export-mix',headers=headers).status_code in {409,503}
                    assert task_count(settings)==export_task_count
                finally:receipt_path.write_bytes(original)
            # Every persistence cut must recover through real native writers.
        finally:runner.close()
