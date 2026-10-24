"""Completion wakes the existing single worker without weakening leases."""
from concurrent.futures import wait as real_wait
from threading import Event

import pytest

import app.background_task_service as background
from app.task_service import STANDARD_BACKGROUND, get_task, submit_task


@pytest.mark.parametrize('fail', [False, True])
def test_completion_wakes_worker_and_preserves_heartbeats_and_failure(client, settings, monkeypatch, fail):
    release = Event()
    waits = []
    heartbeats = []
    original_update = background.update_task

    def handler(*args, **kwargs):
        assert release.wait(3), 'Worker never waited for completion'
        if fail:
            raise TimeoutError('A provider failure is not a heartbeat timeout')

    def wait_for_completion(futures, timeout):
        waits.append(timeout)
        if len(waits) == 1:
            # The operation is still running: renew the original lease again.
            return set(), set(futures)
        release.set()
        return real_wait(futures, timeout=timeout)

    def update(*args, **kwargs):
        if kwargs.get('status') == 'running':
            heartbeats.append(kwargs)
        return original_update(*args, **kwargs)

    task = submit_task(settings.database_path, task_id_prefix='completion-wait',
        task_type='content_generation', subject_ref='fictional-wait',
        operation_identity='completion-wait', execution_lane=STANDARD_BACKGROUND,
        payload={'operation':'publish_copy_generate','request_id':'fictional-wait','publish_copy':{}},
        stage='等待测试', created_by_user_id=1, queue_max=settings.task_queue_max,
        gpu_pending_per_user_max=settings.gpu_pending_per_user_max)
    runner = background.BackgroundTaskRunner(settings)
    runner.handlers['publish_copy_generate'] = handler
    monkeypatch.setattr(background, 'wait', wait_for_completion)
    monkeypatch.setattr(background, 'update_task', update)
    try:
        runner._run(task['task_id'])
        actual = get_task(settings.database_path, task['task_id'])
        assert actual['status'] == ('failed' if fail else 'completed')
        assert actual['attempt_count'] == 1
        assert len(waits) >= 2 and all(t == 1.0 for t in waits)
        assert len(heartbeats) >= 2
        assert all(h['lease_seconds'] == settings.task_lease_seconds for h in heartbeats)
        assert all(h['heartbeat_interval_seconds'] == settings.task_heartbeat_seconds for h in heartbeats)
    finally:
        release.set()
        runner.close()
