"""HTTP trust boundary and scoped original Task-store idempotency."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import threading

import pytest
from fastapi.testclient import TestClient
from app.auth_service import provision_user
from app.main import build_app
from app.task_service import (STANDARD_BACKGROUND, TaskSubmissionError, get_task,
    submit_task, update_task, resume_generation_recovery_task)
from test_content_delivery_console_v1 import login


def submitted(settings, operation=None, intent='a'*64):
    payload={'operation':'script_generation','request_id':'gen_unit_recovery'}
    if operation:
        payload['generation_recovery']={'operation_id':operation,'intent_sha256':intent}
    return submit_task(settings.database_path,task_id_prefix='generation-unit',task_type='content_generation',
        subject_ref='gen_unit_recovery',operation_identity='script_generation:gen_unit_recovery',
        execution_lane=STANDARD_BACKGROUND,payload=payload,stage='queued',created_by_user_id=1,
        queue_max=20,gpu_pending_per_user_max=1)


def test_retry_http_requires_real_session_csrf_and_has_no_path_or_force_input(settings):
    with TestClient(build_app(settings)) as client:
        path='/api/create/gen_unit_recovery/generation-recovery/'
        assert client.post(path+'preview',json={'operation_id':'a'*32}).status_code==401
        provision_user(settings.database_path,'13800000000')
        headers={'X-CSRF-Token':login(client)}
        assert client.post(path+'preview',json={'operation_id':'a'*32}).status_code==403
        for extra in [{'force':True},{'skip_stage':True},{'batch_path':'../outside'},{'actor':{'user_id':2}}]:
            assert client.post(path+'preview',headers=headers,json={'operation_id':'a'*32,**extra}).status_code==422
        assert client.post(path+'confirm',headers=headers,json={'operation_id':'a'*32,'preview_sha256':'b'*64,'output_root':'/outside'}).status_code==422
        assert not list(settings.pipeline_root.glob('data/generation_batches/*/recovery/*/intent.json'))


@pytest.mark.parametrize('status',['queued','running','failed','completed'])
def test_same_generation_operation_dedups_across_all_states(settings,status):
    with TestClient(build_app(settings)):
        provision_user(settings.database_path,'13800000000')
        original=submitted(settings,'b'*32)
        if status!='queued':update_task(settings.database_path,original['task_id'],status=status,stage='unit fixture')
        assert submitted(settings,'b'*32)['task_id']==original['task_id']
        with pytest.raises(TaskSubmissionError):submitted(settings,'b'*32,'c'*64)


def test_concurrent_identical_generation_submissions_have_one_original_task(settings):
    with TestClient(build_app(settings)):
        provision_user(settings.database_path,'13800000000')
        with ThreadPoolExecutor(max_workers=4) as pool:
            tasks=list(pool.map(lambda _:submitted(settings,'d'*32),range(4)))
        assert len({x['task_id'] for x in tasks})==1


def test_generic_failed_operation_can_still_make_a_new_legal_retry(settings):
    with TestClient(build_app(settings)):
        provision_user(settings.database_path,'13800000000')
        first=submitted(settings)
        update_task(settings.database_path,first['task_id'],status='failed',stage='unit fixture')
        second=submitted(settings)
        assert first['task_id']!=second['task_id']
        assert get_task(settings.database_path,first['task_id'])['status']=='failed'


def test_new_intent_cannot_be_mistaken_for_an_active_legacy_generation_task(settings):
    with TestClient(build_app(settings)):
        provision_user(settings.database_path,'13800000000')
        first=submitted(settings)
        with pytest.raises(TaskSubmissionError,match='still active'):
            submitted(settings,'f'*32)
        assert get_task(settings.database_path,first['task_id'])['payload'].get('generation_recovery') is None


def test_recovery_resume_keeps_same_task_and_preserves_queue_capacity(settings):
    with TestClient(build_app(settings)):
        provision_user(settings.database_path,'13800000000')
        task=submitted(settings,'e'*32)
        update_task(settings.database_path,task['task_id'],status='failed',stage='unit fixture')
        with pytest.raises(TaskSubmissionError):resume_generation_recovery_task(settings.database_path,task['task_id'],queue_max=0)
        resumed=resume_generation_recovery_task(settings.database_path,task['task_id'],queue_max=20)
        assert resumed['status']=='queued' and resumed['task_id']==task['task_id']


def test_export_submission_uses_the_original_business_lock_before_enqueue(settings):
    from app.operation_lock import operation_lock,scoped_lock_key
    from app.database import connect
    path=settings.pipeline_root/'data/generation_requests/gen_unit_export/generation_request_v1.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({'schema_version':'generation-request-v1.0','request_id':'gen_unit_export','persona_id':'fixture_pet_store'}),encoding='utf-8')
    held,release=threading.Event(),threading.Event()
    def writer():
        with operation_lock(settings.pipeline_root,scoped_lock_key('business','fixture_pet_store')):
            held.set()
            assert release.wait(15)
    with TestClient(build_app(settings)) as client,ThreadPoolExecutor(max_workers=1) as pool:
        provision_user(settings.database_path,'13800000000')
        headers={'X-CSRF-Token':login(client)}
        future=pool.submit(writer)
        assert held.wait(5)
        try:
            denied=client.post('/api/create/gen_unit_export/export-mix',headers=headers)
            assert denied.status_code==409,denied.text
            db=connect(settings.database_path)
            try:assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==0
            finally:db.close()
        finally:
            release.set()
            future.result()
        accepted=client.post('/api/create/gen_unit_export/export-mix',headers=headers)
        assert accepted.status_code==409 and accepted.json()['detail']['code']=='HUMAN_BUNDLE_INVALID',accepted.text
        db=connect(settings.database_path)
        try:assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==0
        finally:db.close()
