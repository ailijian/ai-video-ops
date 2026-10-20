"""Versioned graph and activation implementation for the original release Owner.

The live decision control is explicitly configured, never inferred from old
artifact provenance paths. An inaccessible/advanced control fences new writes.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import threading
import tarfile
import uuid
import copy
from contextlib import contextmanager
from pathlib import Path

from operation_lock_v1 import operation_lock
from human_review_operations_v1 import io_path
from profile_compatibility_contract_v1_1 import (
    ACTIVATION, CONTROL_LOCK, COVERAGE, READER, REGISTRY, RELEASE,
    CompatibilityError, safe_relative, validate_contract,
)
from profile_compatibility_decisions_v1_1 import (
    DOMAIN, bytes_for, decision_graph, digest, file_sha, read, ref,
    resolve_ref, validate_target, validate_targets, write_once, write_bytes_once, identity_path,
)

CONFIG = DOMAIN / 'runtime_config.json'
CONTROL = DOMAIN / 'control.json'
POINTER = DOMAIN / 'active.json'
_read_scope = threading.local()


def allowed_artifact(relative):
    safe_relative(relative)
    identity = r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}'
    patterns = [
        rf'data/cases/{identity}/(?:case_v1|approval_receipt)\.json',
        rf'data/fingerprints/{identity}/case_fingerprint_v1\.json',
        r'data/patterns/approved/[A-Za-z0-9_/-]+/(?:pattern_v1|approval_receipt)\.json',
        str(DOMAIN).replace('\\', '/') + r'/(?:'
        r'decisions/[a-f0-9]{32}\.json|'
        r'operations/[a-f0-9]{32}/(?:source_snapshot|preview)\.json|'
        r'definitions/[a-f0-9]{64}/(?:profile|rules)\.json|'
        r'evidence/[a-f0-9]{64}\.json|'
        r'sources/[a-f0-9]{64}/storyboard\.json|'
        r'registries/[a-f0-9]{64}/(?:registry|coverage)\.json)',
    ]
    return any(re.fullmatch(pattern, relative) for pattern in patterns)


@contextmanager
def control_read(control):
    """Share an already held fence only within the same synchronous OS thread."""
    key = str(Path(control).resolve())
    held = getattr(_read_scope, 'held', frozenset())
    if key in held:
        yield
        return
    with operation_lock(control, CONTROL_LOCK, shared=True):
        _read_scope.held = held | {key}
        try:
            yield
        finally:
            _read_scope.held = held


@contextmanager
def control_write(control):
    """Allow native read validation beneath this Owner's exclusive write lock.

    Never upgrade a shared read to a write and never transfer the scope to a
    child process. The operating-system lock remains the sole concurrency guard.
    """
    key=str(Path(control).resolve());held=getattr(_read_scope,'held',frozenset())
    if key in held:raise CompatibilityError('Cannot upgrade or nest a Compatibility write fence')
    with operation_lock(control,CONTROL_LOCK):
        _read_scope.held=held|{key}
        try:yield
        finally:_read_scope.held=held


def initialize_control(root):
    path = Path(root) / CONTROL
    with control_write(root):
        if not path.exists():
            write_once(path, {'schema_version': 'compatibility-control-v1.1', 'control_id': uuid.uuid4().hex})
        value = read(path)
        if set(value) != {'schema_version', 'control_id'} or value['schema_version'] != 'compatibility-control-v1.1':
            raise CompatibilityError('Unknown live Compatibility control')
        return value


def configure_runtime(root, control_root, *, purpose, contract_version='1.1',profiles=None):
    if purpose not in {'isolated-validation', 'production'}:
        raise CompatibilityError('Explicit runtime purpose required')
    control = initialize_control(control_root)
    if contract_version=='1.2':
        from profile_compatibility_contract_v1_2 import CONFIG as VERSION,READER,validate_contract as check
        config={'schema_version':VERSION,'purpose':purpose,'control_root':str(Path(control_root).resolve()),
            'control_id':control['control_id'],'reader_version':READER,'profiles':profiles or ['news']}
        write_once(Path(root)/CONFIG,check(config,VERSION))
        return config
    if contract_version!='1.1':raise CompatibilityError('Unknown runtime reader version')
    config = {'schema_version': 'compatibility-runtime-config-v1.1', 'purpose': purpose,
              'control_root': str(Path(control_root).resolve()), 'control_id': control['control_id']}
    write_once(Path(root) / CONFIG, config)
    return config


def _control(root):
    config = read(Path(root) / CONFIG)
    if config.get('schema_version')=='compatibility-runtime-config-v1.2':
        from profile_compatibility_contract_v1_2 import CONFIG as VERSION,validate_contract as check
        check(config,VERSION)
    elif (set(config) != {'schema_version', 'purpose', 'control_root', 'control_id'}
            or config['schema_version'] != 'compatibility-runtime-config-v1.1'
            or config['purpose'] not in {'production', 'isolated-validation'}):
        raise CompatibilityError('Unknown runtime Compatibility configuration')
    path = Path(config['control_root'])
    # Do not create or initialize a missing runtime control as a fallback.
    control = read(path / CONTROL)
    if control.get('control_id') != config['control_id'] or control.get('schema_version') != 'compatibility-control-v1.1':
        raise CompatibilityError('Live Compatibility control identity changed')
    return config, path


def bootstrap_registry(root, *, contract_version='1.1', validation_refs=None, eligibility_stage=None):
    if contract_version=='1.2':
        from profile_compatibility_release_v1_2 import bootstrap_registry as news_registry
        return news_registry(root,validation_refs=validation_refs,eligibility_stage=eligibility_stage)
    if contract_version!='1.1':raise CompatibilityError('Unknown Registry version')
    root = Path(root).resolve()
    with control_write(root):
        graph = decision_graph(root)
        effective = [value for value in graph['heads'].values() if value['effective']]
        for value in effective:
            validate_target(root, value['target'])
        definitions = {value['target']['profile_ref']['sha256'] for value in effective}
        if not effective or len(definitions) != 1:
            raise CompatibilityError('A single exact Mix Profile and valid native approvals are required')
        profile = read(resolve_ref(root, effective[0]['target']['profile_ref']))
        records = {}
        for value in effective:
            target = value['target']
            key = target['pattern_id']
            record = {'pattern_id': key, 'approved_pattern_sha256': target['pattern_ref']['sha256'],
                      'compatible_profiles': ['mix'], 'compatibility_status': 'human_approved_for_target_profile'}
            if key in records and records[key] != record:
                raise CompatibilityError('Conflicting Pattern versions in effective graph')
            records[key] = record
        approval_refs = sorted({r['path']: r for r in [v['effective'] for v in effective]}.values(), key=lambda v: v['path'])
        registry = {'schema_version': REGISTRY, 'reader_version': READER,
            'target_profiles': ['mix'], 'profiles': {'mix': {**profile, 'status': 'production_ready'}},
            'decision_head_sha256': graph['head_sha256'], 'approval_refs': approval_refs,
            'pattern_compatibility_records': list(records.values()), 'authority': {'derived_only': True}}
        directory = root / DOMAIN / 'registries' / graph['head_sha256']
        registry_path = directory / 'registry.json'
        write_once(registry_path, validate_contract(registry, REGISTRY))
        assessments = [read(resolve_ref(root, value['target']['audit_ref'])) for value in effective]
        coverage = {'schema_version': COVERAGE, 'source_registry_ref': ref(root, registry_path),
            'decision_head_sha256': graph['head_sha256'],
            'case_profile_compatibility_audit': {'assessments': assessments},
            'authority': {'can_change_compatibility': False}}
        coverage_path = directory / 'coverage.json'
        write_once(coverage_path, validate_contract(coverage, COVERAGE))
        return {'registry_ref': ref(root, registry_path), 'coverage_ref': ref(root, coverage_path), 'graph': graph}


def _selected_files(root, derived):
    selected = {derived['registry_ref']['path'], derived['coverage_ref']['path']}
    for path in (Path(root) / DOMAIN / 'decisions').glob('*.json'):
        receipt = read(path)
        selected.add(ref(root, path)['path'])
        for item in ('preview_ref', 'source_snapshot'):
            selected.add(receipt[item]['path'])
    # Preserve the entire immutable decision/preview history. Only live targets
    # contribute source bytes: superseded versions stay in their old releases,
    # rather than colliding at one canonical path in the next package.
    for head in derived['graph']['heads'].values():
        if head['effective']:
            target = head['target']
            for key, value in target.items():
                if key.endswith('_ref'):
                    resolve_ref(root, value)
                    selected.add(value['path'])
            pattern = read(resolve_ref(root, target['pattern_ref']))
            for case_id in pattern['scope']['supported_case_ids']:
                for path in (Path(root) / 'data/cases' / case_id / 'case_v1.json',
                             Path(root) / 'data/cases' / case_id / 'approval_receipt.json',
                             Path(root) / 'data/fingerprints' / case_id / 'case_fingerprint_v1.json'):
                    selected.add(ref(root, path)['path'])
    return selected


def validate_bundle(bundle, manifest):
    if manifest.get('schema_version')=='creative-authority-release-v1.2':
        from profile_compatibility_release_v1_2 import validate_bundle as news_bundle
        return news_bundle(bundle,manifest)
    from match_generation_sources_v1 import load_cases_and_fingerprints, load_patterns
    validate_contract(manifest, RELEASE)
    actual = {p.relative_to(io_path(bundle)).as_posix() for p in io_path(bundle).rglob('*') if p.is_file()}
    entries = [value['path'] for value in manifest['files']]
    if len(set(entries)) != len(entries) or actual != set(entries):
        raise CompatibilityError('Release bundle inventory changed')
    for value in manifest['files']:
        if not allowed_artifact(value['path']):
            raise CompatibilityError('Runtime/private/control data is forbidden in a structural release')
        resolve_ref(bundle, value)
    registry_path = resolve_ref(bundle, manifest['registry_ref'])
    coverage_path = resolve_ref(bundle, manifest['coverage_ref'])
    registry = validate_contract(read(registry_path), REGISTRY)
    coverage = validate_contract(read(coverage_path), COVERAGE)
    graph = decision_graph(bundle, expected_control_id=manifest['control_id'])
    if (graph['head_sha256'] != manifest['decision_head_sha256']
            or registry['decision_head_sha256'] != graph['head_sha256']
            or coverage['decision_head_sha256'] != graph['head_sha256']
            or coverage['source_registry_ref'] != manifest['registry_ref']
            or registry['approval_refs'] != manifest['approval_refs']):
        raise CompatibilityError('Release/Registry/Coverage decision graph mismatch')
    targets = [value['target'] for value in graph['heads'].values() if value['effective']]
    if not targets:
        raise CompatibilityError('Mix release has no effective Human compatibility approval')
    for target in targets:
        validate_target(bundle, target)
    approval_refs = {v['effective']['path']: v['effective'] for v in graph['heads'].values() if v['effective']}
    if sorted(approval_refs.values(), key=lambda v: v['path']) != manifest['approval_refs']:
        raise CompatibilityError('Registry cannot manufacture effective approvals')
    # Execute original structural Readers; do not replace formal validation.
    cases = {t['case_id']: resolve_ref(bundle, t['case_ref']) for t in targets}
    fps = {t['case_id']: resolve_ref(bundle, t['fingerprint_ref']) for t in targets}
    patterns = {t['pattern_id']: resolve_ref(bundle, t['pattern_ref']) for t in targets}
    load_cases_and_fingerprints(list(cases.values()), list(fps.values()))
    loaded = load_patterns(list(patterns.values()))
    for pattern in loaded:
        for case_id in pattern['artifact']['scope']['supported_case_ids']:
            case = Path(bundle) / 'data/cases' / case_id / 'case_v1.json'
            fp = Path(bundle) / 'data/fingerprints' / case_id / 'case_fingerprint_v1.json'
            receipt = case.with_name('approval_receipt.json')
            if not all(io_path(p).is_file() for p in (case, fp, receipt)):
                raise CompatibilityError('Pattern full support evidence missing from release')
            lineage = pattern['artifact'].get('lineage') or {}
            if (lineage.get('supporting_approved_case_sha256', {}).get(case_id) != file_sha(case)
                    or lineage.get('supporting_fingerprint_sha256', {}).get(case_id) != file_sha(fp)
                    or read(receipt).get('case_sha256_after_approval') != file_sha(case)
                    or read(receipt).get('human_gate') is not True):
                raise CompatibilityError('Pattern supporting approval SHA mismatch')
    expected_profile = read(resolve_ref(bundle, targets[0]['profile_ref']))
    if registry['profiles']['mix'] != {**expected_profile, 'status': 'production_ready'}:
        raise CompatibilityError('Derived Registry changed its declared Mix Profile')
    return {'graph': graph, 'registry': registry, 'coverage': coverage,
            'approved_cases': len(cases), 'approved_patterns': len(patterns)}


def source_blobs(repo_root, commit):
    """Read only committed machine sources; no runtime artifacts enter this map."""
    names = subprocess.check_output(['git', '-C', str(repo_root), 'ls-tree', '-r', '--name-only', commit, '--',
        'ops-pipeline/scripts', 'internal-console/app', 'internal-console/scripts', 'internal-console/migrations', 'deploy/creative-authority'], text=True).splitlines()
    names = sorted(n for n in names if n.endswith(('.py', '.sql')) and '/tests/' not in n)
    if not names:
        raise CompatibilityError('Release source machine owners are unavailable')
    archive = subprocess.check_output(['git', '-C', str(repo_root), 'archive', '--format=tar', commit, '--', *names])
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:') as source:
        return {name: source.extractfile(name).read() for name in names}


def build_release(root, release_parent, repo_root, *, purpose, parent_release=None,
                  contract_version='1.1',validation_refs=None,eligibility_stage=None):
    root, repo_root = Path(root).resolve(), Path(repo_root).resolve()
    control = initialize_control(root)
    # A new implementation must not be attributed to the old Checkpoint commit.
    status = subprocess.check_output(['git', '-C', str(repo_root), 'status', '--porcelain=v1', '--untracked-files=all'], text=True)
    if status.strip():
        raise CompatibilityError('Release requires a clean, accurately committed source tree')
    commit = subprocess.check_output(['git', '-C', str(repo_root), 'rev-parse', 'HEAD'], text=True).strip()
    sources = []
    for path, blob in source_blobs(repo_root, commit).items():
        actual = (repo_root / path).read_bytes()
        if blob.replace(b'\r\n', b'\n') != actual.replace(b'\r\n', b'\n'):
            raise CompatibilityError('Release source does not match its declared commit')
        sources.append({'path': path, 'git_blob_sha256': hashlib.sha256(blob).hexdigest(),
                        'checkout_sha256': hashlib.sha256(actual).hexdigest()})
    if contract_version=='1.2':
        import profile_compatibility_contract_v1_2 as contract
        from profile_compatibility_release_v1_2 import selected_files as select_news,allowed_artifact as allow_news
        if purpose!='isolated-validation':raise CompatibilityError('News v1.2 is isolated-only')
        from profile_compatibility_release_v1_2 import validate_machine_sources
        validate_machine_sources(repo_root,commit)
    elif contract_version=='1.1':
        import profile_compatibility_contract_v1_1 as contract
        select_news,allow_news=None,None
    else:raise CompatibilityError('Unknown release contract')
    derived = bootstrap_registry(root,contract_version=contract_version,validation_refs=validation_refs,eligibility_stage=eligibility_stage)
    with control_write(root):
        if decision_graph(root)['head_sha256'] != derived['graph']['head_sha256']:
            raise CompatibilityError('Decision graph advanced while preparing release')
        release_id = uuid.uuid4().hex
        directory = Path(release_parent).resolve() / 'releases' / release_id
        directory.mkdir(parents=True, exist_ok=False)
        bundle = directory / 'bundle'
        selected = select_news(root,derived) if select_news else _selected_files(root, derived)
        files = []
        for relative in sorted(selected):
            safe_relative(relative)
            if not (allow_news(relative) if allow_news else allowed_artifact(relative)) or Path(root / relative).is_symlink():
                raise CompatibilityError('Non-structural data cannot enter Compatibility release')
            destination = bundle / relative
            io_path(destination.parent).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(io_path(root / relative), io_path(destination))
            files.append(ref(bundle, destination))
        manifest = {'schema_version': contract.RELEASE, 'release_id': release_id, 'purpose': purpose,
            'profiles': derived.get('profiles',['mix']), 'reader_version': contract.READER, 'source_repo_commit': commit,
            'source_files': sources, 'files': files, 'control_id': control['control_id'],
            'decision_head_sha256': derived['graph']['head_sha256'],
            'registry_ref': derived['registry_ref'], 'coverage_ref': derived['coverage_ref'],
            'approval_refs': read(root / derived['registry_ref']['path'])['approval_refs'],
            'parent_release': parent_release}
        if contract_version=='1.2':manifest['eligibility']=derived['eligibility']
        validate_bundle(bundle, manifest)
        write_once(directory / 'manifest.json', manifest)
        verify_release(directory, repo_root)
        return directory


def verify_release(directory, repo_root):
    directory = Path(directory).resolve()
    raw=read(directory/'manifest.json')
    from profile_compatibility_decisions_v1_1 import contract_for_version
    contract=contract_for_version(raw.get('schema_version'))
    manifest = contract.validate_contract(raw, contract.RELEASE)
    if contract.RELEASE.endswith('v1.2'):
        from profile_compatibility_release_v1_2 import validate_machine_sources
        validate_machine_sources(repo_root,manifest['source_repo_commit'])
    if directory.name != manifest['release_id']:
        raise CompatibilityError('Release identity/path mismatch')
    actual = {p.relative_to(io_path(directory / 'bundle')).as_posix() for p in io_path(directory / 'bundle').rglob('*') if p.is_file()}
    expected = [value['path'] for value in manifest['files']]
    if len(set(expected)) != len(expected) or set(expected) != actual:
        raise CompatibilityError('Release inventory mismatch')
    for value in manifest['files']:
        resolve_ref(directory / 'bundle', value)
    blobs = source_blobs(repo_root, manifest['source_repo_commit'])
    source_names = [value['path'] for value in manifest['source_files']]
    if len(set(source_names)) != len(source_names) or set(source_names) != set(blobs):
        raise CompatibilityError('Release machine source inventory mismatch')
    for value in manifest['source_files']:
        safe_relative(value['path'])
        blob = blobs[value['path']]
        if hashlib.sha256(blob).hexdigest() != value['git_blob_sha256']:
            raise CompatibilityError('Release source Git Blob mismatch')
    return validate_bundle(directory / 'bundle', manifest)


def stage_release(directory, runtime_root, repo_root):
    directory, root = Path(directory).resolve(), Path(runtime_root).resolve()
    manifest = read(directory / 'manifest.json')
    config, control = _control(root)
    expected='creative-authority-release-v1.2' if config['schema_version'].endswith('v1.2') else RELEASE
    if manifest.get('schema_version')!=expected:raise CompatibilityError('Runtime/Release reader version mismatch')
    if 'profiles' in config and config['profiles']!=manifest['profiles']:
        raise CompatibilityError('Runtime/Release declared profiles mismatch')
    if manifest.get('purpose') != config['purpose'] or manifest.get('control_id') != config['control_id']:
        raise CompatibilityError('Validation release cannot enter production or a different control Authority')
    verify_release(directory, repo_root)
    with control_write(control):
        if decision_graph(control)['head_sha256'] != manifest['decision_head_sha256']:
            raise CompatibilityError('Release is stale; stage refuses old permissions')
        destination = root / DOMAIN / 'staged' / manifest['release_id']
        for path in io_path(directory).rglob('*'):
            if not path.is_file():
                continue
            relative = path.relative_to(io_path(directory))
            target = destination / relative
            write_bytes_once(target, path.read_bytes(), temporary_directory=root / DOMAIN / 'transfer_tmp')
        verify_release(destination, repo_root)
        return ref(root, destination / 'manifest.json')


def activate(runtime_root, repo_root, release_ref, operation_id):
    from profile_compatibility_contract_v1_1 import OPERATION, validate
    validate(operation_id, OPERATION)
    root = Path(runtime_root).resolve()
    config, control = _control(root)
    from profile_compatibility_decisions_v1_1 import contract_for_version
    contract=contract_for_version('creative-authority-release-v1.2' if config['schema_version'].endswith('v1.2') else RELEASE)
    with control_write(control):
        manifest_path = resolve_ref(root, release_ref)
        manifest = read(manifest_path)
        contract.validate_contract(manifest,contract.RELEASE)
        verify_release(manifest_path.parent, repo_root)
        if manifest['purpose'] != config['purpose'] or manifest['control_id'] != config['control_id']:
            raise CompatibilityError('Activation purpose/control mismatch')
        if 'profiles' in config and config['profiles']!=manifest['profiles']:
            raise CompatibilityError('Activation declared profiles mismatch')
        if decision_graph(control)['head_sha256'] != manifest['decision_head_sha256']:
            raise CompatibilityError('Cannot activate a stale or withdrawn decision graph')
        pointer_path = root / POINTER
        parent = read(pointer_path).get('activation_ref') if pointer_path.exists() else None
        receipt_path = root / DOMAIN / 'activations' / f'{operation_id}.json'
        if receipt_path.exists():
            receipt = contract.validate_contract(read(receipt_path), contract.ACTIVATION)
            if receipt['release_ref'] != release_ref or (parent not in (ref(root, receipt_path), receipt['parent_activation'])):
                raise CompatibilityError('Activation operation replay conflicts or was superseded')
        else:
            if parent:
                old = contract.validate_contract(read(resolve_ref(root, parent)), contract.ACTIVATION)
                if not manifest['parent_release'] or manifest['parent_release']['sha256'] != old['release_ref']['sha256']:
                    raise CompatibilityError('Activation must name its exact parent release')
            elif manifest['parent_release'] is not None:
                raise CompatibilityError('Initial activation cannot skip parent release')
            receipt = {'schema_version': contract.ACTIVATION, 'operation_id': operation_id,
                'release_ref': release_ref, 'parent_activation': parent,
                'decision_head_sha256': manifest['decision_head_sha256'],
                'control_id': config['control_id'], 'purpose': config['purpose']}
            if manifest['schema_version'].endswith('v1.2'):receipt['eligibility']=manifest['eligibility']
            write_once(receipt_path, contract.validate_contract(receipt, contract.ACTIVATION))
        pointer = {'activation_ref': ref(root, receipt_path)}
        temporary = pointer_path.with_suffix(f'.{operation_id}.tmp')
        with temporary.open('wb') as handle:
            handle.write(bytes_for(pointer))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, pointer_path)
        return {'activation_ref': ref(root, receipt_path), 'receipt': receipt}


def effective_runtime(runtime_root, *, pinned=None):
    root = Path(runtime_root).resolve()
    config, control = _control(root)
    from profile_compatibility_decisions_v1_1 import contract_for_version
    contract=contract_for_version('creative-authority-release-v1.2' if config['schema_version'].endswith('v1.2') else RELEASE)
    with control_read(control):
        # Only the isolated News reader has retained Native qualification.
        # Reuse is derived and process-local. Every access re-hashes all input
        # bytes/inventories under the original control fence; no TTL or mtime
        # grants permission. Two full passes establish a stable before/after
        # fingerprint before any result becomes reusable.
        checks=getattr(_read_scope,'news_checks',{})
        cache_key=str(root)
        previous=checks.get(cache_key)
        before=None
        news=contract.RELEASE.endswith('v1.2') and config['purpose']=='isolated-validation'
        if news and previous:
            from profile_compatibility_release_v1_2 import validation_fingerprint,validate_binding
            before=validation_fingerprint(previous['roots'])
            if before and before==previous['fingerprint'] and previous.get('active') is not None:
                active=copy.deepcopy(previous['active'])
                if pinned is not None:validate_binding(active,pinned)
                return active
            checks.pop(cache_key,None)
        pointer = read(root / POINTER)
        if set(pointer) != {'activation_ref'}:
            raise CompatibilityError('Invalid activation pointer')
        activation = contract.validate_contract(read(resolve_ref(root, pointer['activation_ref'])), contract.ACTIVATION)
        all_activations = {}
        parents = set()
        child_counts = {}
        for path in (root / DOMAIN / 'activations').glob('*.json'):
            item = contract.validate_contract(read(path), contract.ACTIVATION)
            item_ref = ref(root, path)
            all_activations[item_ref['sha256']] = item_ref
            parent = item['parent_activation']
            key = parent['sha256'] if parent else None
            child_counts[key] = child_counts.get(key, 0) + 1
            if parent:
                resolve_ref(root, parent)
                parents.add(parent['sha256'])
        heads = set(all_activations) - parents
        if heads != {pointer['activation_ref']['sha256']} or any(n != 1 for n in child_counts.values()):
            raise CompatibilityError('Activation is incomplete, forked or rolled back; resume its exact operation')
        # Walk append-only activation parents to reject missing history/cycles.
        seen, current = set(), pointer['activation_ref']
        while current:
            if current['sha256'] in seen:
                raise CompatibilityError('Activation lineage cycle')
            seen.add(current['sha256'])
            ancestor = contract.validate_contract(read(resolve_ref(root, current)), contract.ACTIVATION)
            current = ancestor['parent_activation']
        manifest_path = resolve_ref(root, activation['release_ref'])
        manifest = contract.validate_contract(read(manifest_path), contract.RELEASE)
        if 'profiles' in config and config['profiles']!=manifest['profiles']:
            raise CompatibilityError('Runtime declared profiles differ from the active Release')
        graph = decision_graph(control)
        if (manifest['purpose'] != config['purpose'] or activation['purpose'] != config['purpose']
                or activation['control_id'] != config['control_id'] or manifest['control_id'] != config['control_id']
                or activation['decision_head_sha256'] != graph['head_sha256']
                or manifest['decision_head_sha256'] != graph['head_sha256']):
            raise CompatibilityError('兼容性决定已更新或撤回，请先发布并激活当前版本。')
        result = validate_bundle(manifest_path.parent / 'bundle', manifest)
        # Compare live sources as well as immutable staged snapshot.
        validate_targets(control, [value['target'] for value in graph['heads'].values() if value['effective']])
        binding = {'activation_ref': pointer['activation_ref'], 'release_ref': activation['release_ref'],
                   'decision_head_sha256': graph['head_sha256'], 'control_id': config['control_id'],
                   'approval_refs': manifest['approval_refs']}
        active={**result, 'binding': binding, 'bundle_root': manifest_path.parent / 'bundle',
                'manifest': manifest, 'registry_path': resolve_ref(manifest_path.parent / 'bundle', manifest['registry_ref']),
                'coverage_path': resolve_ref(manifest_path.parent / 'bundle', manifest['coverage_ref'])}
        if contract.RELEASE.endswith('v1.2'):
            from profile_compatibility_release_v1_2 import validate_binding
            if activation['eligibility']!=manifest['eligibility']:raise CompatibilityError('Activation eligibility differs from Release')
            if pinned is not None:validate_binding(active,pinned)
        elif pinned is not None and pinned != binding:
            raise CompatibilityError('Open Request uses a different Compatibility activation; cannot continue writes')
        if news:
            from profile_compatibility_release_v1_2 import validation_roots,validation_fingerprint
            roots=validation_roots(root,control,active)
            after=validation_fingerprint(roots)
            stable=bool(previous and before and before==after and roots==previous['roots'])
            if len(checks)>=4:checks.pop(next(iter(checks)))
            checks[cache_key]={'roots':roots,'fingerprint':after,
                'active':copy.deepcopy(active) if stable else None}
            _read_scope.news_checks=checks
        return active


@contextmanager
def runtime_write(root, *, pinned=None):
    _, control = _control(root)
    with control_read(control):
        yield effective_runtime(root, pinned=pinned)


def find_runtime_root(path):
    path = Path(path).resolve()
    for parent in (path, *path.parents):
        if (parent / CONFIG).is_file():
            return parent
    raise CompatibilityError('Compatibility v1.1 has not been explicitly staged and activated')


def active_approval_projection(path):
    """Internal read model, never persisted or accepted as Human approval."""
    runtime = effective_runtime(find_runtime_root(path))
    bundle = runtime['bundle_root']
    cases, pattern_approval = [], None
    for value in runtime['graph']['heads'].values():
        if not value['effective'] or value['target']['target_profile']!='mix':
            continue
        target = value['target']
        cases.append({'case_id': target['case_id'], 'status': 'approved',
            'approved_compatible_generation_profiles': ['mix'],
            'source_approved_case_ref': target['case_ref'], 'fingerprint_ref': target['fingerprint_ref'],
            'native_receipt_ref': value['effective']})
        record = {'pattern_id': target['pattern_id'], 'compatible_profiles': ['mix'],
                  'approved_pattern_sha256': target['pattern_ref']['sha256']}
        if pattern_approval is not None and record != pattern_approval:
            raise CompatibilityError('Initial Mix reader supports a single declared narrow Pattern')
        pattern_approval = record
    approval_refs = runtime['binding']['approval_refs']
    single_receipt_sha = approval_refs[0]['sha256'] if len(approval_refs) == 1 else None
    return {'schema_version': 'compatibility-effective-read-model-v1.1',
            'derived_only': True, 'case_profile_compatibility_approvals': cases,
            'pattern_profile_compatibility_approval': pattern_approval,
            'runtime_binding': runtime['binding']}, single_receipt_sha
