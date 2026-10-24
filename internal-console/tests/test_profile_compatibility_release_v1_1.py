"""Real v1.1 pack/verify/stage/activate using an isolated committed source snapshot."""
import importlib.util
import json
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from test_profile_compatibility_v1_1 import compat, execute, grant, request
from profile_compatibility_contract_v1_1 import CompatibilityError
from profile_compatibility_decisions_v1_1 import DOMAIN, decision_graph, file_sha, read, write_once
from profile_compatibility_release_v1_1 import (
    CONFIG, POINTER, configure_runtime, effective_runtime, initialize_control,
)


@pytest.fixture
def release_node(compat, tmp_path):
    _, settings, _, actor, targets = compat
    grant(settings)
    result = execute(settings, actor, [request(t) for t in targets])
    repo, owner = committed_source_snapshot(settings.repo_root, tmp_path / 'source')
    runtime = tmp_path / 'runtime'
    configure_runtime(runtime, settings.pipeline_root, purpose='isolated-validation')
    return settings, actor, targets, result, repo, owner, runtime, tmp_path / 'packages'


def committed_source_snapshot(source_root, repo, *, complete=False):
    paths = ['ops-pipeline/scripts/' + name for name in (
        'production_profile_v1.py', 'profile_compatibility_contract_v1_1.py',
        'profile_compatibility_decisions_v1_1.py', 'profile_compatibility_authorization_v1.py',
        'profile_compatibility_release_v1_1.py', 'match_generation_sources_v1.py')]
    paths += ['deploy/creative-authority/authority_release.py']
    if complete:
        paths=sorted(str(p.relative_to(source_root)).replace('\\','/')
            for directory in ('ops-pipeline/scripts','internal-console/app','internal-console/scripts',
                              'internal-console/migrations','deploy/creative-authority')
            for p in (source_root/directory).rglob('*')
            if p.is_file() and (p.suffix in {'.py','.sql'} or p.name in {
                'creative_style_rules_v1.json','creative_style_contracts_v1.json',
                'creation_batch_contracts_v1.json','creation_batch_policy_v1.json','creation_batch_policy_v2.json'}) and 'tests' not in p.parts)
    for relative in paths:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_root / relative, path)
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.DEVNULL, text=True)
    git('init', '-b', 'isolated-source-test')
    # Runtime imports may populate bytecode after the first formal pack.
    # Match the real repository's cache policy without ignoring source/data.
    (repo / '.git/info/exclude').write_text('__pycache__/\n*.pyc\n', encoding='utf-8')
    git('config', 'user.name', 'Isolated source fixture')
    git('config', 'user.email', 'isolated-source@example.invalid')
    git('config', 'core.autocrlf', 'false')
    git('add', '--', *paths)
    git('commit', '-m', 'test: exact isolated source snapshot')
    spec = importlib.util.spec_from_file_location('compat_release_test_owner', source_root / 'deploy/creative-authority/authority_release.py')
    owner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(owner)
    return repo, owner


def pack(node, parent=None):
    settings, _, _, _, repo, owner, _, output = node
    return owner.build_release(settings.pipeline_root, output, repo, contract_version='1.1',
                               purpose='isolated-validation', parent_release=parent)


def activate(node, release):
    _, _, _, _, repo, owner, runtime, _ = node
    reference = owner.stage_release_v1_1(release, runtime, repo)
    return owner.activate_release_v1_1(runtime, repo, reference, uuid.uuid4().hex)


def test_native_pack_verify_preflight_and_no_local_approval_runtime_bypass(release_node):
    node = release_node
    settings, _, _, receipt, repo, owner, runtime, _ = node
    from match_generation_sources_v1 import load_profile_registry, load_profile_compatibility_approval
    with pytest.raises(CompatibilityError):
        effective_runtime(runtime)
    package = pack(node)
    checked = owner.verify_release(package, repo)
    assert checked['approved_cases'] == 3 and checked['approved_patterns'] == 1
    registry = package / 'bundle' / read(package / 'manifest.json')['registry_ref']['path']
    with pytest.raises(CompatibilityError):
        load_profile_registry(registry)
    activate(node, package)
    current = owner.preflight(runtime, repo)
    assert current['binding']['approval_refs'] == [receipt['receipt_ref']]
    assert current['registry']['target_profiles'] == ['mix']
    loaded, registry_sha = load_profile_registry(current['registry_path'])
    projection, _ = load_profile_compatibility_approval(current['registry_path'], registry_sha, 'irrelevant-read-model-input')
    assert len(projection['case_profile_compatibility_approvals']) == 3
    assert projection['derived_only'] is True
    # Publication/activation did not change native decision bytes.
    assert file_sha(settings.pipeline_root / receipt['receipt_ref']['path']) == receipt['receipt_ref']['sha256']


def test_withdraw_fences_active_old_release_and_open_writes(release_node):
    node = release_node
    settings, actor, targets, _, repo, owner, runtime, _ = node
    package = pack(node)
    active = activate(node, package)
    pinned = effective_runtime(runtime)['binding']
    plan_path = runtime / 'data/production_plans/open_request/generation_source_plan_v1.json'
    write_once(plan_path, {'request_id': 'open_request', 'profile_compatibility_v1_1': pinned})
    from profile_compatibility_consumers_v1_1 import guarded
    wrote = []
    @guarded
    def review_generation_batch_v2(*, pipeline_root, request_id):
        wrote.append(request_id)
    review_generation_batch_v2(pipeline_root=runtime, request_id='open_request')
    assert wrote == ['open_request']
    execute(settings, actor, [request(targets[0], decision_graph(settings.pipeline_root), 'withdraw')])
    for action in (lambda: owner.preflight(runtime, repo),
                   lambda: owner.stage_release_v1_1(package, runtime, repo),
                   lambda: review_generation_batch_v2(pipeline_root=runtime, request_id='open_request')):
        with pytest.raises(CompatibilityError):
            action()
    assert wrote == ['open_request']
    updated = pack(node, active['receipt']['release_ref'])
    activate(node, updated)
    assert len([v for v in owner.preflight(runtime, repo)['graph']['heads'].values() if v['effective']]) == 2
    with pytest.raises(CompatibilityError):
        review_generation_batch_v2(pipeline_root=runtime, request_id='open_request')


def test_validation_package_cannot_stage_to_production_purpose(release_node):
    settings, _, _, _, repo, owner, runtime, _ = release_node
    package = pack(release_node)
    production_named_fixture = runtime.parent / 'production-purpose-fixture'
    configure_runtime(production_named_fixture, settings.pipeline_root, purpose='production')
    with pytest.raises(CompatibilityError, match='production'):
        owner.stage_release_v1_1(package, production_named_fixture, repo)
    assert not (production_named_fixture / DOMAIN / 'staged').exists()


def test_withdrawn_target_sources_do_not_become_new_release_prerequisites(release_node):
    settings, actor, targets, _, repo, owner, runtime, _ = release_node
    previous = pack(release_node)
    original = (previous / 'manifest.json').read_bytes()
    active = activate(release_node, previous)
    execute(settings, actor, [request(targets[0], decision_graph(settings.pipeline_root), 'withdraw')])
    # Corrupt only obsolete derived evidence in this isolated fixture. Native
    # Case/Pattern evidence remains valid for the other two effective targets.
    path = settings.pipeline_root / targets[0]['audit_ref']['path']
    path.write_bytes(path.read_bytes() + b' ')
    next_package = pack(release_node, active['receipt']['release_ref'])
    manifest = read(next_package / 'manifest.json')
    assert targets[0]['audit_ref']['path'] not in {v['path'] for v in manifest['files']}
    assert owner.verify_release(next_package, repo)['approved_cases'] == 2
    assert (previous / 'manifest.json').read_bytes() == original


def test_partial_activation_resumes_exact_operation_and_pointer_rollback_blocked(release_node, monkeypatch):
    node = release_node
    _, _, _, _, repo, owner, runtime, _ = node
    package = pack(node)
    reference = owner.stage_release_v1_1(package, runtime, repo)
    operation = uuid.uuid4().hex
    import profile_compatibility_release_v1_1 as native
    replace = native.os.replace
    def fail_pointer(*args):
        raise OSError('isolated pointer fault')
    with monkeypatch.context() as fault:
        fault.setattr(native.os, 'replace', fail_pointer)
        with pytest.raises(OSError):
            owner.activate_release_v1_1(runtime, repo, reference, operation)
    assert len(list((runtime / DOMAIN / 'activations').glob('*.json'))) == 1
    resumed = owner.activate_release_v1_1(runtime, repo, reference, operation)
    assert owner.preflight(runtime, repo)['binding']['activation_ref'] == resumed['activation_ref']
    old_pointer = (runtime / POINTER).read_bytes()
    package2 = pack(node, reference)
    activate(node, package2)
    (runtime / POINTER).write_bytes(old_pointer)
    with pytest.raises(CompatibilityError, match='rolled back'):
        owner.preflight(runtime, repo)


def test_unknown_schema_or_missing_companion_and_source_dirty_refused(release_node):
    node = release_node
    _, _, _, _, repo, owner, runtime, _ = node
    package = pack(node)
    manifest_path = package / 'manifest.json'
    original = manifest_path.read_bytes()
    manifest = read(manifest_path)
    manifest['reader_version'] = 'unknown-reader-v999'
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(CompatibilityError):
        owner.verify_release(package, repo)
    manifest_path.write_bytes(original)
    first = read(manifest_path)['approval_refs'][0]
    (package / 'bundle' / first['path']).unlink()
    with pytest.raises(CompatibilityError):
        owner.verify_release(package, repo)
    (repo / 'uncommitted.txt').write_text('uncommitted source', encoding='utf-8')
    with pytest.raises(CompatibilityError, match='committed'):
        pack(node)


@pytest.mark.parametrize('operation', ['source', 'plan', 'generate', 'review', 'export', 'closure'])
def test_real_native_cli_writers_are_fenced_after_withdraw(release_node, operation):
    settings, actor, targets, _, repo, owner, runtime, _ = release_node
    package = pack(release_node)
    activate(release_node, package)
    pinned = effective_runtime(runtime)['binding']
    request_id = 'open_request'
    plan = runtime / 'data/production_plans' / request_id / 'generation_source_plan_v1.json'
    write_once(plan, {'request_id': request_id, 'profile_compatibility_v1_1': pinned})
    batch = runtime / 'data/generation_batches' / request_id / 'generation_batch_v1.json'
    write_once(batch, {'request_id': request_id, 'lineage': {'source_plan': {'path': str(plan)}}})
    review = runtime / 'review-input.json'
    write_once(review, {'items': []})
    execute(settings, actor, [request(targets[0], decision_graph(settings.pipeline_root), 'withdraw')])
    project = Path(__file__).resolve().parents[2]
    scripts = project / 'ops-pipeline/scripts'
    arguments = {
        'source': ['resolve_generation_source_plan_v1.py', '--pipeline-root', str(runtime), '--request-id', request_id],
        'plan': ['resolve_generation_content_plan_v1.py', '--pipeline-root', str(runtime), '--request-id', request_id],
        'generate': ['resolve_generation_batch_v1.py', '--pipeline-root', str(runtime), '--request-id', request_id],
        'review': ['review_generation_batch_v2.py', '--batch', str(batch), '--review-file', str(review)],
        'export': ['export_mix_excel_v1.py', '--batch', str(batch), '--template', str(settings.pipeline_root / 'mix-template.xlsx'), '--output', str(runtime / 'blocked.xlsx')],
        'closure': ['close_generation_export_v1.py', '--pipeline-root', str(runtime), '--request-id', request_id, '--excel', str(runtime / 'blocked.xlsx')],
    }[operation]
    import subprocess
    result = subprocess.run([str(project / 'ops-pipeline/.venv/Scripts/python.exe'), '-X', 'utf8', str(scripts / arguments[0]), *arguments[1:]],
        capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode != 0
    assert 'CompatibilityError' in result.stderr or '兼容性决定已更新或撤回' in result.stdout, result.stdout + result.stderr
    assert not (runtime / 'blocked.xlsx').exists()
    assert not list(runtime.glob('data/content_ledgers/*.json'))


def test_copied_native_source_plan_cannot_downgrade_to_unconfigured_runtime(release_node):
    _, _, _, _, _, _, runtime, _ = release_node
    foreign = runtime.parent / 'unconfigured-runtime'
    plan = foreign / 'data/production_plans/copied/generation_source_plan_v1.json'
    write_once(plan, {'request_id': 'copied', 'profile_compatibility_v1_1': {'control_id': 'native'}})
    from profile_compatibility_consumers_v1_1 import guarded
    @guarded
    def resolve_generation_content_plan(*, pipeline_root, request_id):
        raise AssertionError('Copied native plan reached a legacy writer')
    with pytest.raises(CompatibilityError, match='legacy runtime'):
        resolve_generation_content_plan(pipeline_root=foreign, request_id='copied')


@pytest.mark.parametrize('private_path', [
    'data/personas/private.json', str(DOMAIN / 'control.json').replace('\\', '/'),
    str(CONFIG).replace('\\', '/'), 'console.sqlite3',
])
def test_release_verifier_rejects_private_or_control_files_even_with_matching_inventory(release_node, private_path):
    from profile_compatibility_decisions_v1_1 import ref
    _, _, _, _, repo, owner, _, _ = release_node
    package = pack(release_node)
    path = package / 'bundle' / private_path
    write_once(path, {'isolated_probe': True})
    manifest = read(package / 'manifest.json')
    manifest['files'].append(ref(package / 'bundle', path))
    (package / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(CompatibilityError, match='forbidden'):
        owner.verify_release(package, repo)
