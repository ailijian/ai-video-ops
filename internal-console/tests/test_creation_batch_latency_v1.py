"""Latency boundaries must not replace fresh Native proof or serial dispatch."""
from dataclasses import replace
from threading import Barrier, Event, Lock, current_thread
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import app.creation_batch_gateway as gateway
import app.creation_batch_delivery_gateway as delivery
from app.background_task_service import BackgroundTaskRunner
from app.canonical_gateway import CanonicalOperationError
from app.main import build_app
from conftest import login_and_change_password


def test_group_reads_overlap_at_most_two_and_final_delivery_proof_stays_last(tmp_path, monkeypatch):
    groups=[{'group_id':f'g{i}','request_id':f'gen_{i}','profile':'mix','source_kind':'novel_content',
        'creative_style':{'style_id':'story'},'slots':[{'slot_id':f's{i}','business_type_id':'story','source_kind':'novel_content'}]} for i in range(4)]
    monkeypatch.setattr(gateway.native,'assert_principal',lambda *args:None)
    monkeypatch.setattr(gateway.native,'intent',lambda *args:(None,{'business_id':'fictional'}))
    monkeypatch.setattr(gateway.native,'controls',lambda *args:[])
    monkeypatch.setattr(gateway.native,'groups',lambda *args:groups)
    monkeypatch.setattr(gateway,'task_for',lambda *args:None)
    lock=Lock();barrier=Barrier(2);finished=[];active=0;maximum=0
    def project(_settings,_bid,_context,group,**kwargs):
        nonlocal active,maximum
        with lock:active+=1;maximum=max(maximum,active)
        barrier.wait(timeout=3)
        entry=gateway._group_entry(group)
        entry.update(generated=1,review_ready=True,review_complete=False)
        entry['slots'][0].update(generated=True,unknown=False,generation_failed=False)
        with lock:active-=1;finished.append(group['group_id'])
        return entry
    def composite(*args,**kwargs):
        assert len(finished)==4,'Final Native proof was read before the groups finished'
        return {'completed':[],'blocked':[]}
    monkeypatch.setattr(gateway,'_native_group_projection',project)
    monkeypatch.setattr(delivery,'owner',composite)
    result=gateway.state(SimpleNamespace(pipeline_root=tmp_path,publish_copy_enabled=True),'batch',{})
    assert maximum==2
    assert [g['group_id'] for g in result['groups']]==[g['group_id'] for g in groups]
    assert result['counts']['generated']==result['counts']['review_pending']==4
    assert result['counts']['approved']==result['counts']['delivered']==0
    assert not result['completion_proven']


def test_human_http_returns_original_result_without_inline_coordinator_scan(client,settings,monkeypatch):
    wakes=[]
    monkeypatch.setattr(BackgroundTaskRunner,'start',lambda self:None)
    monkeypatch.setattr(BackgroundTaskRunner,'request_batch_advance',lambda self,bid:wakes.append(bid))
    monkeypatch.setattr(gateway,'advance_batches',Mock(side_effect=AssertionError('HTTP performed an inline coordinator scan')))
    native_result={'all_native_completed':True,'results':[{'request_id':'original-native'}]}
    owner=Mock(return_value=native_result);monkeypatch.setattr(delivery,'owner',owner)
    with TestClient(build_app(replace(settings,background_worker_enabled=True))) as http:
        csrf=login_and_change_password(http)
        body={'scope':'native_content_review','items':[{'slot_id':'s1','decision':'approve'}],
            'operation_id':'explicit_human','source_sha256':'a'*64}
        response=http.post('/api/create/batches/batch_fictional/human-command',headers={'X-CSRF-Token':csrf},json=body)
        assert response.status_code==200,response.text
        assert response.json()=={'result':native_result}
        assert wakes==['batch_fictional']
        assert owner.call_args.args[2]=='execute'
        denied=http.post('/api/create/batches/batch_fictional/human-command',json=body)
        assert denied.status_code==403
        assert wakes==['batch_fictional']


def test_human_wakes_coalesce_on_the_original_serial_worker_without_losing_a_later_wake(settings,monkeypatch):
    entered=Event();release=Event();second=Event();calls=[]
    def advance(_settings,bid):
        calls.append((bid,current_thread().name))
        if len(calls)==1:
            entered.set();assert release.wait(3)
        else:second.set()
        return {'advanced':False,'reason':'paused_or_ended'}
    monkeypatch.setattr(gateway,'advance',advance)
    runner=BackgroundTaskRunner(replace(settings,background_worker_enabled=True))
    runner.schedule_pending=Mock()
    try:
        runner.request_batch_advance('batch_one');assert entered.wait(3)
        runner.request_batch_advance('batch_one');runner.request_batch_advance('batch_one')
        assert len(calls)==1
        release.set();assert second.wait(3)
        # This queued sentinel runs after the original wake callback exits.
        runner.executor.submit(lambda:None).result(timeout=3)
        assert len(calls)==2
        assert all(bid=='batch_one' and name.startswith('standard-background') for bid,name in calls)
        assert not runner._batch_wakes
        assert runner.operation_executor._max_workers==1
    finally:release.set();runner.close()


def test_failed_wake_does_not_poison_explicit_retry_or_create_business_truth(settings,monkeypatch):
    invoked=Event()
    def fail(*args):invoked.set();raise CanonicalOperationError('SOURCE_CHANGED','来源已变化','重新核对')
    monkeypatch.setattr(gateway,'advance',fail)
    runner=BackgroundTaskRunner(replace(settings,background_worker_enabled=True))
    runner.schedule_pending=Mock()
    try:
        runner.request_batch_advance('batch_one');assert invoked.wait(3)
        runner.executor.submit(lambda:None).result(timeout=3)
        assert not runner._batch_wakes;runner.schedule_pending.assert_not_called()
        invoked.clear();runner.request_batch_advance('batch_one');assert invoked.wait(3)
        runner.executor.submit(lambda:None).result(timeout=3)
        assert not runner._batch_wakes
    finally:runner.close()


def test_a_human_filename_hint_still_reenters_fresh_native_gates(tmp_path,monkeypatch):
    group={'request_id':'gen_one','profile':'mix','source_kind':'novel_content'}
    for name in ('generation_batch_approval_receipt.json','approved_generation_batch_v1.json'):
        p=tmp_path/'data/generation_batches/gen_one'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
    monkeypatch.setattr(gateway.native,'intent',lambda *args:(None,{'business_id':'fictional'}))
    monkeypatch.setattr(gateway.native,'running',lambda *args:True)
    monkeypatch.setattr(gateway.native,'groups',lambda *args:[group])
    monkeypatch.setattr(gateway.native,'settle',lambda *args:[])
    monkeypatch.setattr(gateway.native,'current_context',lambda *args:{'actor':{'user_id':1}})
    monkeypatch.setattr(gateway.native,'policy_qualification',lambda *args:None)
    monkeypatch.setattr(gateway,'task_for',lambda *args:None)
    monkeypatch.setattr(gateway,'get_content_delivery_state',Mock(side_effect=AssertionError('Duplicate generation read')))
    proof=Mock(return_value={'generation_quiescent':True,'verification_deferred':False,'counts':{'unknown':0,'unverified':1}})
    monkeypatch.setattr(gateway,'state',proof)
    result=gateway.advance(SimpleNamespace(pipeline_root=tmp_path,publish_copy_enabled=True),'batch_one')
    assert result=={'advanced':False,'reason':'native_recovery_required'}
    proof.assert_called_once()
