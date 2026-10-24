"""Portable activated-release consumers; native pack/activation and fail-closed reads."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from test_profile_compatibility_release_v1_1 import release_node, pack, activate
from test_profile_compatibility_v1_1 import compat, execute, request
from profile_compatibility_contract_v1_1 import CompatibilityError
from profile_compatibility_decisions_v1_1 import decision_graph, file_sha, read, write_once
from profile_compatibility_release_v1_1 import CONFIG, effective_runtime
from resolve_generation_content_plan_v1 import (
    ContentPlanResolutionError, resolve_pattern_path, resolve_fingerprint_paths,
)


def source_plan(node):
    activate(node, pack(node))
    runtime = node[6]
    active = effective_runtime(runtime)
    targets = [v['target'] for v in active['graph']['heads'].values() if v['effective']]
    return runtime, {
        'profile_compatibility_v1_1': active['binding'],
        'selected_patterns': [{'pattern_id': targets[0]['pattern_id'],
            'approved_pattern_sha': targets[0]['pattern_ref']['sha256']}],
        'eligible_case_pool': [{'case_id': t['case_id'], 'fingerprint_sha': t['fingerprint_ref']['sha256']} for t in targets],
    }


def test_separate_release_artifacts_and_legacy_copies_cannot_override(release_node):
    root, plan = source_plan(release_node)
    assert not (root / 'data/patterns/approved').exists()
    assert not (root / 'data/fingerprints').exists()
    pattern = resolve_pattern_path(root, plan)
    fingerprints = resolve_fingerprint_paths(root, plan)
    assert 'staged' in pattern.parts
    assert file_sha(pattern) == plan['selected_patterns'][0]['approved_pattern_sha']
    assert [file_sha(p) for p in fingerprints] == [v['fingerprint_sha'] for v in plan['eligible_case_pool']]
    # A stale/co-located artifact must not create ambiguity or become fallback.
    write_once(root / 'data/patterns/approved/stale/pattern_v1.json',
        {'pattern_id': plan['selected_patterns'][0]['pattern_id'], 'status': 'approved'})
    write_once(root / 'data/fingerprints' / plan['eligible_case_pool'][0]['case_id'] / 'case_fingerprint_v1.json',
        {'case_id': plan['eligible_case_pool'][0]['case_id'], 'stale': True})
    assert resolve_pattern_path(root, plan) == pattern
    assert resolve_fingerprint_paths(root, plan) == fingerprints


@pytest.mark.parametrize('change', ['missing_pin', 'stale_pin', 'pattern_sha', 'fingerprint_sha', 'unknown_case', 'missing_config', 'bundle_changed', 'withdrawn'])
def test_release_source_mismatch_never_falls_back(release_node, change):
    root, plan = source_plan(release_node)
    if change == 'missing_pin':
        del plan['profile_compatibility_v1_1']
    elif change == 'stale_pin':
        plan['profile_compatibility_v1_1']['decision_head_sha256'] = '0' * 64
    elif change == 'pattern_sha':
        plan['selected_patterns'][0]['approved_pattern_sha'] = '0' * 64
    elif change == 'fingerprint_sha':
        plan['eligible_case_pool'][0]['fingerprint_sha'] = '0' * 64
    elif change == 'unknown_case':
        plan['eligible_case_pool'][0]['case_id'] = 'not-approved'
    elif change == 'missing_config':
        (root / CONFIG).unlink()  # Only this test's isolated runtime configuration.
    elif change == 'bundle_changed':
        resolve_pattern_path(root, plan).write_text('{}', encoding='utf-8')
    elif change == 'withdrawn':
        settings, actor, targets = release_node[:3]
        execute(settings, actor, [request(targets[0], decision_graph(settings.pipeline_root), 'withdraw')])
    reader = resolve_fingerprint_paths if change in {'fingerprint_sha', 'unknown_case'} else resolve_pattern_path
    with pytest.raises((CompatibilityError, ContentPlanResolutionError)):
        reader(root, plan)


@pytest.mark.parametrize('script,synthetic', [('resolve_generation_content_plan_v1.py', None),
    ('resolve_generation_batch_v1.py', None), ('compatibility_creation_synthetic.py', 'plan'),
    ('compatibility_creation_synthetic.py', 'generate')])
def test_native_and_synthetic_cli_keep_typed_source_failure(tmp_path, script, synthetic):
    project = Path(__file__).resolve().parents[2]
    root = tmp_path / 'ops-pipeline'
    shutil.copytree(project / 'ops-pipeline/scripts', root / 'scripts', ignore=shutil.ignore_patterns('__pycache__'))
    write_once(root / 'data/production_plans/gen_missing/generation_source_plan_v1.json',
        {'profile_compatibility_v1_1': {'unconfigured': True}})
    python = project / 'ops-pipeline/.venv/Scripts/python.exe'
    command = [str(python), str(project / 'ops-pipeline/tests' / script), synthetic, str(root), 'gen_missing'] if synthetic else [str(python), str(root / 'scripts' / script), '--pipeline-root', str(root), '--request-id', 'gen_missing']
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 2
    assert json.loads(result.stdout)['code'] == 'PROFILE_COMPATIBILITY_BLOCKED'
    assert not list(root.glob('data/content_plans/*/*.json'))
    assert not list(root.glob('data/generation_batches/*/*.json'))


@pytest.mark.parametrize('code', ['PROFILE_COMPATIBILITY_BLOCKED', 'CONTENT_PLAN_LINEAGE_MISMATCH',
    'CONTENT_PLAN_PATTERN_AUTHORITY_AMBIGUITY', 'CONTENT_PLAN_CASE_AUTHORITY_MISSING'])
def test_source_failure_gateway_preserves_code_and_safe_next_step(settings, monkeypatch, code):
    from app.content_delivery_gateway import _run_pipeline_command
    from app.canonical_gateway import CanonicalOperationError
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess([], 2,
        stdout=json.dumps({'code': code, 'message': 'private/internal/path'}), stderr='private stderr'))
    with pytest.raises(CanonicalOperationError) as exc:
        _run_pipeline_command(settings, ['native'])
    assert exc.value.code == code
    assert 'private' not in str(exc.value)
    assert '原请求' in exc.value.next_action
