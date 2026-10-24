"""Failed Human Revision execution stays on its own authorized recovery path."""
import pytest
import uuid

from app.case_library_access import manage_reviewer
from app.task_service import get_task, update_task
from test_case_evidence_revision_v1 import node, native_source, edit_payload, model_boundary
from test_case_library_security_v1 import CASE_ID


@pytest.fixture(autouse=True)
def synthetic_task_ids_do_not_resemble_contact_information(monkeypatch):
    # Model provenance includes paths. Purely numeric random test IDs can look
    # like a phone number to the real Privacy gate; do not disable that gate.
    original = uuid.uuid4
    monkeypatch.setattr(uuid, 'uuid4', lambda: uuid.UUID('aaaaaaaa' + original().hex[8:]))


def failed_revision(node):
    native_source(node)
    client, headers, _ = node[1]['C']
    payload = edit_payload(client.get(f'/api/cases/{CASE_ID}').json())
    saved = client.post(f'/api/cases/{CASE_ID}/review-revisions', headers=headers, json=payload)
    assert saved.status_code == 200
    saved = saved.json()
    model_boundary(node, 'derive', node[0].pipeline_root, node[0].database_path, CASE_ID,
                   payload['attempt_id'], saved['revision_id'], saved['build_task_id'],
                   'build_narration_review_v1', expect_failure=True)
    update_task(node[0].database_path, saved['build_task_id'], status='failed',
                error_code='SYNTHETIC_MODEL_UNAVAILABLE', error_message='修改已保存，等待恢复校验。')
    return payload, saved


def test_failed_revision_detail_activity_and_refresh_are_read_only(node):
    payload, saved = failed_revision(node)
    client = node[1]['C'][0]
    before = {p:p.read_bytes() for p in node[0].pipeline_root.glob('data/**/*.json')}
    original_task = get_task(node[0].database_path, saved['build_task_id'])
    for _ in range(2):
        response = client.get('/api/tasks/' + saved['build_task_id'])
        assert response.status_code == 200
        detail = response.json()
        assert detail['boundary_review'] is None
        assert detail['task']['task_id'] == saved['build_task_id']
        assert detail['task']['payload']['evidence_revision']['attempt_id'] == payload['attempt_id']
        assert detail['task']['error_message'] == '修订校验没有完成，已保存的修改仍然保留。'
        assert 'current_active_task_id' not in detail['task']  # Original analysis is a different execution.
    activity = client.get('/api/tasks/activity')
    assert activity.status_code == 200 and saved['build_task_id'] in activity.text
    assert all(p.read_bytes() == data for p,data in before.items())
    assert get_task(node[0].database_path, saved['build_task_id']) == original_task


@pytest.mark.parametrize('role', ['A', 'B', 'D'])
def test_failed_revision_detail_retry_and_activity_preserve_object_scope(node, role):
    _, saved = failed_revision(node)
    client, headers, _ = node[1][role]
    url = '/api/tasks/' + saved['build_task_id']
    assert client.get(url).status_code == 404
    assert client.post(url+'/retry', headers=headers).status_code == 404
    activity = client.get('/api/tasks/activity')
    assert activity.status_code == 200 and saved['build_task_id'] not in activity.text
    tasks = client.get('/api/tasks')
    assert tasks.status_code == 200 and saved['build_task_id'] not in tasks.text
    assert get_task(node[0].database_path, saved['build_task_id'])['status'] == 'failed'


def test_revision_retry_requires_csrf_and_current_reviewer_and_forbids_old_boundary_review(node):
    _, saved = failed_revision(node)
    client, headers, _ = node[1]['C']
    url = '/api/tasks/' + saved['build_task_id']
    assert client.post(url+'/retry').status_code == 403
    old = client.post(url+'/boundary-review', headers=headers, json={
        'shot_sha256':'0'*64, 'decisions':[{'frame_id':'frame_000000000ms.jpg','action':'keep'}]})
    assert old.status_code == 409 and old.json()['detail']['code'] == 'CASE_EVIDENCE_SCOPE_STALE'
    manage_reviewer(node[0], 3, action='revoke', operator='isolated-test-operator', reason='Revocation regression')
    assert client.post(url+'/retry', headers=headers).status_code == 403
    assert client.get(url).status_code == 200  # Original trusted task creator may still read history.
    assert get_task(node[0].database_path, saved['build_task_id'])['status'] == 'failed'
