"""Production-purpose review delegated by the existing Compatibility/Release owner.

Engineering permission and deployment switches are not an admission. Only an
explicit native Human operation, followed by exact Release activation, can make
this scope effective. Isolated v1.1/v1.2 artifacts are never edited or relabelled.
"""
from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from profile_compatibility_authorization_v1 import authorization, validate_grant_proof
from profile_compatibility_contract_v1_1 import (
    ACTOR, HASH, NULL_REF, OPERATION, REF, TEXT, CompatibilityError, array, obj, validate,
)
from profile_compatibility_decisions_v1_1 import (
    DOMAIN, decision_graph, digest, read, ref, resolve_ref, reviewer_operation, write_once,
)

PREVIEW = 'creative-production-admission-preview-v1.0'
DECISION = 'creative-production-admission-decision-v1.0'
PATTERN_REVIEW = 'news-pattern-production-purpose-review-v1.0'
PATTERN_DECISION = 'news-pattern-production-purpose-decision-v1.0'
SCOPE = 'creative-production-admission-scope-v1.0'
POLICY = 'native-batch-admission-policy-v1.1'
DIRECTORY = DOMAIN / 'production_admission'
MAXIMUM_VIDEOS = 5  # Candidate initial production scope; never a 20/40 capacity claim.
PROFILE_SETS = [['mix'], ['news'], ['mix', 'news']]
STYLES = ['persona', 'story', 'conversion']
REUSE = ['novel_content', 'cross_profile_repurpose']
GRANT = obj({'principal': ACTOR, 'capability': TEXT, 'event_sha256': HASH,
             'events': array({'type': 'object'}, 1)})
SCOPE_SCHEMA = obj({'schema_version': {'const': SCOPE}, 'profiles': {'enum': PROFILE_SETS},
    'creative_styles': array(TEXT), 'news_reuse_intents': array(TEXT),
    'maximum_videos': {'type': 'integer', 'minimum': 1, 'maximum': MAXIMUM_VIDEOS},
    'real_model_execution_authorized': {'const': True},
    'real_model_quality': {'const': 'not_validated'},
    'dispatch_per_business': {'const': 1}, 'unknown_retry': {'const': 'explicit-native-only'}})
PATTERN_SCHEMA = obj({'schema_version': {'const': PATTERN_REVIEW}, 'operation_id': OPERATION,
    'actor': ACTOR, 'authorization': GRANT, 'decision': {'const': 'approve_exact_production_purpose'},
    'patterns': array(obj({'pattern_ref': REF, 'pattern_approval_ref': REF}), 1),
    'purpose': {'const': 'production'}, 'case_scope_expanded': {'const': False},
    'customer_truth_created': {'const': False}, 'human_confirmation_required': {'const': True}, 'at': TEXT})
SNAPSHOT_SCHEMA = obj({'scope': SCOPE_SCHEMA, 'source_repo_commit': {'type': 'string', 'pattern': '^[a-f0-9]{40}$'},
    'source_inventory_sha256': HASH, 'decision_head_sha256': HASH,
    'approval_refs': array(REF, 1), 'pattern_review': {'oneOf': [{'type': 'null'}, PATTERN_SCHEMA]},
    'news_validation_refs': array(REF),
    'news_validation_summary': {'oneOf':[{'type':'null'}, obj({
        'schema_version':{'const':'news-production-qualification-summary-v1.0'},
        'novel_evidence_sha256':HASH,'repurpose_evidence_sha256':HASH,
        'profile_ref':REF,'pattern_ref':REF,'pattern_approval_ref':REF,
        'native_paths_verified':{'const':True},'real_model_quality':{'const':'not_validated'}})]}})
PREVIEW_SCHEMA = obj({'schema_version': {'const': PREVIEW}, 'operation_id': OPERATION,
    'control_id': OPERATION, 'actor': ACTOR, 'authorizations': array(GRANT, 1),
    'parent': NULL_REF, 'action': {'enum': ['approve', 'withdraw']},
    'snapshot': SNAPSHOT_SCHEMA, 'reason': TEXT, 'created_at': TEXT})
DECISION_SCHEMA = obj({'schema_version': {'const': DECISION}, 'operation_id': OPERATION,
    'control_id': OPERATION, 'actor': ACTOR, 'authorizations': array(GRANT, 1),
    'parent': NULL_REF, 'action': {'enum': ['approve', 'withdraw']},
    'preview_ref': REF, 'snapshot': SNAPSHOT_SCHEMA, 'pattern_review_ref': NULL_REF,
    'reason': TEXT, 'decided_at': TEXT, 'human_gate': {'const': True}})
PATTERN_DECISION_SCHEMA = obj({**PATTERN_SCHEMA['properties'],
    'schema_version': {'const': PATTERN_DECISION}, 'human_gate': {'const': True}, 'confirmed_at': TEXT})
SCHEMAS = {SCOPE: SCOPE_SCHEMA, PREVIEW: PREVIEW_SCHEMA, DECISION: DECISION_SCHEMA,
           PATTERN_REVIEW: PATTERN_SCHEMA, PATTERN_DECISION: PATTERN_DECISION_SCHEMA}


class ProductionAdmissionError(CompatibilityError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def check(value, version):
    validate(value, SCHEMAS[version])
    if version == SCOPE:
        if (value['maximum_videos'] > MAXIMUM_VIDEOS
                or value['creative_styles'] != sorted(set(value['creative_styles']))
                or not set(value['creative_styles']) <= set(STYLES)
                or value['news_reuse_intents'] != sorted(set(value['news_reuse_intents']))
                or not set(value['news_reuse_intents']) <= set(REUSE)
                or bool(value['creative_styles']) != ('mix' in value['profiles'])
                or bool(value['news_reuse_intents']) != ('news' in value['profiles'])):
            raise CompatibilityError('Invalid bounded production admission scope')
    if version in {PREVIEW, DECISION}:
        check(value['snapshot']['scope'], SCOPE)
        grants(value['actor'], value['authorizations'], value['snapshot']['scope']['profiles'])
        pattern = value['snapshot']['pattern_review']
        if bool(pattern) != ('news' in value['snapshot']['scope']['profiles']):
            raise CompatibilityError('Independent News Pattern purpose review is required')
        news = 'news' in value['snapshot']['scope']['profiles']
        if (len(value['snapshot']['news_validation_refs']) != (2 if news else 0)
                or bool(value['snapshot']['news_validation_summary']) != news):
            raise CompatibilityError('Both Native News paths require exact qualification before production review')
        if news:
            summary=value['snapshot']['news_validation_summary']
            if ({summary['novel_evidence_sha256'],summary['repurpose_evidence_sha256']}
                    != {item['sha256'] for item in value['snapshot']['news_validation_refs']}
                    or summary['novel_evidence_sha256']==summary['repurpose_evidence_sha256']):
                raise CompatibilityError('Production qualification summary does not bind both exact Native outcomes')
        if pattern:
            from news_pattern_authority_v1_1 import validate_production_purpose_review
            validate_production_purpose_review(pattern)
        if version == DECISION and bool(value['pattern_review_ref']) != bool(pattern):
            raise CompatibilityError('Missing independent Pattern purpose decision receipt')
    return value


def capabilities(profiles):
    from profile_compatibility_contract_v1_1 import CAPABILITY as MIX
    from profile_compatibility_contract_v1_2 import CAPABILITY as NEWS
    return [MIX if profile == 'mix' else NEWS for profile in profiles]


def grants(actor, proofs, profiles):
    if [proof['capability'] for proof in proofs] != capabilities(profiles):
        raise CompatibilityError('Each Profile requires its own independent reviewer permission')
    for proof in proofs:
        validate_grant_proof(proof, capability=proof['capability'])
        if proof['principal'] != actor:
            raise CompatibilityError('Production review cannot borrow another principal')


def source_identity(repo_root, *, require_clean=False):
    from profile_compatibility_release_v1_1 import source_blobs
    root = Path(repo_root).resolve()
    if require_clean and subprocess.check_output(
            ['git', '-C', str(root), 'status', '--porcelain=v1', '--untracked-files=all'], text=True).strip():
        raise CompatibilityError('Production review requires accurately committed clean sources')
    commit = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    blobs = source_blobs(root, commit)
    inventory = []
    for name, blob in blobs.items():
        actual = (root / name).read_bytes()
        if actual.replace(b'\r\n', b'\n') != blob.replace(b'\r\n', b'\n'):
            raise CompatibilityError('Executing production source differs from its Commit')
        inventory.append({'path': name, 'git_blob_sha256': hashlib.sha256(blob).hexdigest(),
                          'checkout_sha256': hashlib.sha256(actual).hexdigest()})
    return commit, digest(inventory)


def targets_for_scope(graph, scope):
    selected = [node['target'] for node in graph['heads'].values()
                if node['effective'] and node['target']['target_profile'] in scope['profiles']]
    if {target['target_profile'] for target in selected} != set(scope['profiles']):
        raise CompatibilityError('A selected Profile has no current independently approved structural scope')
    return selected


def head(root):
    """One append-only release-admission chain. Withdraw never revives an older head."""
    records = {}
    for path in sorted((Path(root) / DIRECTORY / 'decisions').glob('*.json')):
        item = check(read(path), DECISION)
        if path.stem != item['operation_id']:
            raise CompatibilityError('Production decision operation/path differs')
        pre = check(read(resolve_ref(root, item['preview_ref'])), PREVIEW)
        for key in ('operation_id', 'control_id', 'actor', 'authorizations', 'parent',
                    'action', 'snapshot', 'reason'):
            if pre[key] != item[key]:
                raise CompatibilityError('Production decision differs from its reviewed preview')
        if item['pattern_review_ref']:
            pattern = check(read(resolve_ref(root, item['pattern_review_ref'])), PATTERN_DECISION)
            proposal = {k: v for k, v in pattern.items() if k not in {'human_gate', 'confirmed_at'}}
            proposal['schema_version'] = PATTERN_REVIEW
            if proposal != item['snapshot']['pattern_review']:
                raise CompatibilityError('Pattern purpose receipt differs from Human review')
        records[digest(ref(root, path))] = (ref(root, path), item)
    parent, visited, current = None, set(), None
    while True:
        children = [(reference, item) for reference, item in records.values() if item['parent'] == parent]
        if not children:
            break
        if len(children) != 1:
            raise CompatibilityError('Production admission history fork')
        reference, item = children[0]
        if reference['sha256'] in visited:
            raise CompatibilityError('Production admission history cycle')
        visited.add(reference['sha256'])
        if current and item['control_id'] != current[1]['control_id']:
            raise CompatibilityError('Production admission control changed')
        current = (reference, item)
        parent = reference
    if len(visited) != len(records):
        raise CompatibilityError('Disconnected production admission history')
    return current


def prepare(root, database_path, actor, operation_id, scope, repo_root, *, reason, action='approve',news_validation_refs=None):
    """Trusted local Human preview; no grants, Case approvals or models are created."""
    from profile_compatibility_release_v1_1 import initialize_control
    validate(operation_id, OPERATION)
    if action not in {'approve', 'withdraw'} or not isinstance(reason, str) or not reason.strip():
        raise CompatibilityError('Explicit production action and reason required')
    root = Path(root).resolve()
    from profile_compatibility_release_v1_1 import CONFIG
    config_path=root/CONFIG
    if config_path.is_file() and Path(read(config_path)['control_root']).resolve()!=root:
        raise CompatibilityError('Production purpose decisions must be reviewed at their configured source Authority')
    control = initialize_control(root)
    with reviewer_operation(root, actor,allow_native_reads=True):
        path = root / DIRECTORY / 'operations' / operation_id / 'preview.json'
        old = read(path) if path.is_file() else None
        previous = head(root)
        if action == 'withdraw':
            if not previous or previous[1]['action'] != 'approve':
                raise CompatibilityError('No effective production admission to withdraw')
            snapshot = previous[1]['snapshot']
            scope = snapshot['scope']
        else:
            check(scope, SCOPE)
            graph = decision_graph(root)
            targets = targets_for_scope(graph, scope)
            from profile_compatibility_decisions_v1_1 import validate_targets
            validate_targets(root, targets)
            commit, inventory = source_identity(repo_root, require_clean=True)
            pattern = None
            validation_refs = news_validation_refs or []
            summary = None
            if 'news' in scope['profiles']:
                from news_pattern_authority_v1_1 import prepare_production_purpose_review
                pattern = prepare_production_purpose_review(root, database_path, actor, operation_id,
                    [target for target in targets if target['target_profile'] == 'news'])
                if old and old['snapshot']['pattern_review']:
                    pattern['at']=old['snapshot']['pattern_review']['at']
                from news_qualification_v1_2 import production_summary
                summary=production_summary(root,validation_refs)
                if any(summary[key]!=target[key] for target in targets if target['target_profile']=='news'
                        for key in ('profile_ref','pattern_ref','pattern_approval_ref')):
                    raise CompatibilityError('News qualification belongs to another structural scope')
            elif validation_refs:
                raise CompatibilityError('Mix-only admission cannot carry News qualification')
            approvals = sorted({node['effective']['path']: node['effective']
                for node in graph['heads'].values() if node['effective']
                and node['target']['target_profile'] in scope['profiles']}.values(), key=lambda r: r['path'])
            snapshot = {'scope': scope, 'source_repo_commit': commit,
                'source_inventory_sha256': inventory, 'decision_head_sha256': graph['head_sha256'],
                'approval_refs': approvals, 'pattern_review': pattern,
                'news_validation_refs':validation_refs,'news_validation_summary':summary}
        proofs = [authorization(database_path, actor, capability=cap) for cap in capabilities(scope['profiles'])]
        value = {'schema_version': PREVIEW, 'operation_id': operation_id, 'control_id': control['control_id'],
            'actor': actor, 'authorizations': proofs, 'parent': previous[0] if previous else None,
            'action': action, 'snapshot': snapshot, 'reason': reason.strip(),
            'created_at': old['created_at'] if old else datetime.now(timezone.utc).isoformat()}
        write_once(path, check(value, PREVIEW))
        return {'preview_ref': ref(root, path), 'preview': value}


def confirm(root, database_path, actor, operation_id, expected_sha256, repo_root):
    """Original Native Human operation. Explicit confirmation is never inferred."""
    validate(operation_id, OPERATION)
    root = Path(root).resolve()
    with reviewer_operation(root, actor,allow_native_reads=True):
        path = root / DIRECTORY / 'operations' / operation_id / 'preview.json'
        reference = ref(root, path)
        if reference['sha256'] != expected_sha256:
            raise CompatibilityError('Production preview SHA changed')
        preview = check(read(path), PREVIEW)
        if preview['actor'] != actor:
            raise CompatibilityError('Production preview belongs to another principal')
        scope = preview['snapshot']['scope']
        current_proofs = [authorization(database_path, actor, capability=cap) for cap in capabilities(scope['profiles'])]
        if current_proofs != preview['authorizations']:
            raise CompatibilityError('Production reviewer permission changed')
        output = root / DIRECTORY / 'decisions' / f'{operation_id}.json'
        current = head(root)
        if output.is_file():
            if not current or current[0] != ref(root, output):
                raise CompatibilityError('Production decision replay was superseded')
            return {'decision_ref': current[0], 'recovered': True}
        if (current[0] if current else None) != preview['parent']:
            raise CompatibilityError('Production admission head changed; review again')
        pattern_ref = None
        if preview['action'] == 'approve':
            if source_identity(repo_root, require_clean=True) != (
                    preview['snapshot']['source_repo_commit'], preview['snapshot']['source_inventory_sha256']):
                raise CompatibilityError('Production machine sources changed after preview')
            graph = decision_graph(root)
            if graph['head_sha256'] != preview['snapshot']['decision_head_sha256']:
                raise CompatibilityError('Compatibility changed after production preview')
            from profile_compatibility_decisions_v1_1 import validate_targets
            validate_targets(root, targets_for_scope(graph, scope))
            if preview['snapshot']['news_validation_summary']:
                from news_qualification_v1_2 import production_summary
                if production_summary(root,preview['snapshot']['news_validation_refs'])!=preview['snapshot']['news_validation_summary']:
                    raise CompatibilityError('Native News qualification changed after preview')
            if preview['snapshot']['pattern_review']:
                from news_pattern_authority_v1_1 import confirm_production_purpose_review
                pattern_ref = confirm_production_purpose_review(root, database_path, actor,
                    preview['snapshot']['pattern_review'])
        elif preview['snapshot']['pattern_review']:
            pattern_ref = current[1]['pattern_review_ref']
        value = {key: preview[key] for key in ('operation_id','control_id','actor','authorizations',
            'parent','action','snapshot','reason')}
        value.update(schema_version=DECISION, preview_ref=reference, pattern_review_ref=pattern_ref,
                     decided_at=datetime.now(timezone.utc).isoformat(), human_gate=True)
        write_once(output, check(value, DECISION))
        return {'decision_ref': ref(root, output), 'recovered': False}


def current(root, reference=None, *, check_sources=True, require_control=True):
    value = head(root)
    if not value or value[1]['action'] != 'approve' or reference is not None and value[0] != reference:
        raise ProductionAdmissionError('CREATION_PRODUCTION_ADMISSION_REQUIRED',
            'Production admission is missing, superseded or withdrawn')
    reference, decision = value
    control_path = Path(root) / DOMAIN / 'control.json'
    if require_control or control_path.is_file():
        control = read(control_path)
        if decision['control_id'] != control['control_id']:
            raise CompatibilityError('Production admission belongs to another control')
    if check_sources:
        graph = decision_graph(root, expected_control_id=decision['control_id'])
        if graph['head_sha256'] != decision['snapshot']['decision_head_sha256']:
            raise CompatibilityError('Production Compatibility graph changed')
        from profile_compatibility_decisions_v1_1 import validate_targets
        validate_targets(root, targets_for_scope(graph, decision['snapshot']['scope']))
    return reference, decision


def validate_active(active):
    decision = active['production_admission']
    scope = decision['snapshot']['scope']
    if active['manifest']['purpose'] != 'production' or active['manifest']['profiles'] != scope['profiles']:
        raise CompatibilityError('Production admission/Release scope mismatch')
    if (active['manifest']['source_repo_commit'] != decision['snapshot']['source_repo_commit']
            or digest(active['manifest']['source_files']) != decision['snapshot']['source_inventory_sha256']):
        raise CompatibilityError('Production admission does not bind these exact machine sources')
    return scope


def batch_policy(active):
    scope = validate_active(active)
    return {'schema_version': POLICY, 'policy_version': 'production-1',
        'maximum_logical_slots': scope['maximum_videos'], 'maximum_pending_native_requests': scope['maximum_videos'],
        'dispatch_per_business': 1, 'mix_style_quantities': [1, 2],
        'allowed_profiles': scope['profiles'], 'maximum_explicit_cycles': 1,
        'production_admission_ref': active['manifest']['production_admission_ref'],
        'production_qualification_granted': True, 'unknown_retry': 'explicit-native-only',
        'legacy_active_exception': False}


def require_selection(active, *, style=None, profile=None, reuse_intent=None, execution=False):
    scope = validate_active(active)
    if (profile and profile not in scope['profiles'] or style and style not in scope['creative_styles']
            or profile == 'news' and reuse_intent not in scope['news_reuse_intents']):
        raise ProductionAdmissionError('CREATION_PRODUCTION_SELECTION_NOT_ADMITTED',
            'This exact production Style/Profile/source is not admitted')
    if execution and not scope['real_model_execution_authorized']:
        raise ProductionAdmissionError('CREATION_PRODUCTION_EXECUTION_NOT_AUTHORIZED',
            'Real model execution is not authorized by this production admission')
    return scope


def require_native_execution(root, *, profile, style=None, reuse_intent='novel_content'):
    """Native writers cannot bypass admission through an old Console/CLI entry."""
    from profile_compatibility_release_v1_1 import CONFIG,effective_runtime
    path = Path(root)/CONFIG
    if path.is_file() and read(path).get('schema_version')=='compatibility-runtime-config-v1.3':
        return require_selection(effective_runtime(root),profile=profile,style=style,
            reuse_intent=reuse_intent,execution=True)
    return None
