"""No v1.1-to-v1 evidence downgrade; real HTTP, CLI and immutable commands."""
import base64
import json
import os
import subprocess
import sys
import pytest

from app import review_commands
from app.canonical_gateway import _prepare_final_evidence_review
from app.case_library_access import principal
from case_human_review_v2 import quality_context
from test_case_evidence_revision_v1 import node, native_source, final_payload
from test_case_library_security_v1 import ready, CASE_ID
from review_protocol import historical_case_context, frozen_v11_context

URL = f'/api/cases/{CASE_ID}'


def payload(detail, decisions):
    return {'decision': 'approve', 'review_context': frozen_v11_context(detail['approval_context']['token']),
            'evidence_review': decisions, 'quality_decision': {
                **detail['quality_context'], 'decision': 'suitable', 'origin': 'human_final_confirmation'}}


def test_http_v11_scope_unavailable_cannot_downgrade_to_keep(node):
    _, _, candidate, decisions, _, _ = ready(node)
    client, headers, _ = node[1]['C']
    detail = client.get(URL).json()
    context = json.loads(base64.urlsafe_b64decode(frozen_v11_context(detail['approval_context']['token']).split('.')[0]))
    assert context['version'] == review_commands.CASE_VERSION
    assert context['snapshot']['scope_sha256'] is None
    assert detail['evidence_workspace']['state'] == 'unavailable'
    before = candidate.read_bytes()
    result = client.post(URL + '/review', headers=headers, json=payload(detail, decisions))
    assert result.status_code == 409, f'HTTP {result.status_code}; approved={result.json().get("case", {}).get("review", {}).get("approved")}'
    assert result.json()['detail']['code'] == 'CASE_EVIDENCE_SCOPE_UNAVAILABLE'
    assert candidate.read_bytes() == before
    assert not (node[0].pipeline_root / 'data/cases' / CASE_ID / 'approval_receipt.json').exists()
    assert not (candidate.parents[2] / 'case_evidence_final_review_v1.json').exists()


@pytest.mark.parametrize('available,authorized', [(False, True), (True, True), (False, False)])
def test_cli_v11_durable_intent_cannot_downgrade_to_v1_receipt(node, available, authorized):
    settings = node[0]
    if available:
        native_source(node, uncertain=True)
        from app.canonical_gateway import _find_case_path
        candidate = _find_case_path(settings, CASE_ID)[0]
    else:
        _, _, candidate, decisions, _, _ = ready(node)
    client = node[1]['C'][0]
    detail = client.get(URL).json()
    if available:
        decisions = legacy_keep(detail)
    data = payload(detail, decisions)
    command = review_commands.begin(settings, 'case', CASE_ID, 3, data['review_context'],
        {'request_path': URL + '/review', 'payload': {k:v for k,v in data.items() if k != 'review_context'}})
    # A valid old receipt is not proof of v1.1 Coverage. Never mock CLI Gates.
    receipt = _prepare_final_evidence_review(candidate, json.loads(candidate.read_text(encoding='utf-8')),
        decisions, reviewer='13900000003', reviewer_user_id=3)
    quality = candidate.parent / 'synthetic-quality.json'
    quality.write_text(json.dumps({**quality_context(candidate), 'decision': 'suitable',
        'origin': 'human_final_confirmation'}), encoding='utf-8')
    actor = principal(settings, 3)
    arguments = [sys.executable, str(settings.pipeline_root / 'scripts/approve_case_v1.py'),
        '--case', str(candidate), '--reviewer', '13900000003', '--quality-decision', str(quality),
        '--evidence-review-receipt', str(receipt), '--review-operation-id', command['context']['operation_id']]
    if authorized:
        arguments += ['--console-authority-db', str(settings.database_path), '--console-user-id', '3',
                      '--console-principal-namespace', actor['namespace']]
    result = subprocess.run(arguments, capture_output=True, text=True, encoding='utf-8',
        env={**os.environ, 'PYTHONUTF8': '1'})
    assert result.returncode == 2, f'CLI exit={result.returncode}; receipt_written={(candidate.parent / "approval_receipt.json").exists()}'
    assert ('CASE_EVIDENCE_SCOPE_STALE' if available or not authorized else 'CASE_EVIDENCE_SCOPE_UNAVAILABLE') in result.stdout
    assert not (candidate.parent / 'approval_receipt.json').exists()


def legacy_keep(detail):
    evidence = detail['evidence_review']
    return {key: evidence[key] for key in ('candidate_sha256', 'narration_sha256', 'shot_sha256')} | {
        'narration_decisions': [{'item_id': r['item_id'], 'action': 'keep'} for r in evidence['narration_items']],
        'shot_decisions': [{'item_id': r['item_id'], 'action': 'keep'} for r in evidence['shot_items']]}


@pytest.mark.parametrize('kind', ['missing', 'legacy', 'new_scope'])
def test_scope_missing_rejects_every_submission_format(node, kind):
    _, _, candidate, decisions, _, _ = ready(node)
    client, headers, _ = node[1]['C']
    detail = client.get(URL).json()
    evidence = None if kind == 'missing' else decisions if kind == 'legacy' else {
        'schema_version': 'case-evidence-final-review-v2.0', 'confirmation_mode': 'final_bulk_keep',
        'scope_sha256': '0' * 64, 'explicit_keep_ids': []}
    result = client.post(URL + '/review', headers=headers, json=payload(detail, evidence))
    assert result.status_code == 409 and result.json()['detail']['code'] == 'CASE_EVIDENCE_SCOPE_UNAVAILABLE'
    assert not list(candidate.parents[2].glob('final_reviews/*.json'))
    assert not (candidate.parents[2] / 'case_evidence_final_review_v1.json').exists()


@pytest.mark.parametrize('dependency', ['visual_manifest', 'visual_v1'])
def test_missing_native_dependency_is_not_a_legacy_eligibility(node, dependency):
    native_source(node)
    from app.canonical_gateway import _find_case_path
    candidate = _find_case_path(node[0], CASE_ID)[0]
    client, headers, _ = node[1]['C']
    before = client.get(URL).json()
    candidate_value = json.loads(candidate.read_text(encoding='utf-8'))
    from pathlib import Path
    Path(candidate_value['source_artifacts'][dependency]).unlink()  # Fictional test graph only.
    detail = client.get(URL).json()
    assert detail['approval_context']['version'] == review_commands.JOINT_CASE_VERSION
    assert detail['approval_context']['scope_error']['code'] == 'CASE_EVIDENCE_SCOPE_UNAVAILABLE'
    assert not detail['evidence_workspace']['can_approve']
    data = payload({**detail, 'quality_context': before['quality_context']}, None)
    result = client.post(URL + '/review', headers=headers, json=data)
    assert result.status_code == 409 and result.json()['detail']['code'] == 'CASE_EVIDENCE_SCOPE_UNAVAILABLE'
    assert not (node[0].pipeline_root / 'data/cases' / CASE_ID / 'approval_receipt.json').exists()


def test_mismatched_new_scope_is_rejected_then_exact_scope_can_approve(node):
    native_source(node)
    client, headers, _ = node[1]['C']
    detail = client.get(URL).json()
    data = final_payload(detail)
    data['evidence_review']['scope_sha256'] = '0' * 64
    result = client.post(URL + '/review', headers=headers, json=data)
    assert result.status_code == 409 and result.json()['detail']['code'] == 'CASE_EVIDENCE_SCOPE_STALE'
    assert not list(node[0].pipeline_root.glob('data/case_analysis_attempts/*/*/final_reviews/*.json'))
    # A rejected intent stays immutable; a fresh exact context is a distinct operation.
    current = client.get(URL).json()
    result = client.post(URL + '/review', headers=headers, json=final_payload(current))
    assert result.status_code == 200 and result.json()['case']['review']['approved']


def test_real_v10_context_keeps_frozen_review_contract(node):
    _, _, candidate, decisions, _, _ = ready(node)
    client, headers, _ = node[1]['C']
    detail = client.get(URL).json()
    assert detail['approval_context']['version'] == review_commands.JOINT_CASE_VERSION
    data = payload(detail, decisions)
    data['review_context'] = historical_case_context(client, detail)
    frozen = json.loads(base64.urlsafe_b64decode(data['review_context'].split('.')[0]))
    assert frozen['version'] == review_commands.VERSION and 'scope_sha256' not in frozen['snapshot']
    result = client.post(URL + '/review', headers=headers, json=data)
    assert result.status_code == 200 and result.json()['case']['review']['approved']
    assert (candidate.parents[2] / 'case_evidence_final_review_v1.json').is_file()


def test_saved_v11_null_scope_cannot_resume_as_legacy_after_restart(node, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import build_app, CaseReviewRequest
    _, _, _, decisions, _, _ = ready(node)
    client, headers, _ = node[1]['C']
    detail = client.get(URL).json()
    data = payload(detail, decisions)
    command = review_commands.begin(node[0], 'case', CASE_ID, 3, data['review_context'],
        {'request_path': URL + '/review', 'payload': CaseReviewRequest(**data).model_dump(exclude={'review_context'}, exclude_none=True)})
    monkeypatch.setattr(review_commands, '_KEY', b'new process signing key')
    with TestClient(build_app(node[0])) as restarted:
        restarted.cookies.update(client.cookies)
        result = restarted.post(URL + '/review', headers=headers, json=data)
    assert result.status_code == 409 and result.json()['detail']['code'] == 'CASE_EVIDENCE_SCOPE_UNAVAILABLE'
    assert not (command['directory'] / 'result.json').exists()
    assert not (node[0].pipeline_root / 'data/cases' / CASE_ID / 'approval_receipt.json').exists()


def test_saved_exact_v11_scope_with_lost_dependency_is_business_conflict(node):
    from pathlib import Path
    from app.main import CaseReviewRequest
    from app.canonical_gateway import _find_case_path
    native_source(node)
    client, headers, _ = node[1]['C']
    data = final_payload(client.get(URL).json())
    command = review_commands.begin(node[0], 'case', CASE_ID, 3, data['review_context'],
        {'request_path': URL + '/review', 'payload': CaseReviewRequest(**data).model_dump(exclude={'review_context'}, exclude_none=True)})
    candidate = _find_case_path(node[0], CASE_ID)[0]
    value = json.loads(candidate.read_text(encoding='utf-8'))
    Path(value['source_artifacts']['visual_manifest']).unlink()
    result = client.post(URL + '/review', headers=headers, json=data)
    assert result.status_code == 409 and result.json()['detail']['code'] == 'CASE_EVIDENCE_SCOPE_UNAVAILABLE'
    assert not (command['directory'] / 'result.json').exists()
    assert not (node[0].pipeline_root / 'data/cases' / CASE_ID / 'approval_receipt.json').exists()
