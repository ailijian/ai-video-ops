"""One explicit Speaker confirmation over the existing Review and Approval owners."""
from __future__ import annotations

import copy
import re
from datetime import datetime, timezone

from human_review_operations_v1 import digest, file_sha, read, write_once
from . import review_commands, customer_confirmation as common
from .canonical_gateway import CanonicalOperationError

VERSION = 'speaker-final-confirmation-v1.0'
APPROVE = 'approve_speaker_profile'


def fail(code, message):
    return CanonicalOperationError(code, message, '请核对最新出镜人资料；已保存的人审记录及审批收据会保留。')


def guard(settings, identity, *, all_versions=False, operation_id=None):
    root = settings.pipeline_root/'data/review_operations/speaker'/identity
    for path in root.glob('*/intent.json'):
        if path.parent.name != operation_id and not (path.parent/'result.json').exists() and (
                all_versions or read(path).get('version') == review_commands.SPEAKER_VERSION):
            raise fail('SPEAKER_CONFIRMATION_PENDING', '上次出镜人确认尚未完成，请先继续或取消原操作。')


def _protective_scope(value):
    """Conservative recognition of own-work limits, never a grant of personal claims.

    Unrecognised wording stays an explicit review choice. Every clause must only
    restrict scope; matching a restrictive prefix cannot hide a later expansion.
    """
    values = value if isinstance(value, list) else [value]
    clauses = [re.sub(r'\s+', '', part) for item in values if isinstance(item, str)
        for part in re.split(r'[，,。；;\n]', item) if part.strip()]
    if not clauses or len(values) != sum(isinstance(item, str) for item in values):
        return False
    patterns = (
        r'(?:只|仅|仅限|仅限于)(?:讲|讲述|分享|使用|以)?(?:本人|自己)(?:实际)?(?:参与|承担|负责)(?:过)?的?(?:工作|职责|经历|经验|门店服务经验|服务经验)(?:进行第一人称表达|进行表达)?',
        r'不(?:转用|挪用|冒用)(?:公司|企业|他人)的?(?:全部)?(?:成绩|业绩|经历|成果)',
        r'不把(?:公司|企业|他人)的?(?:全部)?(?:成绩|业绩|经历|成果)(?:写成|当作|作为|算作)(?:本人|自己|个人)的?(?:功劳|经历|成绩|成果)',
    )
    return all(any(re.fullmatch(pattern, clause) for pattern in patterns) for clause in clauses)


def sourced_scope(candidate, artifact, intake, business_id, speaker_id):
    """Read-only proof from canonical Intake; client/model safety flags are ignored."""
    answers = intake.get('raw_answers')
    raw_sha = intake.get('raw_input_contract', {}).get('raw_answers_sha256')
    reference = artifact.get('intake_ref', {})
    if (not isinstance(answers, list) or not raw_sha or digest(answers) != raw_sha
            or reference.get('raw_answers_sha256') != raw_sha
            or reference.get('intake_id') != intake.get('intake_id')
            or intake.get('business_ref', {}).get('persona_id') != business_id
            or intake.get('speaker_selection', {}).get('speaker_ref', {}).get('persona_id') != speaker_id
            or candidate.get('persona_scope') != 'speaker'):
        return False
    matches = [v for v in answers if v.get('answer_id') == candidate.get('raw_answer_ref')]
    if len(matches) != 1 or not matches[0].get('source_ref') or matches[0]['source_ref'] != candidate.get('source_ref'):
        return False
    quote = re.sub(r'\s+', '', str(candidate.get('source_excerpt') or ''))
    return bool(quote and quote in re.sub(r'\s+', '', str(matches[0].get('answer_text') or '')))


def review_policy(candidate, *, source_verified=False):
    """Pending selection only. Final Human submission still covers every candidate."""
    conflict = bool(candidate.get('conflict_refs') or candidate.get('authority_conflict') or candidate.get('severity') == 'critical'
        or re.search(r'冲突|争议|待核实|未核实|conflict|unverified', str(candidate.get('review_note', '')), re.I))
    protective = bool(not conflict and source_verified and candidate.get('target_field') == 'role_scope_constraints'
        and _protective_scope(candidate.get('normalized_value')))
    risk = conflict or (candidate.get('target_field') in {'public_display_name', 'public_role', 'first_person_scope', 'role_scope_constraints', 'first_person_forbidden_claims'} and not protective)
    return {'default_review_selection': None if risk else 'approve',
        'protective_scope': protective,
        'review_exception_reason': '请明确核对身份、本人经历或表达边界；不会自动解除已有重要限制。' if risk else ''}


def projection(value):
    from .customer_speaker_confirmation import speaker_projection
    return speaker_projection(value)


def preview(settings, business_id, identity, user_id, actor, payload):
    from .speaker_gateway import _latest_intake_dir, get_speaker_detail
    from .persona_authority import resolve_persona_authority, validate_speaker_business_binding
    from speaker_fact_review_v1 import (validate_request, validate_decision_coverage, apply_decisions,
        build_speaker_persona_input, reviewed_speaker_sources, speaker_blockers)
    from persona_review_lifecycle_v1 import effective_sources, apply_revision_input
    from approve_persona_v1 import validate_approval_authority
    guard(settings, identity, all_versions=True)
    # Signature, exact actor, business, node and current snapshot are checked without writing an intent.
    review_commands.begin(settings, 'speaker', identity, user_id, payload['review_context'],
        {'request_path': f'/api/customers/{business_id}/speakers/{identity}/facts/review', 'payload': {}},
        business_id=business_id, validate_only=True)
    detail = get_speaker_detail(settings, business_id, identity)
    if detail['status'] not in {'fact_review_required', 'persona_review_required'}:
        raise fail('SPEAKER_CONFIRMATION_STALE', '当前出镜人不处于可确认阶段，请先处理分析、补充或客户版本复核。')
    directory = _latest_intake_dir(settings, business_id, identity)
    business = resolve_persona_authority(settings, business_id, 'business').current
    if not directory or not business:
        raise fail('SPEAKER_CONFIRMATION_STALE', '缺少当前已批准客户或本人来源资料。')
    request = validate_request({**copy.deepcopy(payload), 'business_id': business_id, 'speaker_id': identity,
        'intake_id': directory.name, 'reviewer': actor})
    review_path = directory/'speaker_fact_review_v1.json'
    completed = read(review_path) if review_path.is_file() else None
    complete = bool(completed and str(completed['status']).startswith('completed_'))
    target = resolve_persona_authority(settings, identity, 'speaker').review_candidate
    blockers = []
    if complete:
        if request['decisions']:
            raise fail('FACT_REVIEW_DECISION_IMMUTABLE', '已保存的人物核对记录不能再次覆盖。')
        if not target:
            raise fail('SPEAKER_CONFIRMATION_STALE', '本轮尚无准确的待批准人物档案。')
        validate_speaker_business_binding(target, business)
        meaning = projection(target['artifact'])
        blockers = validate_approval_authority(target['artifact'], target['path'])
    else:
        candidates = read(directory/'speaker_fact_candidates_v1.json')
        required = {v['fact_candidate_id'] for v in candidates['fact_candidates'] if v['candidate_state'] == 'requires_review'}
        supplied = {v['candidate_id'] for v in request['decisions']}
        if supplied - required:
            raise fail('SPEAKER_REVIEW_UNKNOWN_CANDIDATE', '不能提交不属于本轮的人物信息。')
        missing = required - supplied
        # Simulate pending rows as excluded only to calculate a read-only preview.
        # These simulated decisions are never signed as a Human review or executed.
        proposed = request['decisions'] + [{'candidate_id': v, 'decision': 'reject'} for v in sorted(missing)]
        validate_decision_coverage(candidates, proposed)
        reviewed = apply_decisions(intake=read(directory/'speaker_intake_v1.json'), candidate_artifact=candidates,
            decisions=proposed, reviewer=actor, reviewed_at=datetime.now(timezone.utc).isoformat())
        reviewed_path = directory/'reviewed_speaker_fact_candidates_v1.json'
        sources = [(p, v) for p, v in reviewed_speaker_sources(settings.pipeline_root, business_id, identity) if p != reviewed_path]
        sources.append((reviewed_path, reviewed))
        source = build_speaker_persona_input(business_id=business_id, speaker_id=identity,
            speaker_type=detail['speaker_type'], intake_id=directory.name, reviewed=reviewed,
            reviewed_path=reviewed_path, reviewed_sources=effective_sources(sources, speaker=True))
        apply_revision_input(settings.pipeline_root, 'speaker', identity, directory, source, reviewed)
        meaning = projection(source)
        blockers = speaker_blockers(source)
        if missing:
            blockers = [f'还有 {len(missing)} 项信息需要明确处理。', *blockers]
    frozen = {}
    mutable = {directory/name for name in ('speaker_fact_review_v1.json', 'reviewed_speaker_fact_candidates_v1.json', 'speaker_persona_input_v1.json')} if not complete else set()
    for base in (settings.pipeline_root/'data/speaker_intakes'/business_id/identity, settings.pipeline_root/'data/personas'/identity,
                 settings.pipeline_root/'data/speaker_revalidations'/identity):
        for path in base.rglob('*.json'):
            if path not in mutable and not (target and path == target['path']):
                frozen[str(path.relative_to(settings.pipeline_root))] = file_sha(path)
    bundle = {'schema_version': VERSION, 'business_id': business_id, 'speaker_id': identity, 'intake_id': directory.name,
        'mode': APPROVE, 'can_submit': not blockers, 'projection': meaning, 'blockers': blockers,
        'review_payload': request, 'fact_review_completed': complete, 'frozen_sources': frozen,
        'existing_candidate': common.ref(settings,target['path']) if target else None,
        'business_ref': common.ref(settings, business['path']), 'business_receipt_ref': common.ref(settings, business['receipt_path'])}
    bundle['preview_sha256'] = digest(bundle)
    context = review_commands.issue(settings, 'speaker', identity, user_id, business_id=business_id, confirmation=bundle)
    return {k: bundle[k] for k in ('schema_version', 'mode', 'can_submit', 'projection', 'blockers', 'preview_sha256')} | {'review_context': context}


def validate_decision(command):
    bundle = command['context'].get('confirmation')
    payload = read(command['directory']/'intent.json')['intent']['payload'] if command['saved'] else command['intent']
    if (not bundle or bundle.get('schema_version') != VERSION or not bundle.get('can_submit')
            or digest({k:v for k,v in bundle.items() if k != 'preview_sha256'}) != bundle.get('preview_sha256')
            or payload.get('confirmation') != APPROVE or payload.get('preview_sha256') != bundle['preview_sha256']):
        raise fail('SPEAKER_CONFIRMATION_REQUIRED', '请完成重点核对，并明确确认当前资料与档案批准。')
    return bundle


def execute(settings, command, reviewer):
    from .speaker_gateway import _latest_intake_dir
    from .persona_authority import resolve_persona_authority
    from .case_library_access import principal
    from . import persona_review_gateway
    from speaker_fact_review_v1 import review_speaker_facts
    from .speaker_task_service import mark_speaker_task_reviewed
    bundle = validate_decision(command);context = command['context']
    bid = bundle['business_id'];sid = bundle['speaker_id']
    if principal(settings, context['actor']['user_id']) != context['actor']:
        raise fail('REVIEW_ACTOR_MISMATCH', '当前人物审核身份已失效。')
    if command['result'] is not None:
        result = command['result']
        if (result.get('schema_version') != VERSION or result.get('preview_sha256') != bundle['preview_sha256']
                or result.get('operation_id') != context['operation_id']):
            raise fail('REVIEW_REPLAY_CONFLICT', '原操作结果与本次确认不一致。')
        verify_approval(settings, result, reviewer, context['operation_id'])
        return result
    directory = _latest_intake_dir(settings, bid, sid)
    business = resolve_persona_authority(settings, bid, 'business').current
    if not directory or directory.name != bundle['intake_id'] or not business or common.ref(settings, business['path']) != bundle['business_ref']:
        raise fail('SPEAKER_CONFIRMATION_STALE', '本人来源或当前客户版本已变化，需要重新核对。')
    for path, sha in bundle['frozen_sources'].items():common.check_ref(settings, {'path': path, 'sha256': sha})
    common.check_ref(settings, bundle['business_ref']);common.check_ref(settings, bundle['business_receipt_ref'])
    target_file = command['directory']/'speaker_approval_target.json'
    if not target_file.exists():
        if bundle['fact_review_completed']:
            current_target=resolve_persona_authority(settings,sid,'speaker').review_candidate
            if not current_target or common.ref(settings,current_target['path']) != bundle['existing_candidate']:
                raise fail('SPEAKER_CONFIRMATION_STALE','待批准人物档案已变化，需要重新核对。')
        if not bundle['fact_review_completed']:
            reviewed = review_speaker_facts(request=bundle['review_payload'], pipeline_root=settings.pipeline_root)
            if reviewed['status'] != 'completed_persona_review_required':
                raise fail('PERSONA_APPROVAL_BLOCKED', '人物核对已保存，但资料仍不满足档案批准条件。')
        target = resolve_persona_authority(settings, sid, 'speaker').review_candidate
        if not target or projection(target['artifact']) != bundle['projection']:
            raise fail('SPEAKER_CONFIRMATION_STALE', '生成的本人档案与已确认范围不一致；核对记录已保留。')
        write_once(target_file, {'schema_version': VERSION, 'operation_id': context['operation_id'], 'actor': context['actor'],
            'preview_sha256': bundle['preview_sha256'], 'intent_ref': common.ref(settings, command['directory']/'intent.json'),
            'fact_review_ref': common.ref(settings, directory/'speaker_fact_review_v1.json'),
            'reviewed_candidates_ref': common.ref(settings, directory/'reviewed_speaker_fact_candidates_v1.json'),
            'business_ref': bundle['business_ref'], 'business_receipt_ref': bundle['business_receipt_ref'],
            'snapshot': review_commands.snapshot(settings, 'speaker', sid, business_id=bid)})
    target = read(target_file)
    if (target['schema_version'] != VERSION or target['operation_id'] != context['operation_id']
            or target['actor'] != context['actor'] or target['preview_sha256'] != bundle['preview_sha256']):
        raise fail('REVIEW_COMMIT_CONFLICT', '原人物批准提交证明不一致。')
    for key in ('intent_ref', 'fact_review_ref', 'reviewed_candidates_ref', 'business_ref', 'business_receipt_ref'):
        common.check_ref(settings, target[key])
    derived = {**command, 'context': {**context, 'snapshot': target['snapshot']}}
    decision_ref = common.ref(settings, target_file)
    if principal(settings, context['actor']['user_id']) != context['actor']:
        raise fail('REVIEW_ACTOR_MISMATCH', '当前人物审核身份已失效。')
    persona_review_gateway.approve(settings, derived, 'speaker', sid, bid, reviewer,
        'Human explicitly confirmed the reviewed Speaker profile and expression boundaries.',
        decision_metadata={'decision_artifact_ref': decision_ref})
    path = settings.pipeline_root/target['snapshot']['artifact']
    result = {'schema_version': VERSION, 'operation_id': context['operation_id'], 'preview_sha256': bundle['preview_sha256'],
        'completion': 'speaker_approved', 'speaker_id': sid, 'decision_ref': decision_ref,
        'fact_review_ref': target['fact_review_ref'], 'persona_ref': common.ref(settings, path),
        'approval_receipt_ref': common.ref(settings, path.parent/'approval_receipt.json')}
    verify_approval(settings, result, reviewer, context['operation_id'])
    mark_speaker_task_reviewed(settings.database_path, sid)
    return review_commands.finish(command, result)


def verify_approval(settings, result, reviewer, operation_id):
    receipt = read(common.check_ref(settings, result['approval_receipt_ref']))
    persona = read(common.check_ref(settings, result['persona_ref']))
    decision = read(common.check_ref(settings, result['decision_ref']))
    common.check_ref(settings, result['fact_review_ref'])
    if (receipt.get('human_gate') is not True or receipt.get('reviewer') != reviewer
            or receipt.get('persona_sha256_after_approval') != result['persona_ref']['sha256']
            or receipt.get('review_decision_metadata') != {'decision_artifact_ref': result['decision_ref']}
            or persona.get('approval', {}).get('human_gate') is not True or decision.get('operation_id') != operation_id):
        raise fail('REVIEW_COMMIT_CONFLICT', '独立人物审批收据与原明确确认不一致。')
