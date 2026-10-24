"""Evidence-derived intake labels, separate from Case and compatibility approval."""
from __future__ import annotations

import math
import re
from functools import lru_cache
from datetime import datetime, timezone
from pathlib import Path

from .canonical_gateway import (
    CanonicalOperationError, _find_case_path, _read_json, _sha256, _write_atomic,
)
from .config import Settings
from .path_safety import resolve_within

# Same formal options as the existing industry selector; custom labels remain human-only.
CASE_INDUSTRIES = ("餐饮", "本地生活", "零售", "烘焙甜品", "美容", "教培", "服装", "饰品", "通用行业")
PROFILE_LABELS = {"mix": "素材混剪", "news": "新闻体", "hybrid": "混合型", "uncertain": "暂不确定"}
INDUSTRY_CUES = {
    "餐饮": ("餐厅", "厨房", "用餐", "菜品", "炒菜", "烹饪"),
    "烘焙甜品": ("蛋糕", "面包", "烘焙", "甜品", "奶油"),
    "美容": ("美容", "护肤", "美甲", "美容院", "美发"),
    "教培": ("课堂", "教学", "培训", "课程", "老师"),
    "服装": ("服装", "试衣", "穿搭", "衣架", "衣服"),
    "饰品": ("首饰", "项链", "耳环", "戒指", "手镯"),
    "零售": ("货架", "收银", "超市", "零售", "商品陈列"),
    "本地生活": ("维修", "家政", "洗车", "保洁", "上门服务"),
}
AUTHORITY = {
    "operator_labels_only": True, "case_approval": False,
    "profile_compatibility_approval": False, "media_rights_granted": False,
    "customer_facts_created": False, "source_evidence_modified": False,
}


def _context(settings: Settings, case_id: str, *, attempt_id: str | None = None):
    case_path, attempt = _find_case_path(settings, case_id,attempt_id=attempt_id)
    case = _read_json(case_path)
    attempt_id = str((attempt or {}).get("attempt_id") or (case.get("analysis_lineage") or {}).get("attempt_id") or "")
    path = None
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{7,127}", attempt_id):
        path = resolve_within(settings.pipeline_root / "data", "case_analysis_attempts", case_id, attempt_id, "case_classification_review_v1.json")
    return case_path, case, attempt_id, path


def _narration_from_bound_storyboard(settings: Settings, case: dict) -> list:
    ref = ((case.get("storyboard") or {}).get("artifact") or {})
    if not ref.get("path") or not ref.get("sha256"):
        return []
    path = Path(ref["path"])
    if not path.is_absolute():
        path = settings.pipeline_root / path
    path = path.resolve()
    if not path.is_relative_to(settings.pipeline_root.resolve()) or not path.is_file() or _sha256(path) != ref["sha256"]:
        return []
    board = _read_json(path)
    if board.get("case_id") != case.get("case_id") or not (board.get("validation") or {}).get("passed"):
        return []
    return board.get("narration_track") or []


def recommend_classification(case: dict, digest: str, narration: list | None = None) -> dict:
    """Read only already projected evidence. No model, title heuristic, or fact transfer."""
    shots = (case.get("storyboard") or {}).get("shots") or []
    narration = narration if narration is not None else ((case.get("storyboard") or {}).get("narration_track") or [])
    duration = (case.get("identity") or {}).get("duration_seconds")
    duration = float(duration) if isinstance(duration, (int, float)) and math.isfinite(duration) else 0
    profile = "uncertain"
    profile_reason = "暂时无法准确判断，请选择。"
    evidence_refs = []
    # Overlapping narration intervals must not manufacture speech dominance.
    spans = []
    for segment in narration:
        start, end = segment.get("start"), segment.get("end")
        if (isinstance(start, (int, float)) and isinstance(end, (int, float))
                and math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= duration):
            spans.append((start, end))
    covered = 0.0
    cursor = 0.0
    for start, end in sorted(spans):
        covered += max(0, end - max(cursor, start))
        cursor = max(cursor, end)
    independent = sum(
        (s.get("interpretation") or {}).get("audio_to_visual_text") == "independent"
        and bool((s.get("evidence") or {}).get("onscreen_text_safe_verbatim")
                 or (s.get("evidence") or {}).get("onscreen_text_sequence"))
        for s in shots
    )
    validation = case.get("validation") or {}
    speech_status = (case.get("audio_evidence") or {}).get("speech_evidence_status")
    usable = validation.get("passed") is True and validation.get("privacy_gate_passed") is True and bool(shots)
    if usable and duration > 0 and (spans or speech_status == "not_detected"):
        speech_dominant = covered / duration >= 0.5
        text_dominant = independent / len(shots) >= 0.5
        if speech_dominant and text_dominant:
            profile = "hybrid"
            profile_reason = "连续口播和独立的画面文字都承担了主要表达，因此更接近混合型。"
        elif speech_dominant and len(shots) >= 2:
            profile = "mix"
            profile_reason = "视频主要通过连续口播表达内容，多个画面用于辅助说明，因此更接近素材混剪。"
        elif text_dominant:
            profile = "news"
            profile_reason = "主要信息通过多个独立的画面文字段落呈现，口播占比较少，因此更接近新闻体。"
        evidence_refs = [str(s.get("shot_id") or index + 1) for index, s in enumerate(shots)]
    # Industry is conservative: at least two distinct cues in observable scenes.
    # A title, claim, or operator's prior selection cannot establish an AI suggestion.
    scenes = " ".join(
        str(v) for s in shots for v in ((s.get("evidence") or {}).get("observable_scene_safe_verbatim") or [])
    )
    scores = {label: sum(cue in scenes for cue in cues) for label, cues in INDUSTRY_CUES.items()} if usable else {}
    ordered = sorted(scores, key=scores.get, reverse=True)
    industry = None
    if ordered and scores[ordered[0]] >= 2 and (len(ordered) == 1 or scores[ordered[0]] > scores[ordered[1]]):
        industry = ordered[0]
    return {
        "industry": industry, "observed_source_profile": profile,
        "industry_reason": f"已分析的画面中出现多项{industry}场景线索，请对照视频检查。" if industry else "暂时无法准确判断，请选择。",
        "profile_reason": profile_reason,
        "needs_human_judgment": industry is None or profile == "uncertain",
        "method": "derived_from_existing_projected_evidence_v1",
        "case_sha256": digest, "shot_refs": evidence_refs,
        "evidence_lineage": case.get("provenance") or {},
        "remote_model_called": False,
    }


def classification_state(settings: Settings, case_id: str, *, attempt_id: str | None = None) -> dict:
    case_path, case, attempt_id, path = _context(settings, case_id,attempt_id=attempt_id)
    digest = _sha256(case_path)
    suggestion = recommend_classification(case, digest, _narration_from_bound_storyboard(settings, case))
    record = _read_json(path) if path and path.is_file() else None
    if record and not (
        record.get("schema_version") == "case-classification-review-v1.0"
        and record.get("case_id") == case_id and record.get("attempt_id") == attempt_id
        and record.get("authority") == AUTHORITY
        and record.get("original_suggestion", {}).get("case_sha256")
        and record.get("human", {}).get("profile") in PROFILE_LABELS
        and record.get("human", {}).get("confirmed_by_user_id")
    ):
        raise CanonicalOperationError("CASE_CLASSIFICATION_INVALID", "分类确认记录无法核对。", "请联系管理员，不要改写审核记录。")
    approved = (case.get("lifecycle") or {}).get("approved") is True
    stale = bool(record and not approved and record.get("confirmed_case_sha256") != digest)
    return {
        "case_id": case_id, "attempt_id": attempt_id,
        "suggestion": record["original_suggestion"] if record else suggestion,
        "human": record.get("human") if record else None,
        "status": "confirmed" if record and not stale else "needs_confirmation",
        "stale": stale, "candidate_sha256": digest,
        "confirmation_sha256": _sha256(path) if record else None,
        "can_confirm": path is not None and not approved and (case.get("lifecycle") or {}).get("status") == "review_required",
        "authority": AUTHORITY,
    }


def classification_summary(settings: Settings, case_id: str, *, attempt_id: str | None = None) -> dict:
    state = classification_state(settings, case_id,attempt_id=attempt_id)
    human = state["human"] or {}
    return {"status": state["status"], "industry": human.get("industry"), "profile": human.get("profile"),
            "confirmed_by": {"phone": human["confirmed_by_phone"]} if human else None,
            "confirmed_at": human.get("confirmed_at")}


def confirm_classification(settings: Settings, case_id: str, *, industry: str | None, profile: str,
                           candidate_sha256: str, expected_confirmation_sha256: str | None,
                           actor_user_id: int, actor_phone: str, attempt_id: str | None = None) -> dict:
    state = classification_state(settings, case_id,attempt_id=attempt_id)
    if _context(settings,case_id)[2] != state["attempt_id"]:
        raise CanonicalOperationError("CASE_CLASSIFICATION_CONFLICT", "这是历史尝试，不能修改当前分类。", "请查看本人原投稿或有权处理的新记录。")
    if not state["can_confirm"] or candidate_sha256 != state["candidate_sha256"] or expected_confirmation_sha256 != state["confirmation_sha256"]:
        raise CanonicalOperationError("CASE_CLASSIFICATION_CONFLICT", "分类结果已变化。", "刷新结果后重新确认。")
    industry = industry.strip() if industry else None
    if profile not in PROFILE_LABELS or (industry is not None and (not industry or len(industry) > 30 or industry in {"待分类", "unknown"})):
        raise CanonicalOperationError("CASE_CLASSIFICATION_INVALID", "请选择有效分类或显式保留未确定状态。", "检查行业与视频结构后重新确认。")
    _, _, attempt_id, path = _context(settings, case_id)
    previous = _read_json(path) if path.is_file() else None
    human = {"industry": industry, "profile": profile, "confirmed_by_user_id": actor_user_id,
             "confirmed_by_phone": actor_phone, "confirmed_at": datetime.now(timezone.utc).isoformat()}
    record = {
        "schema_version": "case-classification-review-v1.0", "case_id": case_id, "attempt_id": attempt_id,
        "original_suggestion": state["suggestion"], "confirmed_case_sha256": candidate_sha256,
        "human": human, "previous_human_choices": (previous.get("previous_human_choices", []) + [previous["human"]]) if previous else [],
        "authority": AUTHORITY,
    }
    _write_atomic(path, record)
    return classification_state(settings, case_id)


# Video content type is a separate Human classification dimension. These
# append-only records never edit Case facts, profile or creative permissions.
@lru_cache(maxsize=1)
def _type_schema():
    from jsonschema import Draft202012Validator
    schema = _read_json(Path(__file__).with_name('case_joint_schemas.json'))
    Draft202012Validator.check_schema(schema)
    return schema


def type_checked(value, name):
    from jsonschema import Draft202012Validator
    schema=_type_schema()
    if not Draft202012Validator({**schema, '$ref':'#/$defs/'+name}).is_valid(value):
        raise CanonicalOperationError('CASE_TYPE_CONTRACT_INVALID','类型确认格式无法核对。','请重新核对当前类型与操作。')
    return value


def type_catalog(settings):
    path=settings.console_root/'app/case_video_type_catalog.json'
    value=type_checked(_read_json(path),'TypeCatalog')
    if (set(value)!={'schema_version','version','entries'} or value['schema_version']!='case-content-type-catalog-v1.0'
            or type(value['version']) is not int or value['version']<1
            or len({v['type_id'] for v in value['entries']})!=len(value['entries'])
            or any(set(v)!={'type_id','label','confirmable'} or type(v['confirmable']) is not bool for v in value['entries'])):
        raise CanonicalOperationError('CASE_TYPE_CATALOG_INVALID','类型目录无法核对。','请恢复准确类型目录。')
    return {'value':value,'ref':{'path':'app/case_video_type_catalog.json','sha256':_sha256(path)}}


def _type_root(settings,case_id):
    import re
    if not re.fullmatch(r'\d{10,24}',case_id):
        raise CanonicalOperationError('CASE_TYPE_CONFLICT','案例身份无法核对。','请返回原案例。')
    return settings.pipeline_root/'data/case_governance/cases'/case_id/'content_type'


def _type_ref(settings,path):
    return {'path':path.relative_to(settings.pipeline_root).as_posix(),'sha256':_sha256(path)}


def _type_read_ref(settings,ref):
    from .path_safety import resolve_within
    path=resolve_within(settings.pipeline_root,ref['path'])
    if _sha256(path)!=ref['sha256']:
        raise CanonicalOperationError('CASE_TYPE_CONFLICT','类型来源已经变化。','请重新核对类型来源。')
    return _read_json(path)


def type_history(settings,case_id):
    from .case_library_access import _owner
    result=[];parent=None
    for sequence,path in enumerate(sorted(_type_root(settings,case_id).glob('decision_*.json')),1):
        record=type_checked(_read_json(path),'JointTypeDecision')
        if (path.name!=f'decision_{sequence:06}.json' or record['case_id']!=case_id
                or record['parent_decision_sha256']!=parent
                or not _owner(str(settings.pipeline_root)).validate_authorization_evidence(settings.database_path,record['actor'])):
            raise CanonicalOperationError('CASE_TYPE_CONFLICT','类型历史或授权无法核对。','请恢复原类型收据。')
        catalog=type_checked(_type_read_ref(settings,record['catalog_snapshot']),'TypeCatalog')
        if (type(catalog.get('version')) is not int or record['catalog_snapshot']['sha256']!=record['source_snapshot']['catalog']['sha256']
                or record['catalog_snapshot']['path']!=(_type_root(settings,case_id)/'catalog_snapshots'/(record['catalog_snapshot']['sha256']+'.json')).relative_to(settings.pipeline_root).as_posix()):
            raise CanonicalOperationError('CASE_TYPE_CONFLICT','类型目录历史无法核对。','请保留原目录快照。')
        confirm=record['confirmation']
        if record['action']=='revoke_type':
            if record['human_command'] is not None or record['human_operation_id'] is not None or not record['operation_id'].startswith('type_withdraw_'):
                raise CanonicalOperationError('CASE_TYPE_CONFLICT','撤回身份无法核对。','请使用独立撤回操作。')
        else:
            type_checked(confirm,'TypeConfirmation')
            validate_type_confirmation(settings,confirm,record['source_snapshot'],catalog={'value':catalog,'ref':record['source_snapshot']['catalog']})
            if (record['confirmed_type_id']!=confirm['type_id'] or record['other_note']!=confirm['other_note']
                    or record['profile_conflict_resolution']!=confirm['profile_conflict_resolution'] or record['reason']!=confirm['reason']
                    or record['action']!=('defer_type' if confirm['type_id'] is None else 'confirm_type')
                    or record['source_snapshot']['catalog']!=confirm['catalog']):
                raise CanonicalOperationError('CASE_TYPE_CONFLICT','类型决定与人工确认不一致。','请恢复原类型决定。')
        if record['human_command'] is not None:
            saved=_type_read_ref(settings,record['human_command']);context=saved['context']
            binding=_read_json(settings.pipeline_root/'data/cases'/case_id/'console_review_command_v1.json')
            if (context['version']!='human-review-command-v1.6' or context['operation_id']!=record['human_operation_id']
                    or record['operation_id']!='type_'+record['human_operation_id']
                    or saved['intent']['payload'].get('type_confirmation')!=confirm
                    or context['type_confirmation']!=confirm or context['sharing']['preview']['type_source']!=record['source_snapshot']
                    or context['actor']!={k:record['actor'][k] for k in ('namespace','user_id')}
                    or context['sharing']['preview']['reviewer_grant_ref']!={k:record['actor'][k] for k in ('namespace','user_id','event_id','event_sha256')}
                    or binding['context']!=context
                    or {**binding['intent_ref'],'path':binding['intent_ref']['path'].replace('\\','/')}!=record['human_command']
                    or record['human_command']['path']!=(settings.pipeline_root/'data/review_operations/case'/case_id/context['operation_id']/'intent.json').relative_to(settings.pipeline_root).as_posix()
                    or record['case_source']['path']!=(settings.pipeline_root/'data/cases'/case_id/'case_v1.json').relative_to(settings.pipeline_root).as_posix()
                    or record['case_approval']['path']!=(settings.pipeline_root/'data/cases'/case_id/'approval_receipt.json').relative_to(settings.pipeline_root).as_posix()
                    or binding['artifacts']['case_v1.json']['sha256']!=record['case_source']['sha256']
                    or binding['artifacts']['approval_receipt.json']['sha256']!=record['case_approval']['sha256']):
                raise CanonicalOperationError('CASE_TYPE_CONFLICT','类型决定不属于原批准操作。','请保留独立收据与原操作身份。')
        elif record['human_operation_id'] is not None:
            raise CanonicalOperationError('CASE_TYPE_CONFLICT','类型操作身份不完整。','请恢复原类型记录。')
        parent=_sha256(path);result.append((record,_type_ref(settings,path)))
    return result


def type_source(settings,case_id):
    from .task_service import get_task
    path,case,attempt_id,_=_context(settings,case_id)
    state=classification_summary(settings,case_id,attempt_id=attempt_id)
    task=get_task(settings.database_path,attempt_id)
    hint=None;hint_ref=None
    if task and task['payload'].get('excel_native_origin'):
        from .case_excel_native import validate_primary_origin,ref
        intent,row,_=validate_primary_origin(settings,task)
        hint=row['raw_case'].get('video_content_type_hint') or None
        base=settings.pipeline_root/'data/case_intake_imports'/str(intent['principal']['user_id'])/intent['input']['origin']['batch_id']
        hint_ref=ref(settings,base/'rows'/(row['row_id']+'.json'))
    history=type_history(settings,case_id)
    return type_checked({'profile':state.get('profile') or (task or {}).get('payload',{}).get('operator_profile_hint'),
        'suggested_type':hint,'suggestion_ref':hint_ref,'catalog':type_catalog(settings)['ref'],
        'parent_decision_sha256':history[-1][1]['sha256'] if history else None},'TypeSource')


def validate_type_confirmation(settings,confirmation,source,*,catalog=None):
    type_checked(confirmation,'TypeConfirmation')
    catalog=catalog or type_catalog(settings)
    allowed={r['type_id'] for r in catalog['value']['entries'] if r['confirmable']}
    selected=confirmation['type_id'];resolution=confirmation['profile_conflict_resolution']
    hints={'新闻体':'news','人设型':'persona','故事型':'story','高转化型':'conversion','其它':'other','待判断':None}
    hint=hints.get(source['suggested_type'])
    conflict=(selected=='news' and source['profile']=='mix') or (selected not in {None,'news'} and source['profile']=='news')
    correction=hint is not None and selected is not None and hint!=selected
    expected='defer' if selected is None else 'correct_suggestion_with_reason' if correction else 'preserve_dimensions_with_reason' if conflict else 'no_conflict'
    if (confirmation['catalog']!=catalog['ref'] or source['catalog']!=catalog['ref']
            or selected is not None and selected not in allowed or resolution!=expected
            or selected!='other' and confirmation['other_note']!=''
            or selected=='other' and not confirmation['other_note'].strip()
            or expected in {'correct_suggestion_with_reason','preserve_dimensions_with_reason'} and not confirmation['reason'].strip()):
        raise CanonicalOperationError('CASE_TYPE_CONFIRMATION_REQUIRED','请明确核对类型、投稿建议与原制作方式。','冲突请填写原因，暂不确定请保留未分类。')
    return confirmation


def current_type(settings,case_id):
    from .case_shared_display import _base,typed_sources_current
    try:
        history=type_history(settings,case_id)
        if not history:return None
        record,ref=history[-1];case,case_sha,approval_sha=_base(settings,case_id)
        if (record['action']=='revoke_type' or record['case_source']['sha256']!=case_sha or record['case_approval']['sha256']!=approval_sha
                or record['catalog_snapshot']['sha256']!=type_catalog(settings)['ref']['sha256']):return None
        if not typed_sources_current(settings,case):return None
        if record['source_snapshot']['suggestion_ref']:_type_read_ref(settings,record['source_snapshot']['suggestion_ref'])
        return {'record':record,'ref':ref}
    except (OSError,ValueError,KeyError,RuntimeError,TypeError):return None


def write_type_decision(settings,case_id,*,actor,operation_id,action,confirmation,source,command=None):
    from .case_library_access import reviewer_authorization
    from .case_shared_display import _base
    from human_review_operations_v1 import write_once
    import re
    expected_pattern=r'type_withdraw_[a-f0-9]{32}' if action=='revoke_type' else r'type_[a-f0-9]{32}'
    if not re.fullmatch(expected_pattern,operation_id):
        raise CanonicalOperationError('CASE_TYPE_CONFLICT','类型操作编号无效。','请保留准确的独立操作编号。')
    authorization=reviewer_authorization(settings,actor)
    history=type_history(settings,case_id)
    existing=[(r,ref) for r,ref in history if r['operation_id']==operation_id]
    if existing:
        record,ref=existing[0]
        if (record['confirmation']!=confirmation or record['action']!=action or {k:record['actor'][k] for k in actor}!=actor
                or record['source_snapshot']!=source):
            raise CanonicalOperationError('CASE_TYPE_CONFLICT','原类型操作已用于其他决定。','不能覆盖或替换原决定。')
        return ref
    parent=history[-1][1]['sha256'] if history else None
    if parent!=source['parent_decision_sha256']:
        raise CanonicalOperationError('CASE_TYPE_CONFLICT','类型历史已变化。','请重新核对。')
    if action=='revoke_type' and (not history or history[-1][0]['action']=='revoke_type'):
        raise CanonicalOperationError('CASE_TYPE_CONFLICT','当前没有可撤回的类型决定。','请核对原类型记录。')
    if action!='revoke_type':validate_type_confirmation(settings,confirmation,source)
    case,_,_=_base(settings,case_id)
    canonical=settings.pipeline_root/'data/cases'/case_id
    catalog=type_catalog(settings);snapshot=_type_root(settings,case_id)/'catalog_snapshots'/(catalog['ref']['sha256']+'.json')
    _store_catalog_snapshot(settings,snapshot,catalog['ref']['sha256'])
    if _sha256(snapshot)!=catalog['ref']['sha256']:raise ValueError('Catalog bytes do not match machine source')
    record={'schema_version':'case-content-type-decision-v1.1','operation_id':operation_id,
        'human_operation_id':command['context']['operation_id'] if command else None,
        'human_command':_type_ref(settings,command['directory']/'intent.json') if command else None,
        'case_id':case_id,'attempt_id':case['analysis_lineage']['attempt_id'],
        'case_source':_type_ref(settings,canonical/'case_v1.json'),'case_approval':_type_ref(settings,canonical/'approval_receipt.json'),
        'actor':authorization,'at':command['at'] if command else datetime.now(timezone.utc).isoformat(),'action':action,
        'confirmation':confirmation,'source_snapshot':source,'catalog_snapshot':_type_ref(settings,snapshot),
        'confirmed_type_id':confirmation['type_id'] if confirmation else None,'other_note':confirmation['other_note'] if confirmation else '',
        'profile_conflict_resolution':confirmation['profile_conflict_resolution'] if confirmation else 'defer',
        'reason':confirmation['reason'] if confirmation else 'Explicit Human type withdrawal','parent_decision_sha256':parent}
    type_checked(record,'JointTypeDecision')
    target=_type_root(settings,case_id)/f'decision_{len(history)+1:06}.json'
    write_once(target,record);type_history(settings,case_id)
    return _type_ref(settings,target)


def _store_catalog_snapshot(settings,target,expected_sha256):
    """Retain exact source bytes, including platform newline encoding."""
    import os,uuid,hashlib
    from human_review_operations_v1 import io_path
    raw=(settings.console_root/'app/case_video_type_catalog.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_sha256:raise ValueError('Catalog source changed')
    target=io_path(target);target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        if _sha256(target)!=expected_sha256:raise ValueError('Catalog snapshot conflict')
        return
    temporary=target.parent/('.'+uuid.uuid4().hex+'.tmp')
    try:
        with temporary.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        try:os.link(temporary,target)
        except FileExistsError:
            if _sha256(target)!=expected_sha256:raise ValueError('Catalog snapshot conflict')
    finally:temporary.unlink(missing_ok=True)


def apply_joint_type(settings,command):
    from .case_shared_display import validate_typed_preview
    from . import review_commands
    saved=review_commands._case_intent(settings,command);context=command['context']
    if saved['intent']['payload'].get('type_confirmation')!=context['type_confirmation']:
        raise CanonicalOperationError('CASE_TYPE_CONFLICT','类型确认与原人工操作不一致。','请恢复原操作。')
    from .case_library_access import reviewer_lock
    with reviewer_lock(settings,context['actor']):
        validate_typed_preview(settings,context['sharing'],context['actor'],committed=True)
        confirm=context['type_confirmation']
        return write_type_decision(settings,context['identity'],actor=context['actor'],operation_id='type_'+context['operation_id'],
            action='defer_type' if confirm['type_id'] is None else 'confirm_type',confirmation=confirm,
            source=context['sharing']['preview']['type_source'],command=command)


def change_type(settings,case_id,actor,payload):
    from .case_shared_display import _base
    from .case_library_access import reviewer_lock
    type_checked(payload,'StandaloneTypeInput')
    with reviewer_lock(settings,actor):
        _,case_sha,receipt_sha=_base(settings,case_id)
        source=type_source(settings,case_id)
        if (payload['approved_case_sha256']!=case_sha or payload['approval_receipt_sha256']!=receipt_sha):
            raise CanonicalOperationError('CASE_TYPE_CONFLICT','批准来源已变化。','请刷新原案例。')
        source['parent_decision_sha256']=payload['expected_parent_sha256']
        if payload['action']=='revoke_type' and payload['confirmation'] is not None:raise ValueError('Withdrawal must not carry a new classification')
        return write_type_decision(settings,case_id,actor=actor,operation_id=payload['operation_id'],action=payload['action'],
            confirmation=payload['confirmation'],source=source)
