"""Native append-only implementation delegated by Production Profile Authority."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from case_console_authorization_v1 import digest
from human_review_operations_v1 import io_path
from operation_lock_v1 import operation_lock
from profile_compatibility_authorization_v1 import authorization, validate_grant_proof
from profile_compatibility_contract_v1_1 import (
    APPROVAL, CONTROL_LOCK, ID, OPERATION, PREVIEW, RULES, SNAPSHOT, TARGET,
    CompatibilityError, safe_relative, validate, validate_contract,
)

DOMAIN = Path('data/production_profiles/compatibility_v1_1')


def contract_for_version(version):
    import profile_compatibility_contract_v1_1 as old
    if version in old.SCHEMAS:return old
    import profile_compatibility_contract_v1_2 as news
    if version in news.SCHEMAS:return news
    raise CompatibilityError('Unknown Compatibility contract; no legacy downgrade')


def contract_for_targets(decisions):
    if not isinstance(decisions,list) or not decisions:
        raise CompatibilityError('Explicit independent target decisions required')
    profiles={d.get('target',{}).get('target_profile') for d in decisions if isinstance(d,dict)}
    if profiles=={'news'}:
        import profile_compatibility_contract_v1_2 as contract
    elif profiles=={'mix'}:
        import profile_compatibility_contract_v1_1 as contract
    else:raise CompatibilityError('One explicit profile permission domain per Human operation required')
    return contract


def identity_path(path):
    value = str(path)
    if value.startswith('\\\\?\\UNC\\'):
        value = '\\\\' + value[8:]
    elif value.startswith('\\\\?\\'):
        value = value[4:]
    return Path(value).resolve()


def read(path):
    try:
        value = json.loads(io_path(path).read_text('utf-8'))
        if not isinstance(value, dict):
            raise ValueError('Expected object')
        return value
    except (OSError, ValueError) as exc:
        raise CompatibilityError(f'Compatibility artifact unavailable: {Path(path).name}') from exc


def file_sha(path):
    return hashlib.sha256(io_path(path).read_bytes()).hexdigest()


def bytes_for(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def write_once(path, value):
    return write_bytes_once(path, bytes_for(value))


def write_bytes_once(path, data, *, temporary_directory=None):
    path = Path(path)
    io_path(path.parent).mkdir(parents=True, exist_ok=True)
    temporary_directory = Path(temporary_directory) if temporary_directory else path.parent
    io_path(temporary_directory).mkdir(parents=True, exist_ok=True)
    staged = None
    try:
        with tempfile.NamedTemporaryFile(dir=io_path(temporary_directory), prefix='.compat-', suffix='.tmp', delete=False) as handle:
            staged = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(staged, io_path(path))  # Exclusive atomic publication, never replace history.
        except FileExistsError:
            if io_path(path).read_bytes() != data:
                raise CompatibilityError('Immutable Compatibility operation conflicts with existing bytes')
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
    return file_sha(path)


def ref(root, path):
    root, path = identity_path(root), identity_path(path)
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise CompatibilityError('Artifact outside configured Authority root') from exc
    safe_relative(relative)
    return {'path': relative, 'sha256': file_sha(path)}


def resolve_ref(root, reference):
    from profile_compatibility_contract_v1_1 import REF
    validate(reference, REF)
    safe_relative(reference['path'])
    root = Path(root).resolve()
    path = (root / reference['path']).resolve()
    physical = io_path(path, resolved=True)
    if not path.is_relative_to(root) or not physical.is_file() or physical.is_symlink() or hashlib.sha256(physical.read_bytes()).hexdigest() != reference['sha256']:
        raise CompatibilityError('Compatibility source version changed or is missing')
    return path


def validate_targets(root, targets):
    """One graph batch: shared News Pattern, independent exact Case checks."""
    from profile_compatibility_news_v1_2 import validate_targets as validate_news_targets
    news = [target for target in targets if target.get('target_profile') == 'news']
    if news:
        validate_news_targets(root, news)
    for target in targets:
        if target.get('target_profile') != 'news':
            validate_target(root, target)
    return targets


def target_id(target):
    contract=contract_for_targets([{'target':target}])
    validate(target, contract.TARGET)
    return digest(target)


def validate_target(root, target):
    """Native audit and independent Pattern scope; no derived Registry inputs."""
    if target.get('target_profile')=='news':
        from profile_compatibility_news_v1_2 import validate_target as validate_news_target
        return validate_news_target(root,target)
    from production_profile_v1 import audit_case_profile_compatibility_v1, declared_mix_profile_v1_1
    validate(target, TARGET)
    for field, expected in {
        'case_ref': f"data/cases/{target['case_id']}/case_v1.json",
        'case_approval_ref': f"data/cases/{target['case_id']}/approval_receipt.json",
        'fingerprint_ref': f"data/fingerprints/{target['case_id']}/case_fingerprint_v1.json",
    }.items():
        if target[field]['path'] != expected:
            raise CompatibilityError('Historical/copied source cannot replace the current canonical Case version')
    pattern_path = target['pattern_ref']['path']
    if (not pattern_path.startswith('data/patterns/approved/') or not pattern_path.endswith('/pattern_v1.json')
            or target['pattern_approval_ref']['path'] != pattern_path.rsplit('/', 1)[0] + '/approval_receipt.json'):
        raise CompatibilityError('Pattern must retain its original approval Owner/domain')
    paths = {name: resolve_ref(root, value) for name, value in target.items() if name.endswith('_ref')}
    pattern, receipt = read(paths['pattern_ref']), read(paths['pattern_approval_ref'])
    if (pattern.get('status') != 'approved' or pattern.get('pattern_id') != target['pattern_id']
            or pattern.get('effectiveness', {}).get('status') != 'unvalidated'
            or target['case_id'] not in (pattern.get('scope') or {}).get('supported_case_ids', [])
            or receipt.get('schema_version') != 'pattern-approval-receipt-v1.0'
            or receipt.get('human_gate') is not True or receipt.get('pattern_id') != target['pattern_id']
            or (receipt.get('approved_pattern') or {}).get('sha256') != target['pattern_ref']['sha256']):
        raise CompatibilityError('请先完成该案例在已批准 Pattern 范围内的审核。')
    lineage = pattern.get('lineage') or {}
    if (lineage.get('supporting_approved_case_sha256', {}).get(target['case_id']) != target['case_ref']['sha256']
            or lineage.get('supporting_fingerprint_sha256', {}).get(target['case_id']) != target['fingerprint_ref']['sha256']
            or receipt.get('supporting_fingerprint_sha256', {}).get(target['case_id']) != target['fingerprint_ref']['sha256']):
        raise CompatibilityError('Pattern supporting Case/Fingerprint version mismatch')
    case, case_receipt = read(paths['case_ref']), read(paths['case_approval_ref'])
    if (str(case.get('case_id')) != target['case_id'] or str(case_receipt.get('case_id')) != target['case_id']
            or case.get('validation', {}).get('passed') is not True):
        raise CompatibilityError('Case Approval identity or validation mismatch')
    storyboard_sha = target['storyboard_ref']['sha256']
    fingerprint = read(paths['fingerprint_ref'])
    if ((case.get('storyboard', {}).get('artifact') or {}).get('sha256') != storyboard_sha
            or case_receipt.get('frozen_artifacts', {}).get('reverse_storyboard_v1', {}).get('sha256') != storyboard_sha
            or fingerprint.get('provenance', {}).get('storyboard_sha256') != storyboard_sha):
        raise CompatibilityError('Case Approval/Fingerprint/Storyboard frozen lineage mismatch')
    profile, rules = read(paths['profile_ref']), read(paths['rules_ref'])
    export = profile.get('export_contract') or {}
    if profile != declared_mix_profile_v1_1(export.get('template_path'), export.get('template_sha256')):
        raise CompatibilityError('Unknown or modified Mix Profile contract')
    expected_rules = {'schema_version': RULES, 'target_profile': 'mix',
        'profile_sha256': target['profile_ref']['sha256'], 'pattern_scope_required': True,
        'rule_version': '1.1', 'automatic_approval': False}
    if (profile.get('profile_id') != 'mix' or profile.get('profile_version') != '1.1'
            or profile.get('status') != 'definition_only' or rules != expected_rules
            or profile.get('script_contract', {}).get('shape') != 'title_and_narration'
            or profile.get('storyboard_contract', {}).get('shape') != 'narration_to_visual_many_to_many'
            or profile.get('case_compatibility_policy') != {
                'approved_compatibility_required_for_new_matching': True, 'case_facts_transfer_permitted': False}
            or profile.get('pattern_compatibility_policy') != {'approved_pattern_required': True,
                'profile_compatibility_must_be_explicit': True, 'cross_profile_compatibility_is_automatic': False}
            or profile.get('validation_policy') != {'profile_compatible_case_required': True,
                'profile_compatible_pattern_required': True, 'privacy_gate_before_remote_call': True}):
        raise CompatibilityError('Mix Profile/rules version mismatch')
    audit = audit_case_profile_compatibility_v1(
        case_path=paths['case_ref'], case_approval_receipt_path=paths['case_approval_ref'],
        fingerprint_path=paths['fingerprint_ref'], storyboard_path=paths['storyboard_ref'],
        legacy_mix_case_ids=set())
    # Normalize provenance paths only in this derived audit, never in source bytes.
    for value in audit['lineage'].values():
        if isinstance(value, dict) and value.get('path'):
            value['path'] = Path(value['path']).resolve().relative_to(Path(root).resolve()).as_posix()
    if read(paths['audit_ref']) != audit or 'mix' not in audit['compatible_generation_profiles_candidate']:
        raise CompatibilityError('Native compatibility audit evidence changed or does not support Mix')
    return target


def prepare_target(root, *, case_id, pattern_id, profile_ref, rules_ref, pattern_path=None):
    from production_profile_v1 import audit_case_profile_compatibility_v1
    root = Path(root).resolve()
    validate(case_id, ID)
    validate(pattern_id, ID)
    case_dir = root / 'data/cases' / case_id
    if pattern_path is None:
        pattern_file = root / 'data/patterns/approved' / pattern_id / 'pattern_v1.json'
    else:
        pattern_file = Path(pattern_path).resolve()
        if not pattern_file.is_relative_to(root / 'data/patterns/approved'):
            raise CompatibilityError('Pattern version must remain in the original approved Pattern domain')
    pattern_dir = pattern_file.parent
    case = read(case_dir / 'case_v1.json')
    recorded = (case.get('storyboard', {}).get('artifact') or {})
    raw_storyboard = Path(recorded.get('path', ''))
    if not raw_storyboard.is_absolute():
        raw_storyboard = root / raw_storyboard
    raw_ref = ref(root, raw_storyboard)
    if raw_ref['sha256'] != recorded.get('sha256'):
        raise CompatibilityError('Approved Case storyboard changed')
    # A byte-identical structural snapshot, not an approval or media-rights grant.
    frozen_storyboard = root / DOMAIN / 'sources' / raw_ref['sha256'] / 'storyboard.json'
    write_bytes_once(frozen_storyboard, io_path(raw_storyboard).read_bytes())
    paths = {'case_ref': case_dir / 'case_v1.json', 'case_approval_ref': case_dir / 'approval_receipt.json',
             'fingerprint_ref': root / 'data/fingerprints' / case_id / 'case_fingerprint_v1.json',
             'storyboard_ref': frozen_storyboard,
             'pattern_ref': pattern_file, 'pattern_approval_ref': pattern_dir / 'approval_receipt.json'}
    audit = audit_case_profile_compatibility_v1(
        case_path=paths['case_ref'], case_approval_receipt_path=paths['case_approval_ref'],
        fingerprint_path=paths['fingerprint_ref'], storyboard_path=paths['storyboard_ref'], legacy_mix_case_ids=set())
    for value in audit['lineage'].values():
        if isinstance(value, dict) and value.get('path'):
            value['path'] = Path(value['path']).resolve().relative_to(root).as_posix()
    audit_path = root / DOMAIN / 'evidence' / f'{digest(audit)}.json'
    write_once(audit_path, audit)
    target = {'case_id': case_id, 'pattern_id': pattern_id, 'target_profile': 'mix',
              **{name: ref(root, path) for name, path in paths.items()},
              'profile_ref': profile_ref, 'rules_ref': rules_ref, 'audit_ref': ref(root, audit_path)}
    return validate_target(root, target)


def decision_graph(root, *, check_sources=False, expected_control_id=None):
    """Compute target heads from deterministic parent refs, never filename time."""
    root = Path(root).resolve()
    control_path = root / DOMAIN / 'control.json'
    if control_path.exists():
        control = read(control_path)
        if control.get('schema_version') != 'compatibility-control-v1.1':
            raise CompatibilityError('Unknown decision control schema')
        if expected_control_id is not None and expected_control_id != control.get('control_id'):
            raise CompatibilityError('Decision control context mismatch')
        expected_control_id = control.get('control_id')
    receipts = {}
    targets = {}
    for io_file in sorted(io_path(root / DOMAIN / 'decisions').glob('*.json')):
        path = identity_path(io_file)
        raw=read(path);contract=contract_for_version(raw.get('schema_version'))
        receipt = contract.validate_contract(raw, contract.APPROVAL)
        if not expected_control_id or receipt['control_id'] != expected_control_id:
            raise CompatibilityError('Decision belongs to another control Authority')
        if path.stem != receipt['operation_id']:
            raise CompatibilityError('Decision operation/path mismatch')
        validate_grant_proof(receipt['authorization'],capability=contract.CAPABILITY)
        if receipt['actor'] != receipt['authorization']['principal']:
            raise CompatibilityError('Decision actor mismatch')
        preview = contract.validate_contract(read(resolve_ref(root, receipt['preview_ref'])), contract.PREVIEW)
        if any(receipt[k] != preview[k] for k in ('control_id', 'actor', 'authorization', 'operation_id', 'source_snapshot', 'decisions')):
            raise CompatibilityError('Decision differs from its authenticated preview')
        snapshot = contract.validate_contract(read(resolve_ref(root, receipt['source_snapshot'])), contract.SNAPSHOT)
        if snapshot['targets'] != [item['target'] for item in receipt['decisions']]:
            raise CompatibilityError('Decision/source snapshot mismatch')
        receipt_ref = ref(root, path)
        receipts[path.relative_to(root).as_posix()] = receipt
        seen = set()
        for decision in receipt['decisions']:
            identity = target_id(decision['target'])
            if identity != decision['target_id'] or identity in seen:
                raise CompatibilityError('Duplicate or invalid decision target')
            seen.add(identity)
            if check_sources:
                validate_target(root, decision['target'])
            targets.setdefault(identity, []).append({'decision': decision, 'receipt_ref': receipt_ref})
    heads = {}
    for identity, nodes in targets.items():
        by_ref = {node['receipt_ref']['sha256']: node for node in nodes}
        children = {}
        for node in nodes:
            parent = node['decision']['parent']
            key = parent['sha256'] if parent else None
            if key in children:
                raise CompatibilityError('Compatibility decision fork')
            if parent:
                parent_node = by_ref.get(key)
                if not parent_node or parent_node['receipt_ref'] != parent:
                    raise CompatibilityError('Compatibility decision parent missing')
            children[key] = node
        visited, key, effective = set(), None, None
        while key in children:
            node = children[key]
            key = node['receipt_ref']['sha256']
            if key in visited:
                raise CompatibilityError('Compatibility decision cycle')
            visited.add(key)
            action = node['decision']['action']
            if action == 'approve':
                if node['decision']['withdraws'] is not None:
                    raise CompatibilityError('Approve cannot withdraw another decision')
                effective = node
            elif action == 'withdraw':
                if not effective or node['decision']['withdraws'] != effective['receipt_ref']:
                    raise CompatibilityError('Withdraw must reference exact effective approval')
                effective = None
            elif node['decision']['withdraws'] is not None:
                raise CompatibilityError('Reject cannot silently withdraw approval')
            head = node
        if len(visited) != len(nodes):
            raise CompatibilityError('Disconnected Compatibility decision history')
        heads[identity] = {'head': head['receipt_ref'],
                           'effective': effective['receipt_ref'] if effective else None,
                           'target': head['decision']['target']}
    return {'heads': heads, 'head_sha256': digest(heads), 'receipts': receipts}


@contextmanager
def reviewer_operation(root, actor):
    with operation_lock(root, 'authority_backup_gate', shared=True):
        with operation_lock(root, CONTROL_LOCK):
            with operation_lock(root, f"profile-reviewer:{actor['namespace']}:{actor['user_id']}"):
                yield


def preview(root, database_path, actor, operation_id, decisions):
    root = Path(root).resolve()
    validate(operation_id, OPERATION)
    contract=contract_for_targets(decisions)
    authorization(database_path, actor,capability=contract.CAPABILITY)
    from profile_compatibility_release_v1_1 import CONFIG, initialize_control
    if (root / CONFIG).exists() and Path(read(root / CONFIG)['control_root']).resolve() != root:
        raise CompatibilityError('Compatibility decisions must be reviewed at their configured source Authority')
    control_id = initialize_control(root)['control_id']
    with reviewer_operation(root, actor):
        grant = authorization(database_path, actor,capability=contract.CAPABILITY)
        graph = decision_graph(root)
        directory = root / DOMAIN / 'operations' / operation_id
        path = directory / 'preview.json'
        if path.exists():
            old = contract.validate_contract(read(path), contract.PREVIEW)
            if old['control_id'] != control_id or old['actor'] != actor or old['authorization'] != grant or old['decisions'] != decisions:
                raise CompatibilityError('Operation preview replay conflicts')
            return {'operation_id': operation_id, 'preview_ref': ref(root, path), 'preview': old}
        if not isinstance(decisions, list) or not decisions:
            raise CompatibilityError('Explicit per-target decisions required')
        identities = set()
        for decision in decisions:
            validate(decision, contract.DECISION)
            if decision['action'] != 'withdraw':
                validate_target(root, decision['target'])
            identity = target_id(decision['target'])
            if decision['target_id'] != identity or identity in identities:
                raise CompatibilityError('Invalid or duplicate target')
            identities.add(identity)
            current = graph['heads'].get(identity, {})
            if decision['parent'] != current.get('head'):
                raise CompatibilityError('Decision parent changed; refresh review')
            if decision['action'] == 'withdraw' and (not current.get('effective') or decision['withdraws'] != current['effective']):
                raise CompatibilityError('Withdraw does not name current approval')
            if decision['action'] != 'withdraw' and decision['withdraws'] is not None:
                raise CompatibilityError('Only withdraw can name an approval to withdraw')
        snapshot = {'schema_version': contract.SNAPSHOT, 'targets': [d['target'] for d in decisions]}
        snapshot_path = directory / 'source_snapshot.json'
        write_once(snapshot_path, contract.validate_contract(snapshot, contract.SNAPSHOT))
        value = {'schema_version': contract.PREVIEW, 'operation_id': operation_id, 'control_id': control_id, 'actor': actor,
                 'authorization': grant, 'source_snapshot': ref(root, snapshot_path),
                 'decisions': decisions, 'created_at': datetime.now(timezone.utc).isoformat()}
        write_once(path, contract.validate_contract(value, contract.PREVIEW))
        return {'operation_id': operation_id, 'preview_ref': ref(root, path), 'preview': value}


def decide(root, database_path, actor, operation_id, preview_sha256):
    root = Path(root).resolve()
    validate(operation_id, OPERATION)
    from profile_compatibility_release_v1_1 import CONFIG
    if (root / CONFIG).exists() and Path(read(root / CONFIG)['control_root']).resolve() != root:
        raise CompatibilityError('Compatibility decisions must be confirmed at their configured source Authority')
    with reviewer_operation(root, actor):
        path = root / DOMAIN / 'operations' / operation_id / 'preview.json'
        raw=read(path);contract=contract_for_version(raw.get('schema_version'))
        value = contract.validate_contract(raw, contract.PREVIEW)
        grant = authorization(database_path, actor,capability=contract.CAPABILITY)
        control = read(root / DOMAIN / 'control.json')
        if (value['control_id'] != control.get('control_id') or control.get('schema_version') != 'compatibility-control-v1.1'
                or file_sha(path) != preview_sha256 or value['actor'] != actor or value['authorization'] != grant):
            raise CompatibilityError('Preview identity, grant or SHA changed; review again')
        graph = decision_graph(root)
        receipt_path = root / DOMAIN / 'decisions' / f'{operation_id}.json'
        if receipt_path.exists():
            receipt = contract.validate_contract(read(receipt_path), contract.APPROVAL)
            if receipt['preview_ref'] != ref(root, path):
                raise CompatibilityError('Conflicting operation replay')
            for decision in receipt['decisions']:
                if graph['heads'][decision['target_id']]['head'] != ref(root, receipt_path):
                    raise CompatibilityError('Old operation cannot replay after a newer decision')
            return {'receipt_ref': ref(root, receipt_path), 'receipt': receipt, 'recovered': True}
        for decision in value['decisions']:
            if decision['action'] != 'withdraw':
                validate_target(root, decision['target'])
            if decision['parent'] != graph['heads'].get(decision['target_id'], {}).get('head'):
                raise CompatibilityError('Decision head advanced since preview')
        intent_path = path.with_name('decision_intent.json')
        receipt = {**value, 'schema_version': contract.APPROVAL, 'preview_ref': ref(root, path),
                   'decided_at': datetime.now(timezone.utc).isoformat(), 'human_gate': True}
        del receipt['created_at']
        if intent_path.exists():
            saved = contract.validate_contract(read(intent_path), contract.APPROVAL)
            if any(saved[k] != receipt[k] for k in receipt if k != 'decided_at'):
                raise CompatibilityError('Interrupted Human decision conflicts with current preview')
            receipt = saved
        else:
            write_once(intent_path, contract.validate_contract(receipt, contract.APPROVAL))
        contract.validate_contract(receipt, contract.APPROVAL)
        write_once(receipt_path, receipt)
        decision_graph(root)
        return {'receipt_ref': ref(root, receipt_path), 'receipt': receipt, 'recovered': False}
