"""Real Native gates with fresh content-based invalidation, no timed Authority cache."""
import copy
import os
import uuid
import time
import json
from pathlib import Path

import pytest

from test_case_evidence_revision_v1 import node
from test_news_novel_runtime_v1_2 import native_news_runtime
from profile_compatibility_contract_v1_1 import CompatibilityError
from profile_compatibility_decisions_v1_1 import read, preview, decide, decision_graph, target_id
import profile_compatibility_release_v1_1 as owner
from profile_compatibility_release_v1_2 import binding, validation_fingerprint


def test_real_news_reuse_revalidates_sources_same_mtime_and_live_withdrawal(node, monkeypatch):
    runtime, _, news, _, _ = native_news_runtime(node)
    root=runtime.pipeline_root
    owner._read_scope.news_checks={}
    full=owner.validate_bundle
    calls=[]

    def observed(*args,**kwargs):
        calls.append(1)
        return full(*args,**kwargs)  # Always the actual formal Native verifier.

    monkeypatch.setattr(owner,'validate_bundle',observed)
    first=owner.effective_runtime(root)
    pinned=binding(first,'novel_content')
    owner.effective_runtime(root,pinned=pinned)
    count=len(calls)
    third=owner.effective_runtime(root,pinned=pinned)
    assert len(calls)==count and count>=2
    assert third==first
    third['manifest']['profiles'].clear()
    assert owner.effective_runtime(root)['manifest']['profiles']==['news']
    invalid=copy.deepcopy(pinned);invalid['decision_head_sha256']='f'*64
    with pytest.raises(CompatibilityError):owner.effective_runtime(root,pinned=invalid)

    config=read(root/owner.CONFIG);control=Path(config['control_root'])
    target=news['targets'][0]
    # Same size and original mtime cannot hide a changed Case, FP or Pattern.
    for key in ('case_ref','fingerprint_ref','pattern_ref'):
        path=control/target[key]['path'];raw=path.read_bytes();stamp=path.stat()
        assert b'\n' in raw
        path.write_bytes(raw.replace(b'\n',b' ',1))
        os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        try:
            with pytest.raises(CompatibilityError):owner.effective_runtime(root,pinned=pinned)
        finally:
            path.write_bytes(raw)
            os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        assert owner.effective_runtime(root,pinned=pinned)['manifest']['profiles']==['news']

    graph=decision_graph(control);tid=target_id(target);head=graph['heads'][tid]
    operation=uuid.uuid4().hex
    proposal=preview(control,runtime.database_path,news['actor'],operation,[{
        'target_id':tid,'target':target,'action':'withdraw','parent':head['head'],
        'withdraws':head['effective'],'reason':'Explicit isolated invalidation regression'}])
    decide(control,runtime.database_path,news['actor'],operation,proposal['preview_ref']['sha256'])
    with pytest.raises(CompatibilityError):owner.effective_runtime(root,pinned=pinned)


def test_fingerprint_includes_private_qualification_data_and_complete_inventory(tmp_path):
    root=tmp_path/'origin';data=root/'data';data.mkdir(parents=True)
    (root/'output').mkdir()
    ledger=data/'content_ledger_v1.json';ledger.write_bytes(b'{"value":1}\n')
    original=validation_fingerprint((root,));stamp=ledger.stat()
    ledger.write_bytes(b'{"value":2}\n');os.utime(ledger,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    assert validation_fingerprint((root,))!=original
    ledger.write_bytes(b'{"value":1}\n')
    assert validation_fingerprint((root,))==original
    extra=data/'unexpected.json';extra.write_bytes(b'{}')
    assert validation_fingerprint((root,))!=original
    extra.unlink()  # Only this disposable pytest file.
    (root/'output'/'published.xlsx').write_bytes(b'PK-exact-publication')
    assert validation_fingerprint((root,))!=original


def test_resolved_ref_keeps_native_sha_boundary_and_fresh_reads(tmp_path):
    from profile_compatibility_decisions_v1_1 import ref,resolve_ref
    from human_review_operations_v1 import io_path
    path=tmp_path/'source.json';path.write_text('{"known":true}\n',encoding='utf-8')
    reference=ref(tmp_path,path)
    assert resolve_ref(tmp_path,reference)==path.resolve()
    assert io_path(path.resolve(),resolved=True)==io_path(path)
    path.write_text('{"known":null}\n',encoding='utf-8')
    with pytest.raises(CompatibilityError):resolve_ref(tmp_path,reference)
    with pytest.raises(CompatibilityError):resolve_ref(tmp_path,{'path':'../source.json','sha256':reference['sha256']})


def test_native_news_click_path_latency_and_single_delivery(node):
    """Real HTTP/Task/Human/Export chain; only the external transport is synthetic."""
    from fastapi.testclient import TestClient
    from app.main import build_app
    from app.task_service import get_task
    from app.database import connect
    from test_news_generation_recovery_v1 import worker,calls as model_calls
    from test_news_qualification_complete_v1_2 import native_task
    runtime,business,_,_,_=native_news_runtime(node)
    timings={}
    def timed(name,function):
        started=time.perf_counter();value=function();timings[name]=time.perf_counter()-started
        return value
    with TestClient(build_app(runtime)) as client:
        login=client.post('/api/auth/login',json={'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login.json()['csrf_token']}
        chosen=timed('preview',lambda:client.post('/api/create/novel-news/preview',headers=headers,json={
            'business_id':business['business_id'],'speaker_id':business['speaker_id']}))
        assert chosen.status_code==200,chosen.text
        selected=chosen.json()['projection']['opportunities'][0]['concept_id']
        created=timed('confirm',lambda:client.post('/api/create/confirm',headers=headers,json={
            'business_id':business['business_id'],'speaker_id':business['speaker_id'],'profile':'news',
            'requested_quantity':1,'confirmed_quantity':1,'idempotency_key':'latency_native_once',
            'selected_opportunity_id':selected}))
        assert created.status_code==200,created.text
        rid=created.json()['result']['request_id'];url='/api/create/novel-news/'+rid
        assert timed('sources',lambda:client.post('/api/create/'+rid+'/resolve-sources',headers=headers)).status_code==200
        generated=timed('generation_admission',lambda:client.post(url+'/generate',headers=headers))
        assert generated.status_code==200,generated.text
        tid=generated.json()['task']['task_id']
        process=timed('generation_worker',lambda:worker(runtime,tid,'success'))
        assert process.returncode==0,(process.stdout,process.stderr)
        assert get_task(runtime.database_path,tid)['status']=='completed'
        assert len(model_calls(runtime.pipeline_root,rid))==1
        state=timed('review_load',lambda:client.get(url+'/state')).json()['state']
        assert state['stage']=='review' and len(state['beats'])==4
        result=timed('review_submit',lambda:client.post(url+'/review',headers=headers,json={
            'decisions':[{'beat_id':b['beat_id'],'decision':'approved','revised_text':b['text']} for b in state['beats']]}))
        assert result.status_code==200,result.text
        export=timed('export_admission',lambda:client.post(url+'/export',headers=headers))
        export_tid=timed('export_worker',lambda:native_task(runtime,export))
        workbook=timed('download',lambda:client.get(url+'/excel'))
        assert workbook.status_code==200 and workbook.content[:2]==b'PK'
        with connect(runtime.database_path) as db:
            before=db.execute('select count(*) from tasks where subject_ref=?',(rid,)).fetchone()[0]
        replay=client.post(url+'/export',headers=headers)
        assert replay.status_code==200 and replay.json()['accepted'] is False
        assert replay.json()['task']['task_id']==export_tid
        with connect(runtime.database_path) as db:
            assert db.execute('select count(*) from tasks where subject_ref=?',(rid,)).fetchone()[0]==before==2
        ledger=read(runtime.pipeline_root/'data/content_ledgers'/business['business_id']/'content_ledger_v1.json')
        assert len([e for e in ledger['entries'] if e['content_id']==rid+'-N001'])==1
        assert len([e for e in ledger['extensions']['presentation_history_v1']['entries'] if e['presentation_id']==rid+'-P001'])==1
    destination=os.environ.get('AIVO_VERIFICATION_ARTIFACTS')
    if destination:
        Path(destination).mkdir(parents=True,exist_ok=True)
        (Path(destination)/'native-click-path-latency.json').write_text(json.dumps({
            'seconds':timings,'request_id':rid,'scope':'isolated qualification, synthetic external transport only',
            'model_calls':1,'tasks':2,'semantic_entries':1,'presentations':1},indent=2),encoding='utf-8')
