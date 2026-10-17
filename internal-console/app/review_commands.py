"""One actor/object/snapshot protocol for final reviews and recoverable commands.

Callers hold the existing object lock and recheck current permissions on every
request, including replays. Intents and results are Canonical companions, not a
second approval lifecycle. A durable intent recovers after a process restart.
"""
from __future__ import annotations

import base64
import hmac
import secrets
from datetime import datetime, timezone
from pathlib import Path

from .canonical_gateway import CanonicalOperationError
from .case_library_access import principal
from human_review_operations_v1 import digest, file_sha, read, write_once

_KEY = secrets.token_bytes(32)
VERSION = "human-review-command-v1.0"
CASE_COMMIT_VERSION = "case-review-command-commit-v1.0"
CASE_COMMIT_FILE = "console_review_command_v1.json"


def blocked(code="REVIEW_CONTEXT_STALE", message="审核对象或版本已变化。"):
    return CanonicalOperationError(code, message, "请刷新并核对最新记录；已保存的决定不会被覆盖。")


def _node(settings):
    return digest([str(settings.pipeline_root.resolve()), str(settings.database_path.resolve())])


def snapshot(settings, kind, identity, *, business_id=None):
    root = settings.pipeline_root
    if kind == "case":
        from .canonical_gateway import _find_case_path, _approval_candidate, _analysis_states
        candidate = _approval_candidate(settings, identity)
        path, attempt = candidate if candidate else _find_case_path(settings, identity)
        sources = [path]
        for state_path, state in _analysis_states(settings, identity):
            sources.append(state_path)
            for name in ("human_review_decision_v1.json", "case_evidence_final_review_v1.json"):
                companion = state_path.parent / name
                if companion.is_file():
                    sources.append(companion)
        canonical = root / "data/cases" / identity
        sources.extend(p for name in ("case_v1.json", "approval_receipt.json") if (p := canonical / name).is_file())
        if attempt:
            directory = root / "data/case_analysis_attempts" / identity / attempt["attempt_id"]
            sources.extend(directory.glob("case_classification_review_v1.json"))
        value = read(path)
        return {"artifact": str(path.relative_to(root)), "artifact_sha256": file_sha(path),
            "attempt_id": (attempt or {}).get("attempt_id") or (value.get("analysis_lineage") or {}).get("attempt_id"),
            "state_sha256": digest({str(p.relative_to(root)): file_sha(p) for p in sources})}
    from .persona_authority import resolve_persona_authority
    authority = resolve_persona_authority(settings, identity, kind)
    selected = authority.review_candidate or authority.current
    directories = [root / "data/personas" / identity]
    if kind == "business":
        directories.append(root / "data/customer_intakes" / identity)
    else:
        directories += [root / "data/speaker_intakes" / business_id / identity,
                        root / "data/personas" / business_id]
    paths = [p for directory in directories for p in directory.rglob("*.json")]
    from .customer_gateway import _latest_intake_dir as customer_intake
    from .speaker_gateway import _latest_intake_dir as speaker_intake
    directory = customer_intake(settings, identity) if kind == "business" else speaker_intake(settings, business_id, identity)
    return {"artifact": str(selected["path"].relative_to(root)) if selected else None,
        "artifact_sha256": file_sha(selected["path"]) if selected else None,
        "intake_id": directory.name if directory else None,
        "revision": selected["revision"] if selected else None,
        "state_sha256": digest({str(p.relative_to(root)): file_sha(p) for p in sorted(paths)})}


def issue(settings, kind, identity, user_id, *, business_id=None):
    import json
    context = {"version": VERSION, "kind": kind, "identity": identity,
        "business_id": business_id, "actor": principal(settings, user_id),
        "node": _node(settings), "operation_id": secrets.token_hex(16),
        "snapshot": snapshot(settings, kind, identity, business_id=business_id)}
    body = base64.urlsafe_b64encode(json.dumps(context, sort_keys=True).encode()).decode()
    token = body + "." + hmac.new(_KEY, body.encode(), "sha256").hexdigest()
    return {"token": token, "operation_id": context["operation_id"], **context["snapshot"]}



def reject_borrowed_context(token, expected_actor):
    """Cheap negative check before locks; never authorizes an operation.

    Full signature, snapshot and committed replay checks still run in the lock.
    A borrowed token must not take the lock ahead of its legitimate submitter.
    """
    import json
    if not token:
        raise blocked("REVIEW_CONTEXT_REQUIRED", "请从当前审核页面提交，不能省略对象版本。")
    try:
        body, _ = token.split(".")
        value = json.loads(base64.urlsafe_b64decode(body))
        matches = isinstance(value, dict) and all(value.get(k) == v for k,v in expected_actor.items())
    except Exception as exc:
        raise blocked("INVALID_REVIEW_CONTEXT") from exc
    if not matches:
        raise blocked("REVIEW_ACTOR_MISMATCH", "不能提交其他账号的审核操作。")

def begin(settings, kind, identity, user_id, token, intent, *, business_id=None, validate_only=False):
    """Validate within the object lock, before any mutation. Return durable identity."""
    import json
    import re
    if not token:
        raise blocked("REVIEW_CONTEXT_REQUIRED", "请从当前审核页面提交，不能省略对象版本。")
    try:
        body, signature = token.split(".")
        context = json.loads(base64.urlsafe_b64decode(body))
        if (context["version"] != VERSION or context["kind"] != kind or context["identity"] != identity
                or context["business_id"] != business_id or context["node"] != _node(settings)
                or not re.fullmatch(r"[a-f0-9]{32}", context["operation_id"])):
            raise ValueError()
    except Exception as exc:
        raise blocked("INVALID_REVIEW_CONTEXT", "审核上下文无效。") from exc
    if context["actor"] != principal(settings, user_id):
        raise blocked("REVIEW_ACTOR_MISMATCH", "不能提交其他账号的审核操作。")
    directory = settings.pipeline_root / "data/review_operations" / kind / identity / context["operation_id"]
    path = directory / "intent.json"
    value = {"version": VERSION, "context": context, "token_sha256": digest(token), "token": token, "intent": intent}
    if path.exists():
        saved = read(path)
        if any(saved.get(k) != v for k, v in value.items()):
            raise blocked("REVIEW_REPLAY_CONFLICT", "这次审核操作已用于其他决定。")
    else:
        if not hmac.compare_digest(signature, hmac.new(_KEY, body.encode(), "sha256").hexdigest()):
            raise blocked("INVALID_REVIEW_CONTEXT")
        if context["snapshot"] != snapshot(settings, kind, identity, business_id=business_id):
            raise blocked()
        value["at"] = datetime.now(timezone.utc).isoformat()
        if validate_only:
            return {"directory": directory, "context": context, "at": value["at"], "result": None, "saved": False}
        write_once(path, value)
    saved = read(path)
    return {"directory": directory, "context": context, "at": saved["at"],
        "result": read(directory / "result.json") if (directory / "result.json").is_file() else None, "saved": True}


def finish(command, result):
    write_once(command["directory"] / "result.json", result)
    return result


def _case_intent(settings, command):
    """The authenticated durable intent, not a request ID alone, owns execution."""
    context = command["context"]
    directory = settings.pipeline_root / "data/review_operations/case" / context["identity"] / context["operation_id"]
    saved = read(directory / "intent.json")
    if (context["kind"] != "case" or context["node"] != _node(settings)
            or directory != command["directory"] or saved["context"] != context
            or saved["intent"]["request_path"] != f'/api/cases/{context["identity"]}/review'
            or saved["intent"]["payload"].get("decision") != "approve"):
        raise blocked("REVIEW_COMMIT_CONFLICT", "审批与原提交操作不一致。")
    return saved


def _ref(settings, path, *, published_path=None):
    path = Path(path)
    target = Path(published_path) if published_path is not None else path
    return {"path": str(target.relative_to(settings.pipeline_root)), "sha256": file_sha(path)}


def stage_case_approval_commit(settings, command, staged_case, staged_governance, governance_path):
    """Associate the exact command in the SAME directory transaction as Approval.

    This is coordination evidence, not another approval or quality lifecycle.
    Failed staging leaves no prospective association on a live approved Case.
    """
    from .path_safety import resolve_within
    saved = _case_intent(settings, command)
    context = command["context"]
    target = context["snapshot"]
    candidate = resolve_within(settings.pipeline_root, target["artifact"])
    value = read(candidate)
    if file_sha(candidate) != target["artifact_sha256"]:
        raise blocked()
    evidence = {"candidate": _ref(settings, candidate)}
    for key, raw in (value.get("source_artifacts") or {}).items():
        if isinstance(raw, str) and raw.lower().endswith(".json"):
            evidence[key] = _ref(settings, resolve_within(settings.pipeline_root, raw))
    confirmation = candidate.parents[2] / "case_evidence_final_review_v1.json"
    if confirmation.exists():
        evidence["final_evidence_review"] = _ref(settings, confirmation)
    canonical = settings.pipeline_root / "data/cases" / context["identity"]
    artifacts = {name: _ref(settings, staged_case.parent / name, published_path=canonical / name)
                 for name in ("case_v1.json", "approval_receipt.json", "console_authorization_receipt_v1.json")}
    artifacts["governance"] = _ref(settings, staged_governance, published_path=governance_path)
    binding = {"schema_version": CASE_COMMIT_VERSION, "context": context,
               "intent_ref": _ref(settings, command["directory"] / "intent.json"),
               "intent_sha256": digest(saved["intent"]), "evidence": evidence, "artifacts": artifacts}
    write_once(staged_case.parent / CASE_COMMIT_FILE, binding)


def committed_case_result(settings, command):
    """Recover only an exactly bound, fully committed Approval. No terminal writer.

    Caller holds the Case lock; the reviewer lock rechecks current capability.
    Historical unfinished commands without a provable association fail closed.
    """
    context = command["context"]
    saved_path = command["directory"] / "intent.json"
    if context["kind"] != "case" or not saved_path.is_file():
        return None
    saved = read(saved_path)
    if saved["intent"]["payload"].get("decision") != "approve":
        return None
    canonical = settings.pipeline_root / "data/cases" / context["identity"] / "case_v1.json"
    association = canonical.parent / CASE_COMMIT_FILE
    if not canonical.exists():
        return None
    if not association.exists():
        if command["result"] is not None:
            return None  # Durable historical results are not new recoveries or approvals.
        target = context["snapshot"]
        attempt = settings.pipeline_root / "data/case_analysis_attempts" / context["identity"] / target["attempt_id"]
        state = read(attempt / "case_analysis_attempt_v1.json")
        if state.get("status") != "approved":
            return None  # Existing partial-transaction repair, never a committed-result shortcut.
        raise blocked("REVIEW_COMMIT_BINDING_REQUIRED", "已有批准缺少与本次提交一致的操作证明，不能自动补写结果。")
    from .case_library_access import reviewer_authorization, reviewer_lock, _owner
    from .canonical_gateway import (
        _validate_approved_case_artifacts, _validate_governance_companion,
        _approval_companion_path, get_case_detail,
    )
    from .path_safety import resolve_within
    with reviewer_lock(settings, context["actor"]):
        reviewer_authorization(settings, context["actor"])
        try:
            saved = _case_intent(settings, command)
            binding = read(association)
            if (binding.get("schema_version") != CASE_COMMIT_VERSION or binding.get("context") != context
                    or binding.get("intent_ref") != _ref(settings, saved_path)
                    or binding.get("intent_sha256") != digest(saved["intent"])):
                raise blocked("REVIEW_COMMIT_CONFLICT", "这个批准属于另一项审核提交，不能恢复到当前操作。")
            for ref in [*binding["evidence"].values(), *binding["artifacts"].values()]:
                path = resolve_within(settings.pipeline_root, ref["path"])
                if file_sha(path) != ref["sha256"]:
                    raise blocked("REVIEW_COMMIT_CONFLICT", "审批关联的证据或收据已变化，需要重新核对。")
            artifacts = binding["artifacts"]
            if (artifacts["case_v1.json"]["path"] != str(canonical.relative_to(settings.pipeline_root))
                    or artifacts["approval_receipt.json"]["path"] != str(canonical.with_name("approval_receipt.json").relative_to(settings.pipeline_root))
                    or artifacts["governance"]["path"] != str(_approval_companion_path(settings, context["identity"]).relative_to(settings.pipeline_root))):
                raise blocked("REVIEW_COMMIT_CONFLICT")
            target = context["snapshot"]
            attempt = settings.pipeline_root / "data/case_analysis_attempts" / context["identity"] / target["attempt_id"]
            state = read(attempt / "case_analysis_attempt_v1.json")
            candidate = resolve_within(settings.pipeline_root, target["artifact"])
            if (state.get("case_id") != context["identity"] or state.get("attempt_id") != target["attempt_id"]
                    or binding["evidence"]["candidate"] != {"path": target["artifact"], "sha256": target["artifact_sha256"]}
                    or file_sha(candidate) != target["artifact_sha256"]):
                raise blocked("REVIEW_COMMIT_CONFLICT")
            if state.get("status") != "approved":
                return None  # Existing transaction reconciliation owns a partial commit.
            case, receipt = _validate_approved_case_artifacts(canonical, expected_case_id=context["identity"],
                expected_attempt_id=target["attempt_id"], recovery=True)
            quality = (case.get("approval") or {}).get("human_quality_decision")
            submission = saved["intent"]["payload"].get("quality_decision")
            if quality is not None and (submission is None or any(quality.get(k) != v for k,v in submission.items())
                    or quality.get("operation_id") != context["operation_id"]
                    or any(quality["actor"].get(k) != v for k,v in context["actor"].items())):
                raise blocked("REVIEW_COMMIT_CONFLICT", "质量决定与原审核操作不一致。")
            if receipt.get("case_sha256_before_approval") != target["artifact_sha256"]:
                raise blocked("REVIEW_COMMIT_CONFLICT")
            _validate_governance_companion(read(_approval_companion_path(settings, context["identity"])),
                case_path=canonical, receipt_path=canonical.with_name("approval_receipt.json"))
            auth = read(canonical.with_name("console_authorization_receipt_v1.json"))
            approved_actor = auth["authorized_principal"]
            if (any(approved_actor.get(k) != v for k,v in context["actor"].items())
                    or auth["approval_receipt_sha256"] != file_sha(canonical.with_name("approval_receipt.json"))
                    or not _owner(str(settings.pipeline_root)).validate_authorization_evidence(settings.database_path, approved_actor)):
                raise blocked("REVIEW_COMMIT_CONFLICT")
            reviewer_authorization(settings, context["actor"], receipt["reviewer"])
            evidence = saved["intent"]["payload"].get("evidence_review")
            if evidence is not None:
                confirmation = read(resolve_within(settings.pipeline_root, binding["evidence"]["final_evidence_review"]["path"]))
                for key in ("candidate_sha256", "narration_sha256", "shot_sha256", "narration_decisions", "shot_decisions"):
                    if confirmation.get(key) != evidence.get(key):
                        raise blocked("REVIEW_COMMIT_CONFLICT")
            result = {"decision": "approved", "case": get_case_detail(settings, context["identity"]),
                      "approval_receipt_ref": artifacts["approval_receipt.json"]}
            if command["result"] is not None:
                stored = command["result"]
                if (stored.get("decision") != "approved" or stored.get("approval_receipt_ref") != result["approval_receipt_ref"]
                        or stored.get("case", {}).get("approved_case_sha256") != result["case"].get("approved_case_sha256")):
                    raise blocked("REVIEW_COMMIT_CONFLICT", "命令已有不一致的终局结果。")
                return stored
            return result
        except (OSError, KeyError, ValueError, TypeError, RuntimeError) as exc:
            if isinstance(exc, CanonicalOperationError):
                raise
            raise blocked("REVIEW_COMMIT_CONFLICT", "审批关联记录不完整，不能自动恢复。") from exc


def validate_target(settings, command, *, approved_ok=False):
    """Recovery may ignore derived state changes, never substitution of the target."""
    target = command["context"]["snapshot"]
    if not target.get("artifact"):
        return
    path = settings.pipeline_root / target["artifact"]
    if not path.resolve().is_relative_to(settings.pipeline_root.resolve()):
        raise blocked()
    if file_sha(path) == target["artifact_sha256"]:
        return
    receipt = path.parent / "approval_receipt.json"
    if approved_ok and not receipt.is_file() and (path.parent / "approval_intent_v1.json").is_file():
        record = read(path.parent / "approval_intent_v1.json")["receipt"]
        if (record.get("persona_sha256_before_approval") == target["artifact_sha256"]
                and record.get("persona_sha256_after_approval") == file_sha(path)):
            return
    if approved_ok and receipt.is_file():
        record = read(receipt)
        if (record.get("persona_sha256_before_approval") == target["artifact_sha256"]
                and record.get("persona_sha256_after_approval") == file_sha(path)):
            return
    raise blocked()


def pending(settings, kind, identity, user_id):
    """Only the submitting principal can recover its private immutable intent."""
    actor = principal(settings, user_id)
    directory = settings.pipeline_root / "data/review_operations" / kind / identity
    result = []
    for path in sorted(directory.glob("*/intent.json")):
        if (path.parent / "result.json").exists():
            continue
        value = read(path)
        if value.get("context", {}).get("actor") != actor or value["context"].get("node") != _node(settings):
            continue
        result.append({"operation_id": value["context"]["operation_id"], "at": value["at"],
            "request_path": value["intent"]["request_path"],
            "payload": {**value["intent"]["payload"], "review_context": value["token"]},
            "can_discard": can_discard(settings, path.parent, value)})
    return result


def can_discard(settings, directory, value):
    """Only an uncommitted submission can be cancelled; decisions stay immutable."""
    if not {p.name for p in directory.iterdir()} <= {"intent.json", "source_upload_reservation_v1.json"}:
        return False
    target = value["context"]["snapshot"]
    if target.get("artifact"):
        path = settings.pipeline_root / target["artifact"]
        if file_sha(path) != target["artifact_sha256"]:
            return False
        approval = path.parent / "approval_intent_v1.json"
        if approval.exists() and read(approval)["receipt"]["persona_sha256_before_approval"] == target["artifact_sha256"]:
            return False
    if value["context"]["kind"] == "case":
        attempt = settings.pipeline_root / "data/case_analysis_attempts" / value["context"]["identity"] / str(target["attempt_id"])
        if (attempt / "human_review_decision_v1.json").exists():
            return False
        canonical = settings.pipeline_root / "data/cases" / value["context"]["identity"] / "approval_receipt.json"
        if canonical.exists():
            return False
    return True
