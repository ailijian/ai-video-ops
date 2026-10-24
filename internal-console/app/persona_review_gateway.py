"""Console orchestration over the existing Canonical Persona owners."""
from pathlib import Path

from .canonical_gateway import CanonicalOperationError
from . import review_commands
from human_review_operations_v1 import read, file_sha


def approve(settings, command, kind, identity, business_id, reviewer, note, *, decision_metadata=None):
    from approve_persona_v1 import approve_persona
    target = command["context"]["snapshot"]
    if not target.get("artifact"):
        raise review_commands.blocked(message="尚未形成可批准的档案。")
    review_commands.validate_target(settings, command, approved_ok=True)
    path = settings.pipeline_root / target["artifact"]
    value = read(path)
    if value.get("persona_id") != identity or value.get("persona_scope", "business") != kind:
        raise review_commands.blocked()
    if kind == "speaker":
        from .persona_authority import resolve_persona_authority, validate_speaker_business_binding
        current = resolve_persona_authority(settings, business_id, "business").current
        if not current:
            raise review_commands.blocked(message="客户档案尚未批准。")
        validate_speaker_business_binding({"artifact": value}, current)
    receipt_path = path.parent / "approval_receipt.json"
    if (value.get("lifecycle") or {}).get("approved") is True and receipt_path.is_file():
        receipt = read(receipt_path)
        if (receipt.get("human_gate") is not True or receipt.get("persona_sha256_after_approval") != file_sha(path)
                or target["artifact_sha256"] not in {receipt.get("persona_sha256_before_approval"), file_sha(path)}
                or (decision_metadata is not None and receipt.get("review_decision_metadata") != decision_metadata)):
            raise review_commands.blocked()
    else:
        try:
            if decision_metadata is None:
                approve_persona(path, reviewer, note)
            else:
                approve_persona(path, reviewer, note, decision_metadata=decision_metadata)
        except RuntimeError as exc:
            raise CanonicalOperationError("PERSONA_APPROVAL_BLOCKED", "档案暂不能批准：" + str(exc), "请处理具体事实或限制，不能跳过审核。") from exc


def amend(settings, command, kind, identity, business_id, action, reason, changes):
    from persona_review_lifecycle_v1 import create_amendment
    target = command["context"]["snapshot"]
    selected = None
    if target.get("artifact"):
        path = settings.pipeline_root / target["artifact"]
        review_commands.validate_target(settings, command)
        selected = {"path": path, "artifact": read(path)}
    base = settings.pipeline_root / "data" / ("customer_intakes" if kind == "business" else "speaker_intakes") / business_id
    if kind == "speaker":
        base /= identity
    directory = base / target["intake_id"] if target.get("intake_id") else None
    try:
        return create_amendment(root=settings.pipeline_root, scope=kind, identity=identity, business_id=business_id,
            operation_id=command["context"]["operation_id"], actor=command["context"]["actor"], at=command["at"],
            action=action, reason=reason, changes=changes, selected=selected, intake_dir=directory,
            plan_path=command["directory"] / "amendment_plan.json")
    except (RuntimeError, ValueError) as exc:
        raise CanonicalOperationError("PERSONA_AMENDMENT_BLOCKED", str(exc), "请提供针对性证据；主体冲突与表达限制须继续走正式限制审核。") from exc
