"""Restricted legacy-scope compatibility, consumed by customer_constraints_v1.

This companion never resolves a relationship or rewrites a Persona. Its only
writer is called under the Console Business lock after current authorization.
Capability grants are trusted local maintenance, with no HTTP grant endpoint.
"""
from __future__ import annotations

import copy
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

VERSION = "legacy-constraint-scope-adjudication-v1.0"
CAPABILITY = "business_legacy_scope_reviewer"
CAPABILITY_VERSION = "business-legacy-scope-capability-v1.0"
DECISIONS = {"external_claims_only", "core_identity_unresolved", "insufficient_evidence"}
TARGET_KEYS = {"constraint_id", "source_intake_id", "raw_answers_sha256", "constraint_sha256"}


def owner():
    import customer_constraints_v1
    return customer_constraints_v1


def require(condition, message):
    if not condition:
        raise RuntimeError("LEGACY_SCOPE_INVALID: " + message)


def write_once(path, value):
    """Atomic visibility; the enclosing operation lock serializes writers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix("." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        require(not path.exists(), "immutable receipt already exists")
        os.rename(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def principal_key(actor):
    require(set(actor) == {"namespace", "user_id"}
        and re.fullmatch(r"[a-f0-9]{32}", str(actor["namespace"]))
        and type(actor["user_id"]) is int and actor["user_id"] > 0, "invalid stable principal")
    return f"{actor['namespace']}/{actor['user_id']}"


def capability_history(root, actor):
    directory = root / "data/customer_governance/legacy_scope_reviewers" / principal_key(actor)
    result, parent = [], None
    for sequence, path in enumerate(sorted(directory.glob("*.json")), 1):
        value = owner().read(path)
        body = {k: v for k, v in value.items() if k != "sha256"}
        require(set(body) == {"schema_version", "capability", "actor", "sequence", "action", "operator", "reason", "at", "parent_sha256"}
            and body["schema_version"] == CAPABILITY_VERSION and body["capability"] == CAPABILITY
            and body["actor"] == actor and body["sequence"] == sequence
            and path.name == f"{sequence:08d}.json" and body["action"] in {"grant", "revoke"}
            and body["operator"].strip() and body["reason"].strip()
            and body["parent_sha256"] == parent and owner().digest(body) == value["sha256"], "invalid reviewer grant history")
        parent = value["sha256"]
        result.append(value)
    return result


def manage_reviewer(root, actor, *, action, operator, reason):
    """Trusted local maintenance only. Never called from an HTTP grant route."""
    from operation_lock_v1 import operation_lock
    key = principal_key(actor)
    require(action in {"grant", "revoke"} and operator.strip() and reason.strip(), "explicit grant/revoke reason required")
    with operation_lock(root, "legacy-scope-reviewer:" + key):
        history = capability_history(root, actor)
        body = {"schema_version": CAPABILITY_VERSION, "capability": CAPABILITY, "actor": actor,
            "sequence": len(history) + 1, "action": action, "operator": operator.strip(), "reason": reason.strip(),
            "at": datetime.now(timezone.utc).isoformat(), "parent_sha256": history[-1]["sha256"] if history else None}
        value = {**body, "sha256": owner().digest(body)}
        write_once(root / "data/customer_governance/legacy_scope_reviewers" / key / f"{len(history)+1:08d}.json", value)
        return value


def authorize(root, database_path, actor):
    principal_key(actor)
    with sqlite3.connect(Path(database_path).resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        node = db.execute("SELECT namespace FROM console_principal_namespace WHERE singleton=1").fetchone()
        user = db.execute("SELECT status,must_change_password FROM users WHERE id=?", (actor["user_id"],)).fetchone()
    require(node and node["namespace"] == actor["namespace"] and user
        and user["status"] == "active" and not user["must_change_password"], "inactive principal")
    history = capability_history(root, actor)
    require(history and history[-1]["action"] == "grant", "explicit Business scope reviewer authorization required")
    return {"capability": CAPABILITY, "grant_sha256": history[-1]["sha256"]}


def target_key(target):
    require(isinstance(target, dict) and set(target) == TARGET_KEYS, "exact legacy target required")
    return owner().legacy_target_key(target)


def find_legacy(root, business_id, target):
    target_key(target)
    require(re.fullmatch(r"[a-z0-9][a-z0-9_]{1,127}", business_id), "invalid Business ID")
    matches = []
    for path in (root / "data/customer_intakes" / business_id).glob("*/customer_intake_v1.json"):
        intake = owner().read(path)
        for record in intake.get("conflicts", []):
            candidate = {"constraint_id": record.get("conflict_id"), "source_intake_id": intake.get("intake_id"),
                "raw_answers_sha256": intake.get("raw_input_contract", {}).get("raw_answers_sha256"),
                "constraint_sha256": owner().digest(record)}
            if candidate == target:
                matches.append((path, intake, record))
    require(len(matches) == 1, "legacy Intake/constraint SHA does not identify one source")
    path, intake, record = matches[0]
    require(record.get("severity") == "critical" and record.get("resolved") is False
        and not any(k in record for k in ("scope", "constraint_type", "contract_version")), "typed or scoped restrictions are ineligible")
    require(owner().digest(intake.get("raw_answers", [])) == target["raw_answers_sha256"], "raw answers SHA mismatch")
    return path, intake, record


def approved(root, persona_id, scope):
    # Validate frozen approval and lineage without recursively consuming policy.
    from show_customer_status_v1 import validate_approved_persona
    values = [validate_approved_persona(root, p, persona_id, scope)
        for p in (root / "data/personas" / persona_id).glob("*/persona_v1.json")]
    values = [v for v in values if v]
    require(values, "independent approved Persona required")
    revisions = [v["revision"] for v in values]
    require(len(revisions) == len(set(revisions)), "ambiguous approved Persona")
    return max(values, key=lambda v: v["revision"])


def evidence_bundle(root, business_id, target, raw_answer_refs):
    path, intake, record = find_legacy(root, business_id, target)
    require(raw_answer_refs and len(set(raw_answer_refs)) == len(raw_answer_refs), "select exact affected source answers")
    decision_path = path.parent / "persona_revision_2_human_review_decision_v1.json"
    reviewed_path = path.parent / "fact_candidates_human_reviewed_v1.json"
    decision, reviewed = owner().read(decision_path), owner().read(reviewed_path)
    require(decision.get("schema_version") == "persona-revision-2-human-review-decision-v1.0"
        and decision.get("decision") == "approve_with_exclusions_and_constraints"
        and reviewed.get("status") == "human_review_closed", "supported finalized historical Human Review required")
    require(reviewed.get("intake_ref", {}).get("intake_id") == intake["intake_id"]
        and reviewed["intake_ref"].get("raw_answers_sha256") == target["raw_answers_sha256"], "historical review Intake lineage mismatch")
    business = approved(root, business_id, "business")
    receipt = owner().read(business["receipt_path"])
    ref = receipt.get("review_decision_metadata", {}).get("decision_artifact_ref", {})
    require(ref.get("sha256") == owner().file_sha(decision_path)
        and Path(ref.get("path", "")).resolve() == decision_path.resolve(), "Human decision not bound by Business Approval")
    from build_persona_v1 import assess_business_persona_capabilities
    capability = assess_business_persona_capabilities(business["artifact"]["facts"])
    require(capability["ready"], "independently approved core business facts required")
    answers = {a["answer_id"]: a for a in intake["raw_answers"]}
    require(set(raw_answer_refs) <= set(answers), "unknown source answer")
    candidates = [v for v in reviewed["fact_candidates"] if v.get("raw_answer_ref") in raw_answer_refs]
    require(candidates and set(raw_answer_refs) == {v["raw_answer_ref"] for v in candidates}, "reviewed affected claims required")
    excluded = set(decision["business"]["excluded_review_refs"])
    for item in candidates:
        human = item.get("human_review", {})
        require(item["fact_candidate_id"] in excluded and item.get("persona_scope") == "business"
            and item.get("production_authority_eligible") is False and human.get("decision") == "keep_requires_review"
            and human.get("reviewer") == decision["reviewer"] and human.get("reviewed_at") == decision["reviewed_at"]
            and item.get("source_excerpt") in answers[item["raw_answer_ref"]]["answer_text"], "claim lacks exact historical excluded Human Review")
    identity = business["artifact"]["facts"]["public_display_name"]["value"]
    relationships = [v["normalized_value"] for v in candidates if isinstance(v.get("normalized_value"), dict)
        and v["normalized_value"].get("required_decision") == "confirm_same_entity_or_define_relationship_and_data_scope"]
    entities = sorted({v["normalized_value"]["entity"] for v in candidates
        if isinstance(v.get("normalized_value"), dict) and v["normalized_value"].get("entity_binding") == "unresolved"})
    require(relationships and entities and all(v.get("target_business") == identity for v in relationships)
        and identity in record.get("topic", "") and all(entity != identity and entity in record["topic"] for entity in entities),
        "historical external attribution claims must match this exact legacy concern")
    required_terms = sorted(set(entities) | {name.strip() for v in relationships
        for name in v.get("speaker_or_source_entity", "").split(" / ") if name.strip()})
    # Preserve source-bound quantitative exclusions even if the reviewer only
    # enters names. Never derive them from all fields or from title keywords.
    numerical_terms = sorted({number for item in candidates for claim in
        (item.get("normalized_value", {}).get("claims", []) if isinstance(item.get("normalized_value"), dict) else [])
        for number in re.findall(r"\d+(?:\.\d+)?|[一二三四五六七八九十百千万两]+", claim)
        if any(number in answers[key]["answer_text"] for key in raw_answer_refs)})
    require(all(any(term in answers[key]["answer_text"] for key in raw_answer_refs) for term in required_terms), "external identity source mismatch")
    refs = [business["path"], business["receipt_path"], path, decision_path, reviewed_path]
    require(intake.get("input_sources"), "immutable original interview source required")
    for source in intake["input_sources"]:
        original = Path(source.get("source_path", "")).resolve()
        require(original.is_relative_to(root.resolve()) and original.is_file()
            and owner().file_sha(original) == source.get("source_sha256"), "original interview SHA mismatch")
        refs.append(original)
    # An independent approved fact must not rely on the excluded source.
    candidate_markers = ["#" + v["fact_candidate_id"] for v in candidates]
    answer_markers = ["#" + v for v in raw_answer_refs]
    for field in ("public_display_name", "primary_products_or_services"):
        fact = business["artifact"]["facts"].get(field, {})
        require(fact.get("state") == "known" and fact.get("source_refs")
            and not any(marker in str(fact["source_refs"]) for marker in candidate_markers + answer_markers), "core identity depends on disputed source")
    # Preserve and bind the approved Speaker control; never reconstruct it.
    controls = reviewed.get("derived_authority_constraints", [])
    if controls:
        bound = False
        for directory in (root / "data/personas").iterdir():
            if directory.name == business_id or not directory.is_dir():
                continue
            try:
                speaker = approved(root, directory.name, "speaker")
            except RuntimeError:
                continue
            artifact = speaker["artifact"]
            if (artifact.get("business_persona_ref") or {}).get("sha256") != business["file_sha256"]:
                continue
            sr = owner().read(speaker["receipt_path"])
            if sr.get("review_decision_metadata", {}).get("decision_artifact_ref", {}).get("sha256") == owner().file_sha(decision_path):
                require(all(v["constraint_id"] in sr["review_decision_metadata"].get("derived_constraint_refs", []) for v in controls), "Speaker restriction approval missing")
                refs.extend([speaker["path"], speaker["receipt_path"]]); bound = True
        require(bound, "approved Speaker restriction lineage required")
    return {"proof": {str(p.relative_to(root)): owner().file_sha(p) for p in refs},
        "raw_answer_refs": sorted(raw_answer_refs), "related_fact_refs": sorted(v["fact_candidate_id"] for v in candidates),
        "answers": [answers[k] for k in sorted(raw_answer_refs)], "business_sha256": business["file_sha256"],
        "required_terms": required_terms, "numerical_terms": numerical_terms}


def receipt_directory(root, business_id, target):
    require(re.fullmatch(r"[a-z0-9][a-z0-9_]{1,127}", business_id), "invalid Business ID")
    path, _, _ = find_legacy(root, business_id, target)
    return path.parent / "legacy_scope_adjudications"


def receipts(root, business_id):
    result, parent = [], None
    require(re.fullmatch(r"[a-z0-9][a-z0-9_]{1,127}", business_id), "invalid Business ID")
    paths = (root / "data/customer_intakes" / business_id).glob("*/legacy_scope_adjudications/*.json")
    for sequence, path in enumerate(sorted(paths, key=lambda p: p.name), 1):
        value = owner().read(path); body = {k: v for k, v in value.items() if k != "sha256"}
        require(value.get("schema_version") == VERSION and value.get("business_id") == business_id
            and value.get("sequence") == sequence and path.name == f"{sequence:08d}.json"
            and value.get("parent_sha256") == parent and owner().digest(body) == value.get("sha256")
            and value.get("decision") in DECISIONS and value.get("reason", "").strip(), "invalid scope receipt history")
        find_legacy(root, business_id, value["target"])
        require(value.get("human_gate") is True and value.get("relationship_status") == "unresolved", "scope decision cannot resolve a relationship")
        request = value.get("request", {})
        require(value["intent_sha256"] == owner().digest({"actor": value["actor"], "request": request})
            and request.get("target") == value["target"] and request.get("decision") == value["decision"]
            and request.get("operation_id") == value["operation_id"]
            and request.get("context_sha256") == context_digest(value["evidence"], parent)
            and str(request.get("reason", "")).strip() == value["reason"]
            and sorted(set(request.get("blocked_terms", []))) == value["blocked_terms"], "receipt differs from committed Human intent")
        principal_key(value["actor"])
        history = capability_history(root, value["actor"])
        require(any(v["sha256"] == value["authorization"]["grant_sha256"] and v["action"] == "grant" for v in history)
            and value["authorization"]["capability"] == CAPABILITY, "scope receipt lacks authorized Human reviewer")
        for rel, sha in value["evidence"]["proof"].items():
            proof = (root / rel).resolve()
            require(proof.is_relative_to(root.resolve()) and owner().file_sha(proof) == sha, "historical evidence changed")
        if value["decision"] == "external_claims_only":
            require(value["blocked_terms"] and value["evidence"]["related_fact_refs"], "external claim controls missing")
        require(value["evidence"] == evidence_bundle(root, business_id, value["target"], value["evidence"]["raw_answer_refs"]), "scope evidence does not match historical review")
        parent = value["sha256"]; result.append(value)
    return result


def context_digest(evidence, parent_receipt_sha256):
    return owner().digest({"evidence": evidence, "parent_receipt_sha256": parent_receipt_sha256})


def adjudicate(root, database_path, business_id, actor, request):
    """Console calls under its Business lock. Current permission is rechecked."""
    from operation_lock_v1 import operation_lock
    # Serialize with grants/revokes through receipt commit. Revocation must not
    # slip between the final authorization check and the immutable decision.
    with operation_lock(root, "legacy-scope-reviewer:" + principal_key(actor), timeout_seconds=0):
        return _adjudicate_locked(root, database_path, business_id, actor, request)


def _adjudicate_locked(root, database_path, business_id, actor, request):
    authorization = authorize(root, database_path, actor)
    require(set(request) == {"target", "decision", "raw_answer_refs", "blocked_terms", "reason", "operation_id", "context_sha256"}, "unknown adjudication fields")
    require(request["decision"] in DECISIONS and re.fullmatch(r"[a-f0-9]{32}", request["operation_id"])
        and isinstance(request["reason"], str) and request["reason"].strip() and len(request["reason"]) <= 2000,
        "explicit Human decision/reason required")
    history = receipts(root, business_id)
    intent = {"actor": actor, "request": request}
    previous = next((v for v in history if v["operation_id"] == request["operation_id"]), None)
    if previous:
        require(previous["intent_sha256"] == owner().digest(intent), "operation replay conflicts with committed intent")
        return previous
    evidence = evidence_bundle(root, business_id, request["target"], request["raw_answer_refs"])
    require(context_digest(evidence, history[-1]["sha256"] if history else None) == request["context_sha256"], "stale scope evidence context")
    terms = request["blocked_terms"]
    text = "\n".join(a["answer_text"] for a in evidence["answers"])
    require(isinstance(terms, list) and len(terms) <= 40 and all(isinstance(t, str) and t.strip() and t in text for t in terms), "prohibited terms require exact saved source")
    if request["decision"] == "external_claims_only":
        require(set(evidence["required_terms"]) <= set(terms), "all disputed external entity/source names must remain prohibited")
        others = [v for v in owner().legacy_critical_constraints(root, business_id)
            if owner().legacy_target_key({**v, "constraint_sha256": owner().digest(v["record"])}) != target_key(request["target"])]
        require(not others and not any(v["constraint_type"] == "identity_conflict" and v["state"] != "resolved"
            for v in owner().collect(root, business_id)), "another core conflict prevents external-only adjudication")
    body = {"schema_version": VERSION, "business_id": business_id, "sequence": len(history)+1,
        "parent_sha256": history[-1]["sha256"] if history else None, "operation_id": request["operation_id"],
        "intent_sha256": owner().digest(intent), "target": request["target"], "decision": request["decision"],
        "request": copy.deepcopy(request),
        "reason": request["reason"].strip(), "actor": actor, "authorization": authorization,
        "at": datetime.now(timezone.utc).isoformat(), "evidence": evidence, "blocked_terms": sorted(set(terms)),
        "relationship_status": "unresolved", "human_gate": True}
    receipt = {**body, "sha256": owner().digest(body)}
    write_once(receipt_directory(root, business_id, request["target"]) / f"{len(history)+1:08d}.json", receipt)
    return receipt


def effective(root, business_id):
    latest = {}
    for value in receipts(root, business_id):
        latest[target_key(value["target"])] = value
    return latest


def effective_records(root, business_id):
    result = []
    for receipt in effective(root, business_id).values():
        if receipt["decision"] != "external_claims_only":
            continue
        _, intake, _ = find_legacy(root, business_id, receipt["target"])
        for answer in receipt["evidence"]["answers"]:
            source = owner().source_ref(intake, answer, answer["answer_text"])
            result.append({"contract_version": owner().CONTRACT_VERSION,
                "constraint_id": "BC-LS-" + owner().digest([receipt["sha256"], answer["answer_id"]])[:24],
                "constraint_type": "publication_prohibition", "scope": "claim", "state": "active",
                "source": source, "affected_fields": [], "blocked_terms": receipt["blocked_terms"],
                "legacy_quantitative_terms": receipt["evidence"]["numerical_terms"],
                "condition": None, "related_fact_refs": receipt["evidence"]["related_fact_refs"],
                "human_review": {"decision": "confirm", "human_gate": True, "reviewer": str(receipt["actor"]),
                    "reviewed_at": receipt["at"], "candidate_sha256": receipt["sha256"]},
                "legacy_scope_receipt_sha256": receipt["sha256"]})
    return result
