"""A0--A4 actual Native history; no simulated approval/Receipt/Closure owner."""
import copy
import json
import os
import shutil
import subprocess
import time
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from test_news_novel_runtime_v1_2 import native_news_runtime
from test_publish_copy_native_v1 import install_templates
from publish_copy_native_support import mix_flow,repurpose_existing,post,current,generation,confirm,worker,calls
from profile_compatibility_decisions_v1_1 import read,file_sha,digest,ref,write_once
from ledger_history_v1 import graph,LedgerHistoryError
from close_generation_export_v1 import close_generation_export,ExportClosureError
from app.main import build_app
from app.task_service import get_task,recover_expired_tasks
from app.background_task_service import BackgroundTaskRunner

def validate_anchor(root, rid):
    """Exercise the Native reader in its declared XLSX-capable interpreter."""
    project=Path(__file__).resolve().parents[2]
    code=('import sys,json;from pathlib import Path;sys.path.insert(0,str(Path(sys.argv[1])/"scripts"));'
          'from ledger_history_v1 import validate_anchor;'
          'print(json.dumps(validate_anchor(Path(sys.argv[1]),sys.argv[2]),ensure_ascii=False))')
    result=subprocess.run([str(project/'ops-pipeline/.venv/Scripts/python.exe'),'-c',code,str(root),rid],
        capture_output=True,text=True,encoding='utf-8',env={**os.environ,'PYTHONIOENCODING':'utf-8'},timeout=60)
    if result.returncode:raise RuntimeError(result.stderr)
    return json.loads(result.stdout)

@contextmanager
def hostile_copy(root,number):
    """A disposable copy occupies the same absolute namespace during the test.

    Path-bearing immutable artifacts are NOT re-encoded to manufacture a copy.
    Only a disposable physical clone is tampered. The original is restored by
    rename, never rewritten. All paths are checked inside the project workspace.
    """
    root=root.resolve();project=Path(__file__).resolve().parents[2]
    assert root.is_relative_to(project.parent.parent) and '.verify' in root.parts
    retained=root.with_name(root.name+'-protected-original')
    clone=root.with_name(root.name+'-hostile-'+str(number))
    assert not retained.exists() and not clone.exists()
    # The formal Release contains deep immutable paths. Use Windows' native
    # extended paths for the byte copy, without rewriting artifact references.
    extended=lambda p:'\\\\?\\'+str(p) if os.name=='nt' else str(p)
    shutil.copytree(extended(root),extended(clone),ignore=shutil.ignore_patterns('__pycache__'))
    root.rename(retained)
    try:
        clone.rename(root)
        assert root.is_dir() and not root.is_junction()
        yield root
    finally:
        if root.exists():root.rename(clone)
        assert not root.exists() and retained.is_dir() and clone.is_dir()
        retained.rename(root)

def test_native_anchor_memory_unknown_and_full_history_negatives(node):
    runtime,business,_,_,_=native_news_runtime(node,mixed=True)
    runtime=replace(runtime,publish_copy_enabled=True,task_lease_seconds=2,task_heartbeat_seconds=1)
    root=runtime.pipeline_root;install_templates(root)
    with TestClient(build_app(runtime)) as client:
        login=client.post('/api/auth/login',json={'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login.json()['csrf_token']}
        rid=mix_flow(client,headers,runtime,business,'anchor_original_mix')
        directory=root/'data/generation_batches'/rid
        original={str(p):file_sha(p) for p in directory.glob('*.json')}
        initial=validate_anchor(root,rid);ledger=root/initial['ledger_ref']['path'];old_ledger=file_sha(ledger)
        first=generation(client,headers,rid);tid=first['task']['task_id']
        stopped=worker(runtime,tid,'sent_without_response')
        assert stopped.returncode==92,(stopped.stdout,stopped.stderr)
        assert len(calls(root,rid))==1
        time.sleep(2.1);runner=BackgroundTaskRunner(runtime)
        try:recover_expired_tasks(runtime.database_path,task_types=('content_generation',),reconciler=runner._reconcile_business_state)
        finally:runner.close()
        assert get_task(runtime.database_path,tid)['status']=='failed'
        assert len(calls(root,rid))==1
        nrid=repurpose_existing(client,headers,runtime,business,'anchor_repurpose')
        assert file_sha(ledger)!=old_ledger
        assert validate_anchor(root,rid)['anchor_ref']==initial['anchor_ref']
        # The historical v1.0 interpreter itself remains exact and strict.
        closure=read(directory/'generation_export_closure_v1.json')
        with pytest.raises(ExportClosureError):
            close_generation_export(pipeline_root=root,request_id=rid,excel_path=Path(closure['excel_export']['path']),verify_only=True)
        assert client.get('/api/create/'+rid+'/exported-excel').status_code==200
        projected=client.get('/api/create/'+rid+'/delivery')
        assert projected.status_code==200,projected.text
        assert projected.json()['state']['stop_point_reached'] is True
        refused=client.post('/api/create/'+rid+'/publish-copy/generate',headers=headers,json={})
        assert refused.status_code==409 and refused.json()['detail']['code']=='PUBLISH_COPY_EXPLICIT_RETRY_REQUIRED',refused.text
        import publish_copy_v1 as native
        execution=get_task(runtime.database_path,tid)['payload']['publish_copy']
        with pytest.raises(RuntimeError) as conflict:
            native.run(root,rid,execution['operation_id'],execution['authorization_context'],transport=lambda _:pytest.fail('Memory conflict must not dispatch'))
        assert conflict.value.code=='PUBLISH_COPY_SOURCE_CHANGED'
        assert len(calls(root,rid))==1  # changed memory never silently rebinds/repeats
        retry=generation(client,headers,rid,retry=True)
        done=worker(runtime,retry['task']['task_id'],'success')
        assert done.returncode==0,(done.stdout,done.stderr)
        assert get_task(runtime.database_path,retry['task']['task_id'])['status']=='completed'
        assert len(calls(root,rid))==2
        assert all(file_sha(Path(p))==v for p,v in original.items())
        confirm(client,headers,rid)
        exported=post(client,'/api/create/'+rid+'/publish-copy/export',headers)
        done=worker(runtime,exported['task']['task_id'],'success')
        assert done.returncode==0,(done.stdout,done.stderr)
        assert get_task(runtime.database_path,exported['task']['task_id'])['status']=='completed'
        selected=current(client,rid)['delivery'];assert selected['state']=='completed'
        anchor=validate_anchor(root,rid);nodes=graph(root,business['business_id'])
        assert len(nodes)==2 and [v['kind'] for _,v in nodes]==['mix_semantic','news_presentation']
        assert len(read(ledger)['entries'])==1
        for _ in range(2):
            replay=post(client,'/api/create/'+rid+'/publish-copy/export',headers)
            assert replay['accepted'] is False and replay['task']['task_id']==exported['task']['task_id']
            assert client.get('/api/create/'+rid+'/publish-copy/excel/'+selected['delivery_id']).status_code==200
        # Clone first proves valid unchanged, then gets one targeted corruption.
        mutations=['unknown_metadata','semantic_text','catalog','updated_at','business','missing_event','unknown_schema',
                   'event_snapshot','event_parent','native_receipt','anchor_snapshot','duplicate_event','rollback_removed_tail',
                   'forged_snapshot_full_replay']
        original_bytes={p.relative_to(root).as_posix():file_sha(p) for p in (root/'data').rglob('*') if p.is_file() and '.locks' not in p.parts}
        observed=[]
        for number,mutation in enumerate(mutations):
            with hostile_copy(root,number) as clone_namespace:
                clone_root=clone_namespace.resolve()
                assert validate_anchor(clone_root,rid)['anchor_ref']  # positive copy control
                ap=clone_root/'data/generation_batches'/rid/'generation_export_anchor_evidence_v1.json'
                a=read(ap);lp=clone_root/'data/content_ledgers'/business['business_id']/'content_ledger_v1.json'
                cs=graph(clone_root,business['business_id']);ep,ev=cs[-1]
                if mutation in {'unknown_metadata','semantic_text','catalog','updated_at','business'}:
                    value=read(lp)
                    if mutation=='unknown_metadata':value['unknown_internal_grant']=True
                    elif mutation=='semantic_text':value['entries'][0]['narration']='篡改历史事实'
                    elif mutation=='catalog':value['fact_atom_catalog']=[]
                    elif mutation=='updated_at':value['updated_at']='1900-01-01'
                    else:value['business_id']='customer_foreign'
                    lp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
                elif mutation=='missing_event':ep.rename(ep.with_suffix('.missing'))
                elif mutation=='unknown_schema':ev['schema_version']='content-ledger-native-transition-v9.0';ep.write_text(json.dumps(ev),encoding='utf-8')
                elif mutation=='event_parent':ev['parent']={'path':'data/missing.json','sha256':'a'*64};ep.write_text(json.dumps(ev),encoding='utf-8')
                elif mutation=='event_snapshot':
                    sp=clone_root/ev['after_ref']['path'];value=read(sp);value['validation']['passed']=False;sp.write_text(json.dumps(value),encoding='utf-8')
                elif mutation=='anchor_snapshot':
                    sp=clone_root/a['ledger_snapshot_ref']['path'];value=read(sp);value['entries']=[];sp.write_text(json.dumps(value),encoding='utf-8')
                elif mutation=='native_receipt':
                    sp=clone_root/read(ep.with_name('receipt.json'))['native_receipt_ref']['path'];value=read(sp);value['validation_passed']=False;sp.write_text(json.dumps(value),encoding='utf-8')
                elif mutation=='duplicate_event':
                    duplicate=ep.parent.with_name('f'*32);shutil.copytree(ep.parent,duplicate)
                elif mutation=='rollback_removed_tail':
                    ep.rename(ep.with_suffix('.missing'))
                    lp.write_bytes((clone_root/a['ledger_snapshot_ref']['path']).read_bytes())
                elif mutation=='forged_snapshot_full_replay':
                    value=read(clone_root/ev['after_ref']['path']);value['historical_exposure_summary']['unknown_count']=99
                    payload=json.dumps(value,ensure_ascii=False,indent=2).encode();sha=__import__('hashlib').sha256(payload).hexdigest()
                    sp=ep.parents[2]/'snapshots'/(sha+'.json');sp.write_bytes(payload)
                    ev['after_ref']={'path':sp.relative_to(clone_root).as_posix(),'sha256':sha};ev['after_canonical_sha256']=digest(value)
                    ev['event_id']=digest({k:v for k,v in ev.items() if k not in {'schema_version','validator_version','event_id'}})[:32]
                    new_parent=ep.parent.with_name(ev['event_id']);ep.parent.rename(new_parent);ep=new_parent/'event.json'
                    ep.write_text(json.dumps(ev,ensure_ascii=False),encoding='utf-8')
                    seal=read(ep.with_name('receipt.json'));seal['event_ref']=ref(clone_root,ep)
                    ep.with_name('receipt.json').write_text(json.dumps(seal),encoding='utf-8');lp.write_bytes(payload)
                with pytest.raises((RuntimeError,OSError,ValueError,KeyError)):validate_anchor(clone_root,rid)
                observed.append(mutation)
        assert all(file_sha(root/name)==sha for name,sha in original_bytes.items())
        # New facts use the existing independent Business and Speaker Human
        # revision gates; no approved JSON is edited to manufacture a source.
        from test_review_flow_closure_v1 import amend,finish_speaker_review
        from test_customer_speaker_revision_v1 import review_current
        from review_protocol import post_review
        from test_news_qualification_complete_v1_2 import novel_flow
        bid=business['business_id'];sid=business['speaker_id'];csrf=headers['X-CSRF-Token']
        amend(client,bid,csrf,field='pricing_facts',value=['晚餐套餐39元，仅限堂食，不含饮品'])
        review_current(client,bid,csrf)
        approved=post_review(client,'/api/customers/'+bid+'/persona/approve',headers=headers,json={'note':'全虚构晚餐新价格独立人审'})
        assert approved.status_code==200,approved.text
        amend(client,bid,csrf,sid=sid,action='rebase');finish_speaker_review(client,bid,sid,csrf)
        approved=post_review(client,'/api/customers/'+bid+'/speakers/'+sid+'/persona/approve',headers=headers,json={'note':'全虚构本人确认新客户版本'})
        assert approved.status_code==200,approved.text
        newer,native_validation=novel_flow(client,headers,runtime,business)
        assert len(read(ledger)['entries'])==2
        assert validate_anchor(root,rid)['anchor_ref']==initial['anchor_ref']
        assert all(file_sha(Path(p))==v for p,v in original.items())
        stale=client.get('/api/create/'+rid+'/publish-copy')
        assert stale.status_code!=200  # historical validity never reopens current source/Truth
        for mutation in ['semantic_order','missing_middle_event']:
            with hostile_copy(root,len(observed)) as namespace:
                clone=namespace.resolve();assert validate_anchor(clone,rid)
                if mutation=='semantic_order':
                    target=clone/'data/content_ledgers'/bid/'content_ledger_v1.json';value=read(target);value['entries'].reverse()
                    target.write_text(json.dumps(value),encoding='utf-8')
                else:
                    middle=graph(clone,bid)[1][0];middle.rename(middle.with_suffix('.missing'))
                with pytest.raises((RuntimeError,OSError,ValueError,KeyError)):validate_anchor(clone,rid)
            observed.append(mutation)
        (root/'anchor_acceptance_evidence.json').write_text(json.dumps({'mix_request':rid,'repurpose_request':nrid,
            'later_native_semantic_request':newer,'native_validation':native_validation,
            'anchor':anchor,'delivery':selected,'negative_cases':observed,'external_calls':len(calls(root,rid)),
            'original_native_files_unchanged':True},ensure_ascii=False,indent=2),encoding='utf-8')
