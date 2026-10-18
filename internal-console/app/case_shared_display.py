"""SHA-bound, append-only display permission; never Case or production approval."""
from __future__ import annotations

import importlib.util
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

from .canonical_gateway import (
    CanonicalOperationError, _read_json, _sha256, case_cover_path,
)
from .case_classification import classification_summary
from .case_library_access import reviewer_authorization, reviewer_lock, _owner

VERSION = 'case-shared-display-v1.0'
FIELDS = ('title','industry','video_type','duration_seconds','structure_summary')
KEYS = {'schema_version','case_id','audience','sequence','parent_sha256','action','at','actor',
        'case_sha256','approval_receipt_sha256','allowed_fields','display','sources','cover_clearance'}
JOINT_VERSION = 'case-shared-display-v1.1'
PREVIEW_VERSION = 'case-shared-display-preview-v1.0'
DECISION_VERSION = 'case-human-display-decision-v1.0'


def _share_error(message, code='CASE_SHARE_PREVIEW_STALE'):
    return CanonicalOperationError(code, message, '请重新核对展示预览；已经保存的收录记录会保留。')


def _grant_ref(authorization):
    return {k:authorization[k] for k in ('namespace','user_id','event_id','event_sha256')}


def _policy(settings):
    # A changed validator invalidates an uncommitted display authorization.
    from human_review_operations_v1 import digest
    return {'version': PREVIEW_VERSION, 'validator_sha256': digest({
        'display': _sha256(Path(__file__)),
        'privacy': _sha256(settings.pipeline_root/'scripts/privacy_projection_v1.py'),
        'source': _sha256(settings.pipeline_root/'scripts/approve_case_v1.py')})}


def _preview_sources(settings, candidate):
    from case_evidence_revision_v1 import source_refs, check_ref
    from .path_safety import resolve_within
    refs = source_refs(settings.pipeline_root, candidate)
    for ref in refs.values():
        check_ref(settings.repo_root, ref)
    case = _read_json(candidate)
    for name in ('source_acquisition_ref', 'source_metadata_ref'):
        ref = case['source_provenance'][name]
        path = resolve_within(settings.pipeline_root, ref['path'])
        if _sha256(path) != ref['sha256']:
            raise _share_error('原始来源已变化，不能签发共享预览。')
        refs[name] = {'path': str(path.relative_to(settings.repo_root)), 'sha256': _sha256(path)}
    return refs


def share_preview(settings, case_id, actor, *, title=None, structure_summary=None):
    try:
        return _build_share_preview(settings,case_id,actor,title=title,structure_summary=structure_summary)
    except CanonicalOperationError:
        raise
    except (FileNotFoundError,ValueError,KeyError,TypeError,RuntimeError) as exc:
        raise _share_error('来源、隐私、证明或审核范围尚未完整核对，请恢复来源或重新分析。') from exc


def _build_share_preview(settings, case_id, actor, *, title=None, structure_summary=None):
    """Read-only, source-bound proposal. Only a signed final command authorizes it.

    Raw narration, claims, proof and model descriptions are never default display
    text. The structural default describes only the validated timeline shape.
    Edited text remains a source-bound Human display proposal, not Customer Truth.
    """
    from case_evidence_revision_v1 import resolve_target, review_scope
    from approve_case_v1 import validate_source_provenance
    from privacy_projection_v1 import validate_case_privacy_gate, scan_sensitive_values
    from human_review_operations_v1 import digest
    authorization = reviewer_authorization(settings, actor)
    from .review_commands import snapshot, CASE_VERSION
    target_snapshot = snapshot(settings, 'case', case_id, version=CASE_VERSION)
    target = resolve_target(settings.pipeline_root, case_id, target_snapshot['attempt_id'])
    scope = review_scope(settings.pipeline_root, case_id, target_snapshot['attempt_id'])
    case = _read_json(target.candidate)
    if (case.get('lifecycle') or {}).get('approved') or scope['summary']['blocked']:
        raise _share_error('尚有来源、修订或风险问题需要处理。')
    refs = _preview_sources(settings, target.candidate)
    _, errors = validate_source_provenance(case)
    if errors:
        raise _share_error('案例来源尚未完整核对，不能批准或共享。')
    validate_case_privacy_gate(case)
    privacy_path = settings.repo_root/refs['privacy_projection_v1']['path']
    if case['privacy_gate'].get('source_projection_sha256') != _sha256(privacy_path):
        raise _share_error('隐私校验证据已变化。')
    understanding = (case.get('storyboard') or {}).get('video_understanding') or {}
    proofs = understanding.get('verified_proofs')
    if (not isinstance(proofs, list) or case.get('quality', {}).get('verified_proof_count') != len(proofs)
            or (not proofs and any(c.get('status') in {'proof','verified_proof','observed_proof','proven'} for c in understanding.get('claims', [])))):
        raise _share_error('案例的证明边界尚未完整核对。')
    metadata = _read_json(settings.repo_root/refs['source_metadata_ref']['path'])
    default_title = str(metadata.get('desc') or metadata.get('title') or '').strip()[:120]
    shots = (case.get('storyboard') or {}).get('shots') or []
    default_summary = f'通过 {len(shots)} 个镜头呈现视频结构，供创作拆解参考。' if shots else ''
    display_title = default_title if title is None else title.strip()
    summary = default_summary if structure_summary is None else structure_summary.strip()
    # No offline semantic oracle can establish a new business assertion. Permit
    # source excerpts and the deterministic structural description only; free
    # paraphrases require a separately supported source-backed review path.
    if (display_title and display_title not in default_title) or (summary and summary not in default_summary):
        raise _share_error('展示修改必须取自当前来源标题或安全结构摘要；不能新增未经证明的主张。')
    classification = classification_summary(settings, case_id, attempt_id=target_snapshot['attempt_id'])
    industry = classification.get('industry') if classification.get('status') == 'confirmed' else None
    classification_path = target.attempt_root/'case_classification_review_v1.json'
    classification_ref = None
    if classification_path.exists():
        record = _read_json(classification_path)
        if record.get('confirmed_case_sha256') != _sha256(target.candidate):
            raise _share_error('分类确认与当前候选不一致。')
        classification_ref = {'path':str(classification_path.relative_to(settings.repo_root)), 'sha256':_sha256(classification_path)}
    duration = (case.get('identity') or {}).get('duration_seconds')
    if isinstance(duration, bool) or not isinstance(duration, (int,float)) or not math.isfinite(duration) or duration <= 0:
        duration = None
    elif float(duration).is_integer():
        duration = int(duration)  # Canonical JSON survives the browser's number roundtrip.
    display = {'title':display_title, 'industry':industry, 'video_type':None,
               'duration_seconds':duration, 'structure_summary':summary}
    # Missing display text is an independent display deficiency. An unavailable
    # source, invalid scope, signature or IO failure must never select this mode.
    blocker = {'code':'CASE_DISPLAY_TITLE_REQUIRED', 'message':'缺少可核对的展示标题，当前只能批准入库。'} if not display_title else None
    if display_title:
        _validate_display(display)
    if scan_sensitive_values(display):
        raise _share_error('展示内容含有敏感信息，请先修正预览。')
    history = _history(settings, case_id)
    candidate_ref = {'path':str(target.candidate.relative_to(settings.pipeline_root)), 'sha256':_sha256(target.candidate)}
    sources = {
        'title':{'kind':'human_confirmed_source_display_title', 'ref':refs['source_metadata_ref'], 'candidate_ref':candidate_ref},
        'industry':{'kind':'classification_confirmation' if industry else 'not_confirmed', 'ref':classification_ref},
        'video_type':{'kind':'no_formal_taxonomy'},
        'duration_seconds':{'kind':'validated_media_identity', 'candidate_ref':candidate_ref, 'evidence_refs':refs},
        'structure_summary':{'kind':'human_reviewed_safe_structure', 'candidate_ref':candidate_ref,
            'privacy_ref':refs['privacy_projection_v1'], 'storyboard_ref':refs['storyboard_v1']}}
    preview = {'schema_version':PREVIEW_VERSION, 'case_id':case_id, 'attempt_id':target_snapshot['attempt_id'],
        'candidate_ref':candidate_ref, 'evidence_sha256':{k:r['sha256'] for k,r in refs.items()}, 'revision_ref':target.revision_ref,
        'revision_validation_ref':target.validation_ref, 'scope_sha256':scope['scope_sha256'],
        'allowed_fields':list(FIELDS), 'display':display, 'sources':sources,
        'cover':{'state':'placeholder', 'cover_ref':None, 'clearance_ref':None},
        'expected_publication_head_sha256':history[-1][1] if history else None,
        'reviewer_grant_ref':_grant_ref(authorization), 'display_policy_ref':_policy(settings)}
    return {'mode':'approve_only' if blocker else 'approve_and_share', 'preview':preview,
        'preview_sha256':digest(preview), 'blocker':blocker, 'blocker_sha256':digest(blocker) if blocker else None}


def validate_preview(settings, bundle, actor, *, committed=False):
    """Revalidate sources and policy before each stage; never trust client flags."""
    from human_review_operations_v1 import digest
    from .path_safety import resolve_within
    preview = bundle['preview']
    if (digest(preview) != bundle['preview_sha256'] or preview['schema_version'] != PREVIEW_VERSION
            or preview['reviewer_grant_ref'] != _grant_ref(reviewer_authorization(settings, actor))
            or preview['display_policy_ref'] != _policy(settings)
            or preview['cover'] != {'state':'placeholder','cover_ref':None,'clearance_ref':None}):
        raise _share_error('展示预览、策略或原审核授权已变化。')
    refs=preview['sources']['duration_seconds']['evidence_refs']
    if preview['evidence_sha256']!={k:r['sha256'] for k,r in refs.items()}:
        raise _share_error('展示来源摘要不一致。')
    for ref in refs.values():
        path = resolve_within(settings.repo_root, ref['path'])
        if _sha256(path) != ref['sha256']:
            raise _share_error('展示来源已变化。')
    classification = preview['sources']['industry'].get('ref')
    if classification and _sha256(resolve_within(settings.repo_root, classification['path'])) != classification['sha256']:
        raise _share_error('展示分类已变化。')
    candidate = resolve_within(settings.pipeline_root, preview['candidate_ref']['path'])
    if _sha256(candidate) != preview['candidate_ref']['sha256']:
        raise _share_error('原审核候选已变化。')
    if committed:
        annotation=settings.pipeline_root/'data/case_governance/cases'/preview['case_id']/'case_industry_annotation_v1.json'
        _,case_sha,_=_base(settings,preview['case_id'])
        industry,_=_confirmed_industry(settings,preview['case_id'],case_sha)
        if annotation.exists() or industry!=preview['display']['industry']:
            raise _share_error('批准后的展示分类来源已变化，需要重新核对。')
    else:
        current = share_preview(settings, preview['case_id'], actor,
            title=preview['display']['title'], structure_summary=preview['display']['structure_summary'])
        if current != bundle:
            raise _share_error('当前展示预览已变化。')
    return preview


def validate_sharing_decision(settings, command, submission, *, committed=False):
    from human_review_operations_v1 import digest
    context = command['context']
    bundle = context.get('sharing')
    if not bundle:
        raise _share_error('当前没有可核对的共享预览，不能执行新版批准。')
    keys = {'schema_version','decision','preview_sha256','preview','blocker_sha256','origin'}
    expected = {'schema_version':DECISION_VERSION,
        'decision':'publish_exact_preview' if bundle['mode']=='approve_and_share' else 'approve_only',
        'preview_sha256':bundle['preview_sha256'], 'preview':bundle['preview'],
        'blocker_sha256':bundle['blocker_sha256'], 'origin':'human_joint_final_confirmation'}
    if not isinstance(submission, dict) or set(submission)!=keys or digest(submission)!=digest(expected):
        raise _share_error('请通过最终确认明确授权当前准确的展示内容。','CASE_SHARE_DECISION_REQUIRED')
    target=context['snapshot']
    if (target.get('sharing_mode')!=bundle['mode'] or target.get('share_preview_sha256')!=digest(bundle['preview'])
            or target.get('share_blocker_sha256')!=bundle['blocker_sha256']
            or target.get('reviewer_grant_ref')!=bundle['preview']['reviewer_grant_ref']
            or bundle['preview']['case_id']!=context['identity'] or bundle['preview']['attempt_id']!=target['attempt_id']
            or bundle['preview']['candidate_ref']!={'path':target['artifact'],'sha256':target['artifact_sha256']}
            or bundle['preview']['scope_sha256']!=target['scope_sha256']
            or bundle['preview']['revision_ref']!=target['revision_ref']
            or bundle['preview']['revision_validation_ref']!=target['revision_validation_ref']):
        raise _share_error('共享授权与原审核操作不一致。')
    return validate_preview(settings, bundle, context['actor'], committed=committed)


def _validate_joint_record(settings, record):
    """Version-specific reader validates the immutable decision/Approval linkage."""
    from human_review_operations_v1 import digest
    from .path_safety import resolve_within
    decision=record['human_display_decision']
    keys={'schema_version','decision','origin','operation_id','intent_ref','preview_sha256',
          'case_id','attempt_id','candidate_ref','evidence_sha256','revision_ref','revision_validation_ref',
          'scope_sha256','actor','decided_at'}
    if set(decision)!=keys or decision['schema_version']!=DECISION_VERSION:
        raise _blocked()
    saved_path=resolve_within(settings.pipeline_root,decision['intent_ref']['path'])
    if _sha256(saved_path)!=decision['intent_ref']['sha256']:
        raise _blocked()
    saved=_read_json(saved_path);context=saved['context'];bundle=context['sharing'];preview=bundle['preview']
    expected_path=settings.pipeline_root/'data/review_operations/case'/record['case_id']/context['operation_id']/'intent.json'
    if (saved_path!=expected_path or context['version']!='human-review-command-v1.2'
            or context['identity']!=record['case_id'] or context['operation_id']!=decision['operation_id']
            or context['actor']!={k:record['actor'][k] for k in ('namespace','user_id')}
            or preview['reviewer_grant_ref']!=_grant_ref(record['actor']) or bundle['mode']!='approve_and_share'
            or bundle['preview_sha256']!=digest(preview) or decision['preview_sha256']!=digest(preview)
            or saved['intent']['payload']['sharing_decision']!={
                'schema_version':DECISION_VERSION,'decision':'publish_exact_preview','preview_sha256':digest(preview),
                'preview':preview,'blocker_sha256':None,'origin':'human_joint_final_confirmation'}
            or record['display']!=preview['display'] or record['sources']!=preview['sources']
            or record['allowed_fields']!=preview['allowed_fields'] or record['cover_clearance'] is not None
            or decision['actor']!=record['actor'] or decision['decided_at']!=saved['at']
            or decision['origin']!='human_joint_final_confirmation' or decision['decision']!='publish_exact_preview'):
        raise _blocked()
    for key in ('case_id','attempt_id','candidate_ref','evidence_sha256','revision_ref','revision_validation_ref','scope_sha256'):
        if decision[key]!=preview[key]: raise _blocked()
    canonical=settings.pipeline_root/'data/cases'/record['case_id']
    binding=_read_json(canonical/'console_review_command_v1.json')
    if (binding['context']!=context or binding['intent_ref']!=decision['intent_ref']
            or binding['artifacts']['case_v1.json']['sha256']!=record['case_sha256']
            or binding['artifacts']['approval_receipt.json']['sha256']!=record['approval_receipt_sha256']):
        raise _blocked()
    return preview


def publish_joint(settings, command):
    """Stage B only. Caller holds Case lock; never calls the Approval writer."""
    from . import review_commands
    from human_review_operations_v1 import read, write_once
    context=command['context'];case_id=context['identity'];actor=context['actor']
    with reviewer_lock(settings,actor):
        authorization=reviewer_authorization(settings,actor)
        saved=review_commands._case_intent(settings,command)
        bundle=context['sharing'];preview=bundle['preview']
        if _grant_ref(authorization)!=preview['reviewer_grant_ref']:
            raise _share_error('原审核授权已失效，请重新核对展示内容。')
        case,case_sha,receipt_sha=_base(settings,case_id)
        history=_history(settings,case_id)
        existing=[(v,h) for v,h in history if v.get('human_display_decision',{}).get('operation_id')==context['operation_id']]
        if len(existing)>1: raise _blocked()
        if existing:
            value,receipt_hash=existing[0]
            _validate_joint_record(settings,value)
            if (value['human_display_decision']['intent_ref']!=review_commands._ref(settings,command['directory']/'intent.json')
                    or value['case_sha256']!=case_sha or value['approval_receipt_sha256']!=receipt_sha):
                raise _blocked()
            # A later withdrawal/publication is authoritative. This branch never
            # republishes, even if result persistence was interrupted originally.
            return {'path':str((_root(settings,case_id)/f"receipt_{value['sequence']:06}.json").relative_to(settings.pipeline_root)),
                    'sha256':receipt_hash}
        validate_sharing_decision(settings,command,saved['intent']['payload'].get('sharing_decision'),committed=True)
        parent=history[-1][1] if history else None
        if parent!=preview['expected_publication_head_sha256']:
            raise _share_error('共享展示状态已变化，需要重新核对。')
        receipt=read(settings.pipeline_root/'data/cases'/case_id/'approval_receipt.json')
        quality=(case.get('approval') or {}).get('human_quality_decision') or {}
        if (receipt['case_sha256_before_approval']!=preview['candidate_ref']['sha256']
                or quality.get('operation_id')!=context['operation_id']
                or (case.get('analysis_lineage') or {}).get('attempt_id')!=preview['attempt_id']):
            raise _share_error('正式批准与原展示预览不一致。')
        decision={k:preview[k] for k in ('case_id','attempt_id','candidate_ref','evidence_sha256',
            'revision_ref','revision_validation_ref','scope_sha256')}
        decision.update(schema_version=DECISION_VERSION,decision='publish_exact_preview',origin='human_joint_final_confirmation',
            operation_id=context['operation_id'],intent_ref=review_commands._ref(settings,command['directory']/'intent.json'),
            preview_sha256=bundle['preview_sha256'],actor=authorization,decided_at=command['at'])
        record={'schema_version':JOINT_VERSION,'case_id':case_id,'audience':'eligible_platform_users',
            'sequence':len(history)+1,'parent_sha256':parent,'action':'publish','at':datetime.now(timezone.utc).isoformat(),
            'actor':authorization,'case_sha256':case_sha,'approval_receipt_sha256':receipt_sha,
            'allowed_fields':preview['allowed_fields'],'display':preview['display'],'sources':preview['sources'],
            'cover_clearance':None,'human_display_decision':decision}
        _validate_joint_record(settings,record)
        path=_root(settings,case_id)/f"receipt_{record['sequence']:06}.json"
        write_once(path,record)
        return review_commands._ref(settings,path)


def _blocked(message='共享展示记录无法核对。'):
    return CanonicalOperationError('CASE_DISPLAY_CONFLICT',message,'请刷新案例并重新核对。')


def _root(settings,case_id):
    if not re.fullmatch(r'\d{10,24}',str(case_id)):
        raise _blocked()
    return settings.pipeline_root/'data/case_governance/cases'/case_id/'shared_display'


def _base(settings,case_id):
    _root(settings,case_id)  # Reject identifiers before touching filesystem paths.
    path = settings.pipeline_root/'data/cases'/case_id/'case_v1.json'
    receipt_path = path.parent/'approval_receipt.json'
    case, receipt = _read_json(path), _read_json(receipt_path)
    case_sha, receipt_sha = _sha256(path), _sha256(receipt_path)
    lifecycle = case.get('lifecycle') or {}
    if (case.get('case_id') != case_id or lifecycle.get('status') != 'approved' or lifecycle.get('approved') is not True
            or receipt.get('case_id') != case_id or receipt.get('human_gate') is not True
            or receipt.get('decision') != 'approved' or receipt.get('case_sha256_after_approval') != case_sha):
        raise _blocked('案例批准与收据尚未完整核对。')
    # Preserve the existing full approved-artifact validator and partial recovery boundary.
    from .canonical_gateway import _validate_approved_case_artifacts, _partial_approval_state
    _validate_approved_case_artifacts(path,expected_case_id=case_id,
        expected_attempt_id=str((case.get('analysis_lineage') or {}).get('attempt_id') or ''),
        expected_reviewer=str(receipt.get('reviewer') or ''))
    if _partial_approval_state(settings,case_id,case) is not None:
        raise _blocked('案例需要先恢复正式批准。')
    return case, case_sha, receipt_sha


def _history(settings,case_id):
    previous = None
    records = []
    for sequence,path in enumerate(sorted(_root(settings,case_id).glob('receipt_*.json')),1):
        value = _read_json(path)
        joint = value.get('schema_version') == JOINT_VERSION
        if (path.name != f'receipt_{sequence:06}.json' or set(value) != (KEYS | {'human_display_decision'} if joint else KEYS)
                or value['schema_version'] not in {VERSION,JOINT_VERSION} or value['case_id'] != case_id
                or value['audience'] != 'eligible_platform_users'
                or value['sequence'] != sequence or value['parent_sha256'] != previous
                or value['action'] not in {'publish','withdraw'}
                or not re.fullmatch(r'[a-f0-9]{64}',str(value['case_sha256']))
                or not re.fullmatch(r'[a-f0-9]{64}',str(value['approval_receipt_sha256']))
                or set(value['actor']) != {'namespace','user_id','capability','event_id','event_sha256'}
                or value['actor']['capability'] != 'case_library_reviewer'):
            raise _blocked()
        if not _owner(str(settings.pipeline_root)).validate_authorization_evidence(settings.database_path,value['actor']):
            raise _blocked()
        if value['action'] == 'publish':
            if (value['allowed_fields'] != list(FIELDS) or set(value['display']) != set(FIELDS)
                    or set(value['sources']) != set(FIELDS)):
                raise _blocked()
            _validate_display(value['display'])
            if joint:
                _validate_joint_record(settings, value)
        elif value['allowed_fields'] or value['display'] or value['sources'] or value['cover_clearance']:
            raise _blocked()
        elif joint:
            raise _blocked()  # Existing explicit withdraw uses its frozen v1.0 contract.
        previous = _sha256(path)
        records.append((value,previous))
    return records


def _validate_display(display):
    if not isinstance(display['title'],str) or not display['title'].strip() or len(display['title']) > 120:
        raise _blocked('请提供已人工核对的展示标题。')
    if display['industry'] is not None and (not isinstance(display['industry'],str) or len(display['industry']) > 30):
        raise _blocked()
    if display['video_type'] is not None:  # No formal type taxonomy exists in the current contract.
        raise _blocked('当前尚无正式视频类型合同。')
    duration=display['duration_seconds']
    if duration is not None and (isinstance(duration,bool) or not isinstance(duration,(int,float)) or not math.isfinite(duration) or duration <= 0):
        raise _blocked()
    if not isinstance(display['structure_summary'],str) or len(display['structure_summary']) > 1000:
        raise _blocked()
    text=display['title']+' '+display['structure_summary']
    if re.search(r'(?<!\d)1[3-9]\d{9}(?!\d)|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',text):
        raise _blocked('共享展示中不能包含个人联系方式。')


def _confirmed_industry(settings,case_id,case_sha):
    annotation_path=settings.pipeline_root/'data/case_governance/cases'/case_id/'case_industry_annotation_v1.json'
    if annotation_path.is_file():
        from .canonical_gateway import get_case_detail
        detail=get_case_detail(settings,case_id)
        annotation=detail.get('industry_annotation')
        if annotation:
            return annotation['industry'],{'kind':'industry_annotation','sha256':_sha256(annotation_path)}
    summary=classification_summary(settings,case_id)
    if summary['status']=='confirmed' and summary.get('industry'):
        case_path=settings.pipeline_root/'data/cases'/case_id/'case_v1.json'
        attempt_id=(_read_json(case_path).get('analysis_lineage') or {}).get('attempt_id')
        path=settings.pipeline_root/'data/case_analysis_attempts'/case_id/str(attempt_id)/'case_classification_review_v1.json'
        record=_read_json(path)
        receipt=_read_json(case_path.parent/'approval_receipt.json')
        if record.get('confirmed_case_sha256')!=receipt.get('case_sha256_before_approval'):
            raise _blocked('分类确认与原批准候选无法绑定。')
        return summary['industry'],{'kind':'classification_confirmation','sha256':_sha256(path)}
    return None,{'kind':'not_confirmed','case_sha256':case_sha}


def publication_context(settings,case_id):
    try:
        _,case_sha,receipt_sha=_base(settings,case_id)
        history=_history(settings,case_id)
        return {'available':True,'approved_case_sha256':case_sha,'approval_receipt_sha256':receipt_sha,
                'cover_available':case_cover_path(settings,case_id) is not None,
                'display_receipt_sha256':history[-1][1] if history else None,
                'published':bool(history and history[-1][0]['action']=='publish' and shared_projection(settings,case_id))}
    except (CanonicalOperationError,OSError,ValueError,TypeError,KeyError) as exc:
        return {'available':False,'published':False,'blocker':{
            'code':getattr(exc,'code','CASE_DISPLAY_EVIDENCE_UNAVAILABLE'),
            'message':'案例的来源、隐私或批准收据证据尚未完整通过共享校验。',
            'next_action':'请由指定审核或运维人员核对原来源与批准证据。保留历史审核；补证完成前不能共享。'}}


def change_publication(settings,case_id,*,actor,action,title='',structure_summary='',cover_evidence=None,
                       approved_case_sha256,approval_receipt_sha256,expected_display_receipt_sha256=None):
    if action not in {'publish','withdraw'}: raise _blocked()
    with reviewer_lock(settings,actor):
        authorization=reviewer_authorization(settings,actor)
        case,case_sha,receipt_sha=_base(settings,case_id)
        history=_history(settings,case_id)
        parent=history[-1][1] if history else None
        if case_sha!=approved_case_sha256 or receipt_sha!=approval_receipt_sha256 or parent!=expected_display_receipt_sha256:
            raise _blocked('案例或共享决定已经变化。')
        display,sources,clearance={},{},None
        if action=='publish':
            industry,industry_source=_confirmed_industry(settings,case_id,case_sha)
            duration=(case.get('identity') or {}).get('duration_seconds')
            if isinstance(duration,bool) or not isinstance(duration,(int,float)) or not math.isfinite(duration) or duration<=0:
                duration=None
            display={'title':title.strip(),'industry':industry,'video_type':None,
                     'duration_seconds':duration,'structure_summary':structure_summary.strip()}
            _validate_display(display)
            spec=importlib.util.spec_from_file_location('case_display_privacy',settings.pipeline_root/'scripts/privacy_projection_v1.py')
            privacy=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(privacy)
            if privacy.scan_sensitive_values(display):
                raise _blocked('展示内容需要先处理隐私信息。')
            sources={'title':{'kind':'human_confirmed_display_title','case_sha256':case_sha},
                     'industry':industry_source,'video_type':{'kind':'no_formal_taxonomy'},
                     'duration_seconds':{'kind':'approved_case_identity','case_sha256':case_sha},
                     'structure_summary':{'kind':'human_reviewed_structural_reference','case_sha256':case_sha}}
            if cover_evidence is not None:
                path=case_cover_path(settings,case_id)
                provenance=case.get('source_provenance') or {}
                source_sha=provenance.get('recorded_source_media_sha256') or ((case.get('source_evidence') or {}).get('video') or {}).get('sha256')
                if (path is None or not re.fullmatch(r'[a-f0-9]{64}',str(source_sha))
                        or set(cover_evidence)!= {'reference','statement','display_rights_confirmed'}
                        or cover_evidence['display_rights_confirmed'] is not True
                        or not str(cover_evidence['reference']).strip() or not str(cover_evidence['statement']).strip()):
                    raise _blocked('封面需要独立、明确的展示权利证据。')
                clearance={'case_id':case_id,'case_sha256':case_sha,'source_media_sha256':source_sha,
                           'cover_sha256':_sha256(path),'scope':'eligible_platform_users_display_only',
                           'evidence':cover_evidence,'production_media_rights_granted':False}
        record={'schema_version':VERSION,'case_id':case_id,'audience':'eligible_platform_users','sequence':len(history)+1,
                'parent_sha256':parent,'action':action,'at':datetime.now(timezone.utc).isoformat(),
                'actor':authorization,'case_sha256':case_sha,'approval_receipt_sha256':receipt_sha,
                'allowed_fields':list(FIELDS) if action=='publish' else [],'display':display,'sources':sources,
                'cover_clearance':clearance}
        root=_root(settings,case_id)
        root.mkdir(parents=True,exist_ok=True)
        target=root/f"receipt_{record['sequence']:06}.json"
        from .canonical_gateway import _write_atomic
        # The caller holds the existing Case authority lock; no old receipt is replaced.
        if target.exists(): raise _blocked()
        _write_atomic(target,record)
        return publication_context(settings,case_id)


def shared_projection(settings,case_id):
    try:
        _,case_sha,receipt_sha=_base(settings,case_id)
        history=_history(settings,case_id)
        if not history: return None
        record,record_sha=history[-1]
        if record['action']!='publish' or record['case_sha256']!=case_sha or record['approval_receipt_sha256']!=receipt_sha:
            return None
        industry,source=_confirmed_industry(settings,case_id,case_sha)
        if record['display']['industry']!=industry or (record['schema_version']==VERSION and record['sources']['industry']!=source):
            return None
        return {'case_id':case_id,**record['display'],'status':'approved','visibility':'shared',
                'published_at':record['at'],'display_revision':record_sha,
                'cover_url':f'/api/case-library/{case_id}/cover' if shared_cover_path(settings,case_id,record) else None,
                'media_rights':{'production_authorized':False},'review':{'can_review':False,'approved':True}}
    except (CanonicalOperationError,OSError,ValueError,TypeError,KeyError):
        return None


def shared_cover_path(settings,case_id,record=None):
    try:
        case,case_sha,receipt_sha=_base(settings,case_id)
        if record is None:
            history=_history(settings,case_id)
            if not history: return None
            record=history[-1][0]
        clearance=record.get('cover_clearance')
        if (record['action']!='publish' or record['case_sha256']!=case_sha
                or record['approval_receipt_sha256']!=receipt_sha or not clearance
                or clearance.get('case_id')!=case_id or clearance.get('case_sha256')!=case_sha
                or clearance.get('source_media_sha256')!=((case.get('source_provenance') or {}).get('recorded_source_media_sha256')
                    or ((case.get('source_evidence') or {}).get('video') or {}).get('sha256'))
                or clearance.get('scope')!='eligible_platform_users_display_only'
                or clearance.get('production_media_rights_granted') is not False
                or clearance.get('evidence',{}).get('display_rights_confirmed') is not True):
            return None
        path=case_cover_path(settings,case_id)
        return path if path and _sha256(path)==clearance['cover_sha256'] else None
    except (CanonicalOperationError,OSError,ValueError,TypeError,KeyError):
        return None


def shared_cases(settings):
    rows=[]
    for root in (settings.pipeline_root/'data/case_governance/cases').glob('*/shared_display'):
        row=shared_projection(settings,root.parent.name)
        if row: rows.append(row)
    return sorted(rows,key=lambda row:(row['published_at'],row['case_id']),reverse=True)


def sharing_status(settings, case_id):
    """Public-state wording only, no private operation, actor or Task disclosure."""
    if shared_projection(settings,case_id):
        return {'sharing_state':'approved_shared','sharing_label':'已收录并共享'}
    result={'sharing_state':'approved_only','sharing_label':'已收录，共享尚未完成',
        'sharing_next_action':'请由指定审核人从共享展示管理核对允许展示的内容。'}
    try:
        history=_history(settings,case_id)
        if history and history[-1][0]['action']=='withdraw':
            return {'sharing_state':'approved_withdrawn','sharing_label':'已收录，已撤回共享',
                'sharing_next_action':'共享已撤回，原收录记录保留。如需再次共享，请重新核对并明确授权展示内容。'}
        canonical=settings.pipeline_root/'data/cases'/case_id
        binding_path=canonical/'console_review_command_v1.json'
        if not binding_path.exists():return result
        from .path_safety import resolve_within
        binding=_read_json(binding_path);context=binding['context']
        intent_path=resolve_within(settings.pipeline_root,binding['intent_ref']['path'])
        if (context['version']!='human-review-command-v1.2' or context['identity']!=case_id
                or _sha256(intent_path)!=binding['intent_ref']['sha256']):return result
        terminal=intent_path.with_name('result.json')
        if not terminal.exists():
            result['sharing_next_action']='原提交审核人可继续原操作完成共享；无需重新批准案例。'
            return result
        value=_read_json(terminal)
        if (value.get('schema_version')=='case-review-share-result-v1.0'
                and value.get('operation_id')==context['operation_id']
                and value.get('intent_ref')==binding['intent_ref']
                and value.get('approved_case_ref',{}).get('sha256')==_sha256(canonical/'case_v1.json')
                and value.get('approval_receipt_ref',{}).get('sha256')==_sha256(canonical/'approval_receipt.json')):
            if value['completion']=='approval_kept_share_reconfirmation_required':
                result.update(sharing_state='approved_reconfirm',sharing_label='已收录，需重新核对展示内容',
                    sharing_next_action='原展示确认已失效。请从共享展示管理重新核对当前来源、分类及展示内容。')
                blocker=value.get('blocker') or {}
                if blocker.get('code') in {'CASE_SHARE_PREVIEW_STALE','CASE_DISPLAY_CONFLICT'}:
                    result['sharing_next_action']=blocker['message']+' 请从共享展示管理重新核对并明确授权。'
            elif value['completion']=='approved_only':
                result['sharing_next_action']='本次仅批准入库。请补齐允许展示的内容后，从共享展示管理明确确认。'
        return result
    except (CanonicalOperationError,OSError,ValueError,KeyError,TypeError):
        return result  # No failed read grants display or invents an executable recovery.
