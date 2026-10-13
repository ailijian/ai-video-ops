"""Business restriction contract over existing Intake/Candidate/Human Review.

This module writes no authority. It validates and derives the same policy for
Persona approval and production; approved bytes and receipts are never patched.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "business-restriction-v1.0"
CONSTRAINT_TYPES = {"publication_prohibition", "unverified_claim", "identity_conflict", "conditional_fact"}
SCOPES = {"business", "claim"}
DECISIONS = {"confirm", "exclude", "defer", "dismiss", "resolve"}
STATES = {"pending_review", "active", "resolved"}
AMENDMENT_VERSION = "restriction-amendment-v1.0"
CONTROL_FIELDS = {"scope", "affected_fields", "blocked_terms", "condition"}


def normalize_amendment(value: Any) -> dict[str, Any]:
    required = {"schema_version", "original_constraint_sha256", "candidate_sha256",
        "control", "evidence_quote", "reason", "production_impact"}
    if not isinstance(value, dict) or set(value) != required:
        raise RuntimeError("Restriction amendment has unknown or missing fields.")
    if value["schema_version"] != AMENDMENT_VERSION or not isinstance(value["control"], dict) or set(value["control"]) != CONTROL_FIELDS:
        raise RuntimeError("Unsupported restriction amendment contract.")
    for key in ("original_constraint_sha256", "candidate_sha256"):
        if not isinstance(value[key], str) or len(value[key]) != 64 or any(c not in "0123456789abcdef" for c in value[key]):
            raise RuntimeError("Amendment requires exact original SHA.")
    for key in ("evidence_quote", "reason", "production_impact"):
        if not isinstance(value[key], str) or not value[key].strip():
            raise RuntimeError("Amendment requires source, reason and production impact.")
    return copy.deepcopy(value)


def amend_control(raw: dict[str, Any], decision: dict[str, Any], intake: dict[str, Any], candidate_sha: str) -> dict[str, Any]:
    amendment = normalize_amendment(decision["amendment"])
    if amendment["original_constraint_sha256"] != digest(raw) or amendment["candidate_sha256"] != candidate_sha:
        raise RuntimeError("Restriction amendment original candidate SHA differs.")
    if decision["decision"] not in {"confirm", "defer"}:
        raise RuntimeError("Amendment cannot resolve, dismiss or promote a claim.")
    control = amendment["control"]
    if control["scope"] != raw["scope"]:
        raise RuntimeError("Amendment cannot change restriction scope.")
    quote = amendment["evidence_quote"]
    answer = next((v for v in intake["raw_answers"] if quote in str(v.get("answer_text") or "")), None)
    if answer is None:
        raise RuntimeError("Amendment requires an exact saved source quote.")
    evidence = source_ref(intake, answer, quote)
    amended = {**copy.deepcopy(raw), **copy.deepcopy(control)}
    validate_record(amended)
    if any(term not in quote for term in control["blocked_terms"]):
        raise RuntimeError("Amended prohibited terms must occur in amendment evidence.")
    narrower = (not set(raw["blocked_terms"]).issubset(control["blocked_terms"])
        or not set(raw["affected_fields"]).issubset(control["affected_fields"]))
    if narrower and (evidence == raw["source"] or quote in raw["source"]["evidence_quote"] or raw["source"]["evidence_quote"] in quote):
        raise RuntimeError("Narrowing a restriction requires additional accurate evidence.")
    if raw["constraint_type"] == "identity_conflict" and control != {k: raw[k] for k in CONTROL_FIELDS}:
        raise RuntimeError("Core identity control must use the explicit resolution gate.")
    if raw["constraint_type"] == "conditional_fact":
        if raw["condition"] not in str(control["condition"] or "") or control["condition"] not in quote:
            raise RuntimeError("Amendment cannot remove the original supported condition.")
    amendment["source"] = evidence
    amendment["original_control"] = {k: copy.deepcopy(raw[k]) for k in CONTROL_FIELDS}
    decision["amendment"] = amendment
    return amended


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("Restriction authority artifact must be an object.")
    return value


def validate_source(source: dict[str, Any], intake: dict[str, Any]) -> None:
    answers = intake.get("raw_answers") or []
    raw_sha = digest(answers)
    if raw_sha != intake.get("raw_input_contract", {}).get("raw_answers_sha256"):
        raise RuntimeError("Restriction raw source SHA mismatch.")
    answer = next((a for a in answers if a.get("answer_id") == source.get("raw_answer_ref")), None)
    quote = source.get("evidence_quote")
    if (source.get("intake_id") != intake.get("intake_id")
            or source.get("raw_answers_sha256") != raw_sha
            or not answer or source.get("answer_sha256") != digest(answer)
            or not isinstance(quote, str) or not quote.strip()
            or quote not in str(answer.get("answer_text") or "")):
        raise RuntimeError("Restriction requires an exact, SHA-bound source quote.")
    from privacy_projection_v1 import assert_safe_for_external_model
    assert_safe_for_external_model(quote)


def source_ref(intake: dict[str, Any], answer: dict[str, Any], quote: str) -> dict[str, Any]:
    result = {"intake_id": intake["intake_id"], "raw_answer_ref": answer["answer_id"],
        "raw_answers_sha256": intake["raw_input_contract"]["raw_answers_sha256"],
        "answer_sha256": digest(answer), "evidence_quote": quote}
    validate_source(result, intake)
    return result


def validate_record(item: dict[str, Any]) -> None:
    from build_persona_v1 import FACT_FIELDS
    if (not isinstance(item, dict) or item.get("contract_version") != CONTRACT_VERSION
            or item.get("constraint_type") not in CONSTRAINT_TYPES
            or item.get("scope") not in SCOPES or item.get("state") not in STATES
            or not str(item.get("constraint_id") or "").startswith("BC-")
            or not isinstance(item.get("source"), dict)):
        raise RuntimeError("Unknown or malformed Business restriction contract.")
    source = item["source"]
    for key in ("raw_answers_sha256", "answer_sha256"):
        value = source.get(key)
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise RuntimeError("Restriction source SHA is invalid.")
    if not all(isinstance(source.get(k), str) and source[k].strip()
            for k in ("intake_id", "raw_answer_ref", "evidence_quote")):
        raise RuntimeError("Restriction source reference is incomplete.")
    for key in ("affected_fields", "blocked_terms", "related_fact_refs"):
        if not isinstance(item.get(key), list) or any(not isinstance(v, str) or not v.strip() for v in item[key]):
            raise RuntimeError("Restriction impact references are invalid.")
    if set(item["affected_fields"]) - set(FACT_FIELDS):
        raise RuntimeError("Restriction affected field is unknown.")
    if item["constraint_type"] == "identity_conflict" and item["scope"] != "business":
        raise RuntimeError("Core identity conflicts cannot be downgraded to claim scope.")
    if item["constraint_type"] != "identity_conflict" and item["scope"] != "claim":
        raise RuntimeError("Non-identity restriction must explicitly identify claim scope.")
    if item["scope"] == "claim" and not (item["blocked_terms"] or item["affected_fields"]):
        raise RuntimeError("Claim restriction needs explicit impact references.")
    if item["constraint_type"] == "conditional_fact" and not str(item.get("condition") or "").strip():
        raise RuntimeError("Conditional fact must retain its condition.")
    if item.get("human_review") is None:
        if item["state"] != "pending_review":
            raise RuntimeError("AI cannot activate or resolve a restriction.")
    else:
        review = item["human_review"]
        if (review.get("decision") not in DECISIONS or review.get("human_gate") is not True
                or not review.get("reviewer") or not review.get("reviewed_at")
                or not review.get("candidate_sha256")):
            raise RuntimeError("Restriction Human decision is incomplete.")
        expected = "resolved" if review["decision"] in {"dismiss", "resolve"} else "active"
        if item["state"] != expected:
            raise RuntimeError("Restriction state differs from Human decision.")
        if review["decision"] in {"dismiss", "resolve"} and not review.get("evidence"):
            raise RuntimeError("Restriction resolution requires new source evidence.")
        if review["decision"] == "exclude" and item["constraint_type"] != "unverified_claim":
            raise RuntimeError("Exclusion cannot resolve core conflicts or other restriction types.")
        if "amendment" in review:
            amendment = review["amendment"]
            normalize_amendment({k: v for k, v in amendment.items() if k not in {"source", "original_control"}})
            if (review["decision"] not in {"confirm", "defer"}
                    or amendment["candidate_sha256"] != review["candidate_sha256"]
                    or amendment["control"] != {k: item[k] for k in CONTROL_FIELDS}
                    or not amendment.get("source") or set(amendment.get("original_control", {})) != CONTROL_FIELDS):
                raise RuntimeError("Effective amendment differs from the Human decision.")


def legacy_critical_constraints(root: Path, business_id: str) -> list[dict[str, Any]]:
    from customer_intake_v1 import critical_readiness_constraints
    result = []
    for path in (root / "data" / "customer_intakes" / business_id).glob("*/customer_intake_v1.json"):
        intake = read(path)
        for record in critical_readiness_constraints(intake):
            identifier = str(record.get("constraint_id") or record.get("conflict_id") or record.get("question_id") or digest(record)[:16])
            result.append({"constraint_id": identifier, "record": record, "source_intake_id": intake["intake_id"],
                "raw_answers_sha256": intake.get("raw_input_contract", {}).get("raw_answers_sha256"),
                "computed_raw_sha256": digest(intake.get("raw_answers") or [])})
    return result


def legacy_target_key(target: dict[str, Any]) -> tuple[Any, ...]:
    return (target.get("constraint_id"), target.get("source_intake_id"),
        target.get("raw_answers_sha256"), target.get("constraint_sha256"))


def unresolved_legacy_constraints(root: Path, business_id: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    resolved = {legacy_target_key(v["human_review"]["resolution_target"]) for v in records
        if (v.get("human_review") or {}).get("decision") == "resolve" and v["human_review"].get("resolution_target")}
    return [v for v in legacy_critical_constraints(root, business_id) if legacy_target_key({
        **v, "constraint_sha256": digest(v["record"])}) not in resolved]


def extract_constraints(intake: dict[str, Any], output: dict[str, Any], safe_materials: str) -> list[dict[str, Any]]:
    raw = output.get("constraints", [])
    if not isinstance(raw, list) or len(raw) > 30:
        raise RuntimeError("Extraction constraints must be a bounded list.")
    result: list[dict[str, Any]] = []
    for proposed in raw:
        if not isinstance(proposed, dict):
            raise RuntimeError("Constraint extraction item must be an object.")
        quote = proposed.get("evidence_quote")
        if not isinstance(quote, str) or not quote.strip() or quote not in safe_materials:
            raise RuntimeError("Constraint quote is not in the task-safe projection.")
        answer = next((a for a in intake["raw_answers"] if quote in str(a.get("answer_text") or "")), None)
        if answer is None:
            raise RuntimeError("Constraint quote cannot resolve to raw source.")
        item = {"contract_version": CONTRACT_VERSION, "constraint_type": proposed.get("constraint_type"),
            "scope": proposed.get("scope"), "source": source_ref(intake, answer, quote),
            "affected_fields": copy.deepcopy(proposed.get("affected_fields", [])),
            "blocked_terms": copy.deepcopy(proposed.get("blocked_terms", [])),
            "related_fact_refs": copy.deepcopy(proposed.get("related_fact_refs") or ["source_claim:" + answer["answer_id"]]),
            "condition": proposed.get("condition"), "state": "pending_review"}
        item["constraint_id"] = "BC-" + digest(item)[:24]
        validate_record(item)
        if any(term not in quote for term in item["blocked_terms"]):
            raise RuntimeError("Restriction blocked terms require quote evidence.")
        if item["constraint_type"] == "conditional_fact" and item["condition"] not in quote:
            raise RuntimeError("Restriction condition requires quote evidence.")
        if item not in result:
            result.append(item)
    return result


def normalize_decisions(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise RuntimeError("constraint_decisions must be a list.")
    result = []
    for item in raw:
        if not isinstance(item, dict) or item.get("decision") not in DECISIONS or not item.get("constraint_id"):
            raise RuntimeError("Use a typed restriction Human decision.")
        if set(item) - {"constraint_id", "decision", "note", "resolution_quote", "evidence", "resolution_target", "amendment"}:
            raise RuntimeError("Unknown restriction decision payload; fields cannot be silently discarded.")
        entry = {"constraint_id": str(item["constraint_id"]), "decision": item["decision"],
            "note": str(item.get("note") or "").strip()}
        if "amendment" in item:
            entry["amendment"] = normalize_amendment(item["amendment"])
        if item["decision"] in {"dismiss", "resolve"}:
            quote = str(item.get("resolution_quote") or "").strip()
            if not entry["note"] or (not isinstance(item.get("evidence"), dict) and not quote):
                raise RuntimeError("Resolution or false-positive dismissal needs reason and source evidence.")
            if quote:
                entry["resolution_quote"] = quote
            else:
                entry["evidence"] = copy.deepcopy(item["evidence"])
            if item.get("resolution_target") is not None:
                target = item["resolution_target"]
                if not isinstance(target, dict) or not target.get("constraint_id") or not target.get("constraint_sha256"):
                    raise RuntimeError("Resolution requires exact target identity and candidate SHA.")
                entry["resolution_target"] = copy.deepcopy(target)
        result.append(entry)
    if len({v["constraint_id"] for v in result}) != len(result):
        raise RuntimeError("Duplicate restriction decision.")
    return sorted(result, key=lambda v: v["constraint_id"])


def apply_decisions(records: list[dict[str, Any]], decisions: list[dict[str, Any]], *,
        intake: dict[str, Any], candidate_sha: str, reviewer: str, reviewed_at: str) -> list[dict[str, Any]]:
    if {v["constraint_id"] for v in records} != {v["constraint_id"] for v in decisions}:
        raise RuntimeError("Every restriction needs an explicit typed Human decision.")
    by_id = {v["constraint_id"]: v for v in decisions}
    result = []
    for raw in records:
        validate_record(raw)
        validate_source(raw["source"], intake)
        item = copy.deepcopy(raw)
        decision = by_id[item["constraint_id"]]
        decision = copy.deepcopy(decision)
        action = decision["decision"]
        if "amendment" in decision:
            item = amend_control(raw, decision, intake, candidate_sha)
        if action in {"dismiss", "resolve"}:
            if decision.get("resolution_quote"):
                quote = decision["resolution_quote"]
                answer = next((v for v in intake["raw_answers"] if quote in str(v.get("answer_text") or "")), None)
                if answer is None:
                    raise RuntimeError("Resolution evidence must quote this intake's saved source.")
                decision["evidence"] = source_ref(intake, answer, quote)
            validate_source(decision["evidence"], intake)
            if decision["evidence"] == raw["source"]:
                raise RuntimeError("Conflict resolution requires additional evidence, not the original conflict quote.")
        item["human_review"] = {**copy.deepcopy(decision), "candidate_sha256": candidate_sha,
            "reviewer": reviewer, "reviewed_at": reviewed_at, "human_gate": True}
        item["state"] = "resolved" if action in {"dismiss", "resolve"} else "active"
        validate_record(item)
        result.append(item)
    return result


def resolution_targets(root: Path, business_id: str, current_intake: str) -> list[dict[str, Any]]:
    result = []
    for path in (root / "data" / "customer_intakes" / business_id).glob("*/persona_fact_candidates_v1.json"):
        if path.parent.name == current_intake:
            continue
        for record in read(path).get("derived_authority_constraints") or []:
            validate_record(record)
            result.append({"constraint_id": record["constraint_id"], "constraint_sha256": digest(record),
                "constraint_type": record["constraint_type"], "evidence_quote": record["source"]["evidence_quote"]})
    for item in legacy_critical_constraints(root, business_id):
        if item["source_intake_id"] != current_intake:
            result.append({"constraint_id": item["constraint_id"], "constraint_sha256": digest(item["record"]),
                "source_intake_id": item["source_intake_id"], "raw_answers_sha256": item["raw_answers_sha256"],
                "constraint_type": "identity_conflict", "evidence_quote": str(item["record"].get("question") or "待核实关键冲突")})
    return result


def policy(records: list[dict[str, Any]]) -> dict[str, Any]:
    blockers, terms, fields, conditions = [], [], [], []
    for item in records:
        validate_record(item)
        action = (item.get("human_review") or {}).get("decision")
        if item["state"] == "resolved":
            continue
        if (item["state"] == "pending_review" or item["constraint_type"] == "identity_conflict"
                or action == "defer" or (item["constraint_type"] == "unverified_claim" and action != "exclude")):
            blockers.append(item)
        if item["constraint_type"] == "conditional_fact":
            conditions.append(item)
        else:
            terms.extend(item["blocked_terms"])
            fields.extend(item["affected_fields"])
    return {"blockers": blockers, "blocked_terms": sorted(set(terms)),
        "excluded_fields": sorted(set(fields)), "conditions": conditions,
        "derived_authority_constraints": copy.deepcopy(records)}


def validate_control_layer(persona: dict[str, Any]) -> dict[str, Any]:
    layer = persona.get("persona_control_layer")
    if not layer:
        return policy([])
    if not isinstance(layer, dict) or layer.get("contract_version") != CONTRACT_VERSION:
        raise RuntimeError("Unknown Business Persona control layer.")
    records = layer.get("derived_authority_constraints")
    if not isinstance(records, list) or not records:
        raise RuntimeError("Business control layer must contain validated restrictions.")
    return policy(records)


def collect(pipeline_root: Path, business_id: str) -> list[dict[str, Any]]:
    """Read only existing canonical sources, candidates and finalized Human reviews."""
    result = []
    originals = {}
    legacy = {legacy_target_key({**v, "constraint_sha256": digest(v["record"])}): v
        for v in legacy_critical_constraints(pipeline_root, business_id)}
    root = pipeline_root / "data" / "customer_intakes" / business_id
    for directory in sorted(root.glob("*")):
        candidate_path = directory / "persona_fact_candidates_v1.json"
        if not candidate_path.is_file():
            continue
        candidate = read(candidate_path)
        records = candidate.get("derived_authority_constraints") or []
        if not records:
            continue
        intake = read(directory / "customer_intake_v1.json")
        if candidate.get("intake_ref", {}).get("raw_answers_sha256") != digest(intake.get("raw_answers", [])):
            raise RuntimeError("Restriction candidate intake lineage mismatch.")
        for item in records:
            validate_record(item)
            validate_source(item["source"], intake)
            originals[item["constraint_id"]] = item
        review_path = directory / "customer_fact_review_v1.json"
        reviewed_path = directory / "reviewed_persona_fact_candidates_v1.json"
        if (directory / "review_progress").is_dir():
            from customer_fact_review_v1 import read_review_progress
            progress = read_review_progress(directory)
            records = progress["artifact"]["derived_authority_constraints"]
            if reviewed_path.is_file() and records != read(reviewed_path).get("derived_authority_constraints"):
                raise RuntimeError("Completed restriction projection differs from immutable progress.")
        elif review_path.is_file() and reviewed_path.is_file():
            review = read(review_path)
            if (review.get("authority", {}).get("human_gate") is not True
                    or review.get("source", {}).get("fact_candidates_sha256") != file_sha(candidate_path)):
                raise RuntimeError("Restriction Human Review candidate SHA mismatch.")
            expected = apply_decisions(records, normalize_decisions(review.get("constraint_decisions", [])),
                intake=intake, candidate_sha=file_sha(candidate_path), reviewer=review["reviewer"],
                reviewed_at=review["reviewed_at"])
            if expected != read(reviewed_path).get("derived_authority_constraints"):
                raise RuntimeError("Restriction reviewed artifact differs from Human decision.")
            records = expected
        result.extend(records)
    resolved_ids = set()
    for item in result:
        review = item.get("human_review") or {}
        target = review.get("resolution_target")
        if target is None:
            continue
        old = originals.get(target.get("constraint_id"))
        legacy_target = legacy.get(legacy_target_key(target))
        if old is None and legacy_target:
            if (review.get("decision") != "resolve" or item["constraint_type"] != "identity_conflict"
                    or target.get("constraint_sha256") != digest(legacy_target["record"])
                    or target.get("source_intake_id") != legacy_target["source_intake_id"]
                    or target.get("raw_answers_sha256") != legacy_target["raw_answers_sha256"]
                    or legacy_target["raw_answers_sha256"] != legacy_target["computed_raw_sha256"]):
                raise RuntimeError("Legacy critical resolution source/identity/evidence does not validate.")
            continue
        if (review.get("decision") != "resolve" or old is None
                or target.get("constraint_sha256") != digest(old)
                or old["constraint_type"] != item["constraint_type"] or old["scope"] != item["scope"]
                or old["source"] == review.get("evidence")):
            raise RuntimeError("Restriction resolution target/source/hash does not validate.")
        resolved_ids.add(old["constraint_id"])
    # Derived only: neither the original candidate nor its decision is changed.
    effective = []
    for item in result:
        if item["constraint_id"] in resolved_ids:
            resolution = next(v for v in result if (v.get("human_review") or {}).get("resolution_target", {}).get("constraint_id") == item["constraint_id"])
            item = {**copy.deepcopy(item), "state": "resolved", "human_review": copy.deepcopy(resolution["human_review"])}
        effective.append(item)
    return effective


def root_for_persona(path: Path) -> Path | None:
    for parent in path.resolve().parents:
        if (parent / "data" / "personas").is_dir():
            return parent
    return None


def production_policy(persona: dict[str, Any], persona_path: Path | None = None) -> dict[str, Any]:
    base = validate_control_layer(persona)
    if "_production_constraints" in persona:
        base = policy(persona["_production_constraints"])
    recorded_input = (persona.get("provenance") or {}).get("input_path")
    root = root_for_persona(persona_path or Path(recorded_input)) if persona_path or recorded_input else None
    if root is not None:
        records = collect(root, str(persona["persona_id"]))
        canonical_ids = {item["constraint_id"] for item in records}
        if any(item["constraint_id"] not in canonical_ids for item in base["derived_authority_constraints"]):
            raise RuntimeError("Business restriction source/candidate cannot be resolved canonically.")
        by_id = {v["constraint_id"]: v for v in base["derived_authority_constraints"]}
        by_id.update({v["constraint_id"]: v for v in records})
        base = policy(list(by_id.values()))
        # Legacy critical conflicts never disappear because an unrelated
        # supplement happened to acquire a Known fact.
        base["blockers"].extend(v["record"] for v in unresolved_legacy_constraints(root, str(persona["persona_id"]), records))
    return base


def assert_production_allowed(persona: dict[str, Any], path: Path | None = None, *, consumer: str = "mix") -> dict[str, Any]:
    if persona.get("persona_scope", "business") != "business":
        return {}
    value = production_policy(persona, path)
    if value["blockers"]:
        raise RuntimeError("BUSINESS_CONSTRAINT_BLOCKED: unresolved or unreviewed restriction.")
    if consumer != "mix" and value["derived_authority_constraints"]:
        raise RuntimeError("BUSINESS_CONSTRAINT_CONSUMER_UNSUPPORTED: this path has no restriction-aware content validator.")
    return value


def truth_projection(persona: dict[str, Any], *, path: Path | None = None) -> dict[str, Any]:
    value = assert_production_allowed(persona, path)
    result = copy.deepcopy(persona)
    for field, fact in result.get("facts", {}).items():
        if fact.get("state") != "known":
            continue
        text = json.dumps(fact.get("value"), ensure_ascii=False)
        if field in value["excluded_fields"] or any(term in text for term in value["blocked_terms"]):
            fact.update(state="unknown", value=None)
    return result


def assert_publication_allowed(persona: dict[str, Any], path: Path, texts: list[str]) -> None:
    rules = assert_production_allowed(persona, path)
    for text in texts:
        if any(term in text for term in rules["blocked_terms"]):
            raise RuntimeError("BUSINESS_RESTRICTION_FORBIDDEN_PUBLICATION")
        if any(item["condition"] not in text and (item["affected_fields"] or any(term in text for term in item["blocked_terms"])) for item in rules["conditions"]):
            raise RuntimeError("BUSINESS_RESTRICTION_CONDITION_MISSING")
