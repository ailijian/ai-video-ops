from dataclasses import replace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.auth_service import provision_user
from app.config import Settings
from app.database import connect
from app.main import build_app
from app.background_task_service import BackgroundTaskRunner
from app.creation_batch_gateway import advance, advance_batches
from app.release_availability import batch_task_disabled
from conftest import login_and_change_password


def test_environment_batch_rollout_is_default_closed(monkeypatch):
    monkeypatch.delenv('AIVO_CREATION_BATCH_ENABLED', raising=False)
    monkeypatch.delenv('AIVO_ENV_FILE', raising=False)
    assert not Settings.from_environment().creation_batch_enabled
    monkeypatch.setenv('AIVO_CREATION_BATCH_ENABLED', '1')
    assert Settings.from_environment().creation_batch_enabled
    monkeypatch.setenv('AIVO_CREATION_BATCH_ENABLED', 'unknown')
    assert not Settings.from_environment().creation_batch_enabled


@pytest.mark.parametrize('suffix,body', [
    ('preview', {'business_id':'fictional','speaker_id':'fictional','configuration':{},'operation_id':'release_gate'}),
    ('confirm', {'business_id':'fictional','speaker_id':'fictional','configuration':{},'operation_id':'release_gate','preflight_sha256':'a'*64}),
    ('batch_fictional/control', {'action':'resume','operation_id':'release_gate'}),
])
def test_closed_batch_http_never_admits_or_mutates(settings, suffix, body):
    runtime = replace(settings, creation_batch_enabled=False)
    with TestClient(build_app(runtime)) as client:
        provision_user(runtime.database_path, '13800000000')
        csrf = login_and_change_password(client)
        response = client.post('/api/create/batches/'+suffix, headers={'X-CSRF-Token':csrf}, json=body)
        assert response.status_code == 503, response.text
        assert response.json()['detail']['code'] == 'CREATION_BATCH_NOT_ENABLED'
        with connect(runtime.database_path) as db:
            assert db.execute('SELECT count(*) FROM tasks').fetchone()[0] == 0
        assert not (runtime.pipeline_root/'data/creation_batches').exists()


def test_disabled_maintenance_never_opens_a_batch(settings):
    runtime = replace(settings, creation_batch_enabled=False)
    assert advance(runtime, 'does_not_exist') == {'advanced':False,'reason':'batch_not_enabled'}
    assert advance_batches(runtime) is None


def test_disabled_runner_preserves_unclaimed_batch_and_does_not_call_handler(settings, monkeypatch):
    import app.background_task_service as service
    task = {'task_id':'release_pending','payload':{'operation':'creation_batch_export'}}
    monkeypatch.setattr(service, 'get_task', lambda *args: task)
    claim = Mock(side_effect=AssertionError('Disabled batch was claimed'))
    monkeypatch.setattr(service, 'claim_task', claim)
    runner = BackgroundTaskRunner(replace(settings, creation_batch_enabled=False))
    try:
        runner._run('release_pending')
        claim.assert_not_called()
    finally:
        runner.close()


def test_disabled_runner_checks_native_request_reference_without_mutation(settings):
    import json
    path = settings.pipeline_root/'data/generation_requests/gen_release_gate/generation_request_v1.json'
    path.parent.mkdir(parents=True)
    content = json.dumps({'request_id':'gen_release_gate','batch_admission_ref':{'id':'batch_fictional'}})
    path.write_text(content, 'utf-8')
    task = {'subject_ref':'gen_release_gate','payload':{'operation':'script_generation'}}
    assert batch_task_disabled(replace(settings, creation_batch_enabled=False),task)
    assert not batch_task_disabled(replace(settings, creation_batch_enabled=True),task)
    assert path.read_text('utf-8') == content


def test_closed_batch_is_not_rescheduled_by_an_enabled_background_worker(settings, monkeypatch):
    import app.background_task_service as service
    task = {'task_id':'preserved_pending','payload':{'operation':'creation_batch_export'}}
    monkeypatch.setattr(service, 'iter_queued_tasks', lambda *args,**kwargs: [task])
    runtime = replace(settings, creation_batch_enabled=False, background_worker_enabled=True)
    runner = BackgroundTaskRunner(runtime)
    submit = Mock(side_effect=AssertionError('Closed batch entered the executor'))
    monkeypatch.setattr(runner.executor, 'submit', submit)
    try:
        runner.schedule_pending()
        runner.schedule_pending()
        submit.assert_not_called()
        assert runner._scheduled == set()
        assert task['task_id'] == 'preserved_pending'
    finally:
        runner.close()
