"""One explicit Business confirmation over the existing Human Review owners.

No new truth store: read-only previews are signed Review Contexts; durable
coordination lives in the existing review_operations intent/companion/result.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path

from human_review_operations_v1 import digest, file_sha, read, write_once, io_path
from . import review_commands
from .canonical_gateway import CanonicalOperationError

VERSION = "customer-final-confirmation-v1.0"
APPROVE = "approve_business_profile"
SAVE = "save_review_progress"


def fail(code, message):
    return CanonicalOperationError(code, message, "请核对最新资料；已保存的人审决定与审批收据会保留。")


def ref(settings, path):
    return {"path": str(path.relative_to(settings.pipeline_root)), "sha256": file_sha(path)}


def check_ref(settings, value):
    from .path_safety import resolve_within
    path = resolve_within(settings.pipeline_root, value["path"])
    if not io_path(path).is_file() or file_sha(path) != value["sha256"]:
        raise fail("CUSTOMER_CONFIRMATION_STALE", "来源或审批记录已变化，不能沿用原确认。")
    return path


def projection(persona):
    """Stable user-visible meaning, independent of write timestamps/receipts."""
    facts = persona.get("facts") or {}
    controls = (persona.get("persona_control_layer") or {}).get("derived_authority_constraints", [])
    return {"facts": {k: copy.deepcopy(v["value"]) for k, v in sorted(facts.items()) if v.get("state") == "known"},
        "constraints": [{**{k: copy.deepcopy(v.get(k)) for k in (
            "constraint_id", "constraint_type", "scope", "state", "source", "blocked_terms", "affected_fields", "condition")},
            "decision": (v.get("human_review") or {}).get("decision")}
            for v in sorted(controls, key=lambda v: (v["source"].get("intake_id", ""), v["constraint_id"]))]}


def unfinished(settings, identity, *, all_versions=False):
    directory = settings.pipeline_root / "data/review_operations/business" / identity
    return [p for p in directory.glob("*/intent.json") if not (p.parent / "result.json").exists()
            and (all_versions or read(p).get("version") in {review_commands.BUSINESS_VERSION,review_commands.CUSTOMER_SPEAKER_VERSION})]


def guard(settings, identity, *, all_versions=False):
    if unfinished(settings, identity, all_versions=all_versions):
        raise fail("CUSTOMER_CONFIRMATION_PENDING", "上次客户档案确认尚未完成，请先恢复或取消原操作。")


def preview(settings, identity, user_id, actor, payload):
    from .customer_gateway import validate_customer_review_context, _latest_intake_dir
    from .persona_authority import resolve_persona_authority
    from customer_fact_review_v1 import (read_review_progress, validate_review_request, _validate_progress_subset,
        apply_human_decisions, derive_business_persona_input)
    from approve_persona_v1 import validate_approval_authority
    guard(settings, identity, all_versions=True)
    request = copy.deepcopy(payload)
    token = request.pop("review_context", None)
    submission = validate_customer_review_context(settings, identity, token, user_id, actor, request)
    directory = _latest_intake_dir(settings, identity)
    progress = read_review_progress(directory)
    normalized = validate_review_request({**request, "business_id": identity, "intake_id": directory.name, "reviewer": actor})
    review_path = directory / "customer_fact_review_v1.json"
    completed = read(review_path) if review_path.is_file() else None
    complete = bool(completed and str(completed["status"]).startswith("completed_"))
    authority = resolve_persona_authority(settings, identity, "business")
    target = authority.review_candidate
    at = datetime.now(timezone.utc).isoformat()
    if complete:
        if normalized["decisions"] or normalized.get("constraint_decisions") or normalized.get("industry_review"):
            raise fail("FACT_REVIEW_DECISION_IMMUTABLE", "已保存的完整审核不能由本次确认覆盖。")
        if target:
            if Path(completed.get("artifacts", {}).get("business_persona_v1", "")).resolve() != target["path"].resolve():
                raise fail("CUSTOMER_CONFIRMATION_STALE", "待批准档案与本轮资料不一致。")
            meaning = projection(target["artifact"])
            blockers = validate_approval_authority(target["artifact"], target["path"])
        else:
            meaning = {"facts": {}, "constraints": []}
            blockers = ["本轮尚未形成可批准的新档案；已批准的旧版本继续保留。"]
    else:
        _validate_progress_subset(progress["artifact"], normalized)
        proposed = apply_human_decisions(intake=read(directory / "customer_intake_v1.json"),
            candidate_artifact=progress["artifact"], decisions=normalized["decisions"], reviewer=actor,
            reviewed_at=at, partial=True, industry_review=normalized.get("industry_review"),
            constraint_decisions=normalized.get("constraint_decisions"),
            candidate_sha=file_sha(directory / "persona_fact_candidates_v1.json"))
        source, blockers, no_new = derive_business_persona_input(pipeline_root=settings.pipeline_root,
            business_id=identity, intake_root=directory, reviewed=proposed, proposed=True)
        meaning = projection(source)
        if any(v.get("candidate_state") == "requires_review" for v in proposed["fact_candidates"]) or any(
                not v.get("human_review") for v in proposed.get("derived_authority_constraints", [])):
            blockers = [*blockers, "还有未处理的信息或限制。"]
        if no_new:
            blockers = [*blockers, "没有新的可批准内容，保留已有批准版本。"]
    frozen = {}
    for base in (settings.pipeline_root / "data/customer_intakes" / identity,
                 settings.pipeline_root / "data/personas" / identity):
        for path in base.rglob("*.json"):
            if target and path == target["path"]:
                continue
            if (not complete and path == review_path) or (
                    request.get("speaker_confirmations") and path == directory / "speaker_discovery_confirmation_v1.json"):
                continue  # Existing owners recover these operation-local projections.
            frozen[str(path.relative_to(settings.pipeline_root))] = file_sha(path)
    bundle = {"schema_version": VERSION, "business_id": identity, "intake_id": directory.name,
        "mode": SAVE if blockers else APPROVE, "projection": meaning, "blockers": blockers,
        "review_payload": request, "source_review_context": token, "submission": submission,
        "fact_review_completed": complete, "frozen_sources": frozen,
        "existing_candidate": ref(settings, target["path"]) if target else None}
    bundle['can_submit'] = not blockers or (not complete and (progress['complete'] or bool(
        normalized['decisions'] or normalized.get('constraint_decisions') or normalized.get('industry_review'))))
    bundle["preview_sha256"] = digest(bundle)
    context = review_commands.issue(settings, "business", identity, user_id, confirmation=bundle)
    return {"schema_version": VERSION, "mode": bundle["mode"], "projection": meaning,
        "blockers": blockers, "can_submit":bundle['can_submit'], "preview_sha256": bundle["preview_sha256"], "review_context": context}


def validate_decision(command):
    bundle = command["context"].get("confirmation")
    if (bundle or {}).get('schema_version') == 'customer-final-confirmation-v1.1':
        from .customer_speaker_confirmation import validate_decision as validate_joint
        return validate_joint(command)['business']
    payload = read(command["directory"] / "intent.json")["intent"]["payload"] if command["saved"] else command["intent"]
    if (not bundle or bundle.get("schema_version") != VERSION
            or digest({k:v for k,v in bundle.items() if k != "preview_sha256"}) != bundle.get("preview_sha256")
            or payload.get("confirmation") != bundle["mode"] or payload.get("preview_sha256") != bundle["preview_sha256"]):
        raise fail("CUSTOMER_CONFIRMATION_REQUIRED", "请明确确认当前最终摘要；不能省略批准决定或使用过期摘要。")
    if not bundle.get('can_submit'):
        raise fail('CUSTOMER_CONFIRMATION_REQUIRED', '尚无可提交的核对决定或可批准的新档案。')
    return bundle


def _validate_sources(settings, bundle):
    from .customer_gateway import _latest_intake_dir
    if _latest_intake_dir(settings, bundle["business_id"]).name != bundle["intake_id"]:
        raise fail("CUSTOMER_CONFIRMATION_STALE", "客户已增加新资料，请重新核对。")
    for path, sha in bundle["frozen_sources"].items():
        check_ref(settings, {"path": path, "sha256": sha})


def execute(settings, command, reviewer, *, on_review=lambda: None, on_approved=lambda: None, finish_result=None):
    """Caller holds the same Business lock and current authenticated principal."""
    from .customer_gateway import validate_customer_review_context, review_customer_facts
    from .persona_authority import resolve_persona_authority
    from . import persona_review_gateway
    context = command["context"]
    finish = finish_result or (lambda result:review_commands.finish(command,result))
    bundle = validate_decision(command)
    identity = context["identity"]
    target_file = command["directory"] / "business_approval_target.json"
    if command["result"] is not None:
        result = command["result"]
        if result.get("schema_version") != VERSION or result.get("preview_sha256") != bundle["preview_sha256"]:
            raise fail("REVIEW_REPLAY_CONFLICT", "原操作已有不一致的终局结果。")
        if result.get("approval_receipt_ref"):
            receipt = read(check_ref(settings, result["approval_receipt_ref"]))
            persona = read(check_ref(settings, result["persona_ref"]))
            decision = check_ref(settings, result["decision_ref"])
            if (receipt.get('review_decision_metadata') != {'decision_artifact_ref':result['decision_ref']}
                    or receipt.get('reviewer') != reviewer or receipt.get('human_gate') is not True
                    or receipt.get('persona_sha256_after_approval') != result['persona_ref']['sha256']
                    or persona.get('approval',{}).get('human_gate') is not True
                    or read(decision).get('operation_id') != context['operation_id']):
                raise fail('REVIEW_COMMIT_CONFLICT', '原操作审批证明不一致。')
        return result
    _validate_sources(settings, bundle)
    if not target_file.exists():
        review_result = None
        if not bundle["fact_review_completed"]:
            request = bundle["review_payload"]
            submission = validate_customer_review_context(settings, identity, bundle["source_review_context"],
                context["actor"]["user_id"], reviewer, request)
            review_result = review_customer_facts(settings, business_id=identity, reviewer=reviewer,
                decisions=request["decisions"], note=request.get("note", ""),
                industry_review=request.get("industry_review"), constraint_decisions=request.get("constraint_decisions"),
                submission=submission)
        if bundle["mode"] == SAVE:
            people = on_review()
            return finish({"schema_version": VERSION,
                "preview_sha256": bundle["preview_sha256"], "operation_id": context["operation_id"],
                "completion": "review_saved", "review": review_result, "approval_receipt_ref": None,
                "speaker_confirmation":people})
        target = resolve_persona_authority(settings, identity, "business").review_candidate
        if not target or projection(target["artifact"]) != bundle["projection"]:
            raise fail("CUSTOMER_CONFIRMATION_STALE", "生成的档案与已确认摘要不一致；已保存核对结果，请重新检查。")
        target_snapshot = review_commands.snapshot(settings, "business", identity)
        intake = settings.pipeline_root / "data/customer_intakes" / identity / bundle["intake_id"]
        review_refs = [ref(settings, p) for p in sorted((intake / "review_progress").glob("*.json"))]
        review_refs += [ref(settings, intake / name) for name in (
            "customer_fact_review_v1.json", "reviewed_persona_fact_candidates_v1.json") if (intake / name).is_file()]
        write_once(target_file, {"schema_version": VERSION, "operation_id": context["operation_id"],
            "actor": context["actor"], "preview_sha256": bundle["preview_sha256"],
            "intent_ref": ref(settings, command["directory"] / "intent.json"), "snapshot": target_snapshot,
            "fact_review_refs": review_refs})
    target = read(target_file)
    if (target["operation_id"] != context["operation_id"] or target["actor"] != context["actor"]
            or target["preview_sha256"] != bundle["preview_sha256"]):
        raise fail("REVIEW_REPLAY_CONFLICT", "档案批准提交证明不匹配。")
    check_ref(settings, target["intent_ref"])
    for value in target["fact_review_refs"]:
        check_ref(settings, value)
    approval_command = {**command, "context": {**context, "snapshot": target["snapshot"]}}
    metadata = {"decision_artifact_ref": ref(settings, target_file)}
    from .case_library_access import principal
    if principal(settings, context['actor']['user_id']) != context['actor']:
        raise fail('REVIEW_ACTOR_MISMATCH', '当前客户审核身份已失效，不能继续批准。')
    persona_review_gateway.approve(settings, approval_command, "business", identity, identity, reviewer,
        "Human explicitly confirmed the reviewed Business profile and restrictions.", decision_metadata=metadata)
    path = settings.pipeline_root / target["snapshot"]["artifact"]
    receipt = read(path.parent / "approval_receipt.json")
    if (receipt.get("reviewer") != reviewer or receipt.get("human_gate") is not True
            or receipt.get("persona_sha256_before_approval") != target["snapshot"]["artifact_sha256"]
            or receipt.get("persona_sha256_after_approval") != file_sha(path)
            or receipt.get("review_decision_metadata") != metadata):
        raise fail("REVIEW_COMMIT_CONFLICT", "审批收据与原明确确认不一致。")
    people = on_review()
    on_approved()
    return finish({"schema_version": VERSION,
        "preview_sha256": bundle["preview_sha256"], "operation_id": context["operation_id"],
        "completion": "business_approved", "approval_receipt_ref": ref(settings, path.parent / "approval_receipt.json"),
        "persona_ref": ref(settings, path), "decision_ref": ref(settings, target_file), "speaker_confirmation":people})
