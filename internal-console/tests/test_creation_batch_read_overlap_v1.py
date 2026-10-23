"""Read overlap keeps original proof and exact bytes; it grants no approval."""
import json,os
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from dataclasses import replace
from fastapi.testclient import TestClient

import app.creation_batch_gateway as gateway
from app.canonical_gateway import CanonicalOperationError
from app.background_task_service import BackgroundTaskRunner
from app.main import build_app
from conftest import login_and_change_password


def proof_files(tmp_path):
    base=tmp_path/'data/generation_batches/gen_unit';base.mkdir(parents=True)
    receipt=base/'generation_batch_approval_receipt.json'
    reviewed=base/'approved_generation_batch_v1.json'
    # These intentionally incomplete records are unit witnesses, never Native
    # qualification. The real Native validation is covered by integration tests.
    receipt.write_text(json.dumps({'status':'approved','source_batch':{'path':'unit-source.json'}}))
    reviewed.write_text('{"unit":"approved"}')
    proof={'receipt':gateway.read(receipt),'receipt_path':receipt,'receipt_sha':gateway.file_sha(receipt),
        'reviewed':reviewed,'reviewed_sha':gateway.file_sha(reviewed),'source':tmp_path/'unit-source.json'}
    return proof,{'approved':True,'sha256':proof['reviewed_sha']}


def test_mix_view_and_original_human_reader_overlap_without_skipping_an_admission(tmp_path,monkeypatch):
    rid='gen_unit';path=tmp_path/'request.json';path.write_text('{"batch_admission_ref":{}}')
    monkeypatch.setattr(gateway.native,'request_path',lambda *args:path)
    admission=Mock();monkeypatch.setattr(gateway.native,'validate_admission',admission)
    monkeypatch.setattr(gateway,'task_for',lambda *args:None)
    barrier=Barrier(2);seen=[]
    def source(*args):seen.append('human');barrier.wait(timeout=3);return None
    def view(*args):
        seen.append('view');barrier.wait(timeout=3)
        raise CanonicalOperationError('STOP_AFTER_OVERLAP','unit boundary','no output')
    monkeypatch.setattr(gateway,'_mix_review_source',source)
    monkeypatch.setattr(gateway,'get_content_delivery_state',view)
    group={'request_id':rid,'group_id':'g','profile':'mix','source_kind':'novel_content',
        'creative_style':{'style_id':'persona'},'slots':[]}
    with pytest.raises(CanonicalOperationError) as exc:
        gateway._native_group_projection(SimpleNamespace(pipeline_root=tmp_path),'unit',{},group)
    assert exc.value.code=='STOP_AFTER_OVERLAP'
    assert set(seen)=={'view','human'};admission.assert_called_once()


@pytest.mark.parametrize('changed',['receipt','reviewed','projection_sha','approval'])
def test_read_merge_rejects_changed_bytes_or_different_native_review_even_with_same_metadata(tmp_path,changed):
    proof,review=proof_files(tmp_path)
    assert gateway._current_mix_review_source(tmp_path,'gen_unit',review,proof)==proof['source']
    if changed in {'receipt','reviewed'}:
        path=proof['receipt_path'] if changed=='receipt' else proof['reviewed']
        stat=path.stat();value=path.read_bytes()
        # Equal size and original mtime cannot turn a stale SHA into proof.
        path.write_bytes(value.replace(b'approved',b'rejected'))
        os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        assert path.stat().st_size==stat.st_size
    elif changed=='projection_sha':review['sha256']='0'*64
    else:review['approved']=False
    with pytest.raises(CanonicalOperationError) as exc:
        gateway._current_mix_review_source(tmp_path,'gen_unit',review,proof)
    assert exc.value.code=='CREATION_BATCH_REVIEW_SOURCE_CHANGED'


def test_human_completion_during_parallel_read_reenters_original_proof(tmp_path,monkeypatch):
    proof,review=proof_files(tmp_path);native=Mock(return_value=proof)
    monkeypatch.setattr(gateway,'_mix_review_source',native)
    assert gateway._current_mix_review_source(tmp_path,'gen_unit',review,None)==proof['source']
    native.assert_called_once_with(tmp_path,'gen_unit')


def test_incomplete_human_bundle_is_not_treated_as_approved(tmp_path,monkeypatch):
    import delivery_receipt_recovery_v1 as human
    import generation_recovery_v1 as recovery
    monkeypatch.setattr(human,'human_state',lambda *args:{'completed':False})
    validator=Mock(side_effect=AssertionError('Incomplete Human operation was promoted'))
    monkeypatch.setattr(recovery,'validate_approved_source',validator)
    assert gateway._mix_review_source(tmp_path,'gen_unit') is None
    validator.assert_not_called()


def test_original_native_source_rejection_cannot_become_a_read_proof(tmp_path,monkeypatch):
    proof_files(tmp_path)
    import delivery_receipt_recovery_v1 as human
    import generation_recovery_v1 as recovery
    monkeypatch.setattr(human,'human_state',lambda *args:{'completed':True})
    def reject(*args):raise RuntimeError('Original source withdrawn')
    monkeypatch.setattr(recovery,'validate_approved_source',reject)
    with pytest.raises(RuntimeError,match='Original source withdrawn'):
        gateway._mix_review_source(tmp_path,'gen_unit')


def test_quiet_hint_skips_only_idle_coordination_and_keeps_lease_recovery_and_queued_work(settings,monkeypatch):
    import app.background_task_service as background
    runner=BackgroundTaskRunner(settings);events=[]
    monkeypatch.setattr(background,'recover_expired_tasks',lambda *args,**kw:events.append('recover'))
    advance=Mock(side_effect=lambda *args,**kw:events.append(('advance',kw)))
    monkeypatch.setattr(gateway,'advance_batches',advance)
    runner.schedule_pending=lambda:events.append('pending')
    try:
        epoch=runner.batch_read_epoch();runner.note_batch_read('batch_old',epoch,complete=True)
        runner._recover_and_schedule()
        assert events==['recover',('advance',{'skip_batches':frozenset({'batch_old'})}),'pending']
        runner.schedule();assert not runner._quiet_batches
        runner.note_batch_read('batch_old',epoch,complete=True)
        assert not runner._quiet_batches  # An older read cannot swallow a new wake.
        runner.note_batch_read('batch_old',runner.batch_read_epoch(),complete=True)
        runner.note_batch_read('batch_old',runner.batch_read_epoch(),complete=False)
        assert not runner._quiet_batches
    finally:runner.close()


def test_explicit_human_wake_clears_idle_hints_before_queueing(settings,monkeypatch):
    runner=BackgroundTaskRunner(replace(settings,background_worker_enabled=True))
    runner.executor.submit=Mock()
    try:
        epoch=runner.batch_read_epoch();runner.note_batch_read('batch_old',epoch,complete=True)
        runner.request_batch_advance('batch_old')
        assert not runner._quiet_batches and runner.batch_read_epoch()>epoch
        runner.note_batch_read('batch_old',epoch,complete=True)
        assert not runner._quiet_batches
        runner.executor.submit.assert_called_once_with(runner._advance_after_human,'batch_old')
    finally:runner.close()


def test_maintenance_exclusion_never_applies_to_explicit_gateway_reentry(tmp_path,monkeypatch):
    for bid in ['batch_old','batch_new']:
        path=tmp_path/'data/creation_batches'/bid/'intent.json';path.parent.mkdir(parents=True);path.write_text('{}')
    calls=[];monkeypatch.setattr(gateway,'advance',lambda settings,bid:calls.append(bid))
    runtime=SimpleNamespace(pipeline_root=tmp_path)
    gateway.advance_batches(runtime,skip_batches=frozenset({'batch_old'}))
    assert calls==['batch_new']
    calls.clear();gateway.advance_batches(runtime)
    assert calls==['batch_new','batch_old']


def test_http_never_serves_a_cached_completed_projection_and_native_rejection_still_fails(client,settings,monkeypatch):
    monkeypatch.setattr(BackgroundTaskRunner,'start',lambda self:None)
    notes=[];monkeypatch.setattr(BackgroundTaskRunner,'note_batch_read',lambda self,bid,epoch,**kw:notes.append((bid,kw)))
    original=Mock(return_value={'batch_id':'batch_unit','completion_proven':True})
    monkeypatch.setattr(gateway,'state',original)
    with TestClient(build_app(replace(settings,background_worker_enabled=True))) as client:
        login_and_change_password(client)
        for _ in range(2):assert client.get('/api/create/batches/batch_unit').status_code==200
        assert original.call_count==2 and len(notes)==2
        original.side_effect=CanonicalOperationError('SOURCE_WITHDRAWN','unit native rejection','stop')
        assert client.get('/api/create/batches/batch_unit').status_code>=400
        assert original.call_count==3 and len(notes)==2
