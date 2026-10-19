"""Console projection for the existing Business restriction owner."""
from __future__ import annotations

from .canonical_gateway import CanonicalOperationError
from .case_library_access import principal
from .customer_gateway import get_customer_detail


def scope_projection(settings, business_id, user_id):
    import customer_constraints_v1 as constraints
    import legacy_constraint_scope_v1 as scope
    get_customer_detail(settings, business_id)
    actor = principal(settings, user_id)
    try:
        scope.authorize(settings.pipeline_root, settings.database_path, actor)
        can_adjudicate = True
    except RuntimeError:
        can_adjudicate = False
    result = []
    all_receipts = scope.receipts(settings.pipeline_root, business_id)
    for legacy in constraints.legacy_critical_constraints(settings.pipeline_root, business_id):
        target = {k: legacy[k] for k in ("constraint_id", "source_intake_id", "raw_answers_sha256")}
        target["constraint_sha256"] = constraints.digest(legacy["record"])
        try:
            path, intake, _ = scope.find_legacy(settings.pipeline_root, business_id, target)
        except RuntimeError:
            result.append({"target": target, "groups": [], "eligible": False, "receipts": [], "default_decision": "insufficient_evidence"})
            continue
        reviewed_path = path.parent / "fact_candidates_human_reviewed_v1.json"
        groups = []
        if reviewed_path.is_file():
            reviewed = constraints.read(reviewed_path)
            answer_ids = sorted({v.get("raw_answer_ref") for v in reviewed.get("fact_candidates", [])
                if v.get("production_authority_eligible") is False and v.get("persona_scope") == "business" and v.get("raw_answer_ref")})
            for answer_id in answer_ids:
                try:
                    evidence = scope.evidence_bundle(settings.pipeline_root, business_id, target, [answer_id])
                except (RuntimeError, OSError, KeyError):
                    continue
                answer = evidence["answers"][0]
                groups.append({"raw_answer_ref": answer_id, "source_text": answer["answer_text"],
                    "required_terms": evidence["required_terms"],
                    "claims": [{"id": v["fact_candidate_id"], "value": v["normalized_value"]}
                        for v in reviewed["fact_candidates"] if v.get("raw_answer_ref") == answer_id],
                    "context_sha256": scope.context_digest(evidence, all_receipts[-1]["sha256"] if all_receipts else None)})
        history = [v for v in all_receipts if v["target"] == target]
        result.append({"target": target, "groups": groups, "eligible": bool(groups),
            "receipts": [{k: v[k] for k in ("decision", "reason", "at", "actor", "sha256", "relationship_status")}
                for v in history], "default_decision": "insufficient_evidence"})
    return {"can_adjudicate": can_adjudicate, "items": result}


def submit_scope(settings, business_id, user_id, request):
    import legacy_constraint_scope_v1 as scope
    actor = principal(settings, user_id)
    try:
        scope.authorize(settings.pipeline_root, settings.database_path, actor)
    except RuntimeError as exc:
        raise CanonicalOperationError("BUSINESS_SCOPE_REVIEWER_REQUIRED", "此账号没有历史限制范围审核授权。", "请交由明确授权的客户审核人处理。") from exc
    try:
        return scope.adjudicate(settings.pipeline_root, settings.database_path, business_id, actor, request)
    except (RuntimeError, OSError, KeyError, TypeError, ValueError) as exc:
        raise CanonicalOperationError("LEGACY_SCOPE_REVIEW_BLOCKED", "范围裁决未保存：来源、审核状态或提交内容不符合要求。", "请刷新并核对原始来源；现有生产限制继续保留。") from exc
