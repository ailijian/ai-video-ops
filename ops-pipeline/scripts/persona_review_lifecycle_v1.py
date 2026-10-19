"""Append-only correction/rebase companions for existing Persona Human Gates.

Approved revisions never move or change. Returned unapproved candidates remain
byte-identical and are excluded only by a validated disposition companion.
Corrections are new Intake proposals, not Truth; existing Fact Review and final
Persona Approval still decide their use. Restrictions are never resolved here.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from human_review_operations_v1 import read, write_once, file_sha, digest

VERSION = "persona-review-lifecycle-v1.0"
SPEAKER_FIELDS = {"public_display_name", "public_role", "speaker_role_facts",
    "first_person_allowed_topics", "first_person_forbidden_claims", "role_scope_constraints"}
PROTECTED_FIELDS = {"first_person_forbidden_claims", "role_scope_constraints", "forbidden_claims",
    "prohibited_topics", "information_requiring_human_review"}


def amendable_fields(scope):
    from build_persona_v1 import FACT_FIELDS
    fields = SPEAKER_FIELDS if scope == "speaker" else set(FACT_FIELDS) - (SPEAKER_FIELDS - {"public_display_name"})
    return sorted(fields - PROTECTED_FIELDS)


def candidate_path(output_root, source):
    revision = int(source.get("revision") or 1)
    suffix = source.get("review_candidate_id")
    if suffix is not None and not re.fullmatch(r"[a-f0-9]{32}", suffix):
        raise RuntimeError("Invalid review candidate identity")
    return Path(output_root) / source["persona_id"] / (
        f"revision_{revision:04d}" + ("_" + suffix[:12] if suffix else "")) / "persona_v1.json"


def is_returned(path):
    path = Path(path)
    receipt = path.parent / "review_disposition_v1.json"
    if not receipt.exists():
        return False
    value = read(receipt)
    amendment = Path(value.get("amendment_path", ""))
    if (value.get("version") != VERSION or value.get("action") != "return_for_review"
            or value.get("candidate_sha256") != file_sha(path)
            or not amendment.is_file() or value.get("amendment_sha256") != file_sha(amendment)):
        raise RuntimeError("Persona review disposition lineage is invalid")
    source = read(amendment)
    if source.get("source_candidate") != {"path": str(path.resolve()), "sha256": file_sha(path)}:
        raise RuntimeError("Persona disposition targets another candidate")
    if (read(path).get("lifecycle") or {}).get("approved") is not False:
        raise RuntimeError("Approved Persona cannot be returned or hidden")
    return True


def replacement_fields(directory, reviewed):
    path = Path(directory) / "review_amendment_v1.json"
    if not path.exists():
        return set()
    amendment = read(path)
    if amendment.get("version") != VERSION:
        raise RuntimeError("Unsupported Persona amendment")
    for source in amendment["source_refs"]:
        if file_sha(Path(source["path"])) != source["sha256"]:
            raise RuntimeError("Persona amendment source changed")
    accepted = {v["target_field"] for v in reviewed.get("fact_candidates", [])
        if v.get("candidate_state") == "known_candidate"
        and (v.get("human_review") or {}).get("decision") in {"approve", "edit"}}
    # Expression prohibitions can be supplemented, never removed by ordinary correction.
    return set(amendment["replacement_fields"]) & accepted - PROTECTED_FIELDS


def effective_sources(sources, *, speaker=False):
    """Later explicitly reviewed replacements supersede facts, never controls/history."""
    result = copy.deepcopy(sources)
    for index, row in enumerate(result):
        directory, reviewed = (row[0].parent, row[1]) if speaker else (row[2].parent, row[1])
        fields = replacement_fields(directory, reviewed)
        if fields:
            for earlier in result[:index]:
                earlier[1]["fact_candidates"] = [v for v in earlier[1].get("fact_candidates", [])
                    if v.get("target_field") not in fields]
    return result


def scalar_review_values(historical, preview, current, replacing):
    """Identical conflict semantics for partial saves and final materialization."""
    from customer_intake_v1 import SCALAR_PERSONA_FIELDS
    result = {}
    for field in SCALAR_PERSONA_FIELDS:
        values = [v.get("normalized_value") for _, source, _ in historical
            for v in source.get("fact_candidates", []) if field not in replacing
            and v.get("target_field") == field and v.get("candidate_state") == "known_candidate"]
        values += [v.get("normalized_value") for v in preview.get("fact_candidates", [])
            if v.get("target_field") == field and v.get("candidate_state") == "known_candidate"]
        fact = ((current or {}).get("artifact", {}).get("facts") or {}).get(field, {})
        if fact.get("state") == "known" and field not in replacing:
            values.append(fact["value"])
        result[field] = values
    return result


def apply_revision_input(root, scope, identity, directory, source, reviewed):
    """Preserve current approved facts and attach explicit new candidate identity."""
    from show_customer_status_v1 import resolve_current_persona, AuthorityResolutionError
    try:
        current = resolve_current_persona(root, identity, scope)
    except AuthorityResolutionError as exc:
        if exc.code not in {"PERSONA_NOT_FOUND", "APPROVED_PERSONA_NOT_FOUND"}:
            raise
        current = None
    replaced = replacement_fields(directory, reviewed)
    if current:
        for field, fact in current["artifact"].get("facts", {}).items():
            if fact.get("state") == "known" and field not in replaced and field not in source["facts"]:
                source["facts"][field] = copy.deepcopy(fact)
        source["revision"] = current["revision"] + 1
        source["previous_approved_persona_path"] = str(current["path"])
        # Existing approved controls are independent of ordinary fact replacement.
        if scope == "speaker":
            for key in ("persona_control_layer", "critical_constraints"):
                if key in current["artifact"]:
                    source[key] = copy.deepcopy(current["artifact"][key])
    amendment_path = Path(directory) / "review_amendment_v1.json"
    if amendment_path.exists():
        source["review_candidate_id"] = read(amendment_path)["operation_id"]
    return replaced


def create_amendment(*, root, scope, identity, business_id, operation_id, actor, at,
        action, reason, changes, selected, intake_dir, plan_path):
    """Caller holds Business lock. Resume the saved plan after any interrupted write."""
    from build_persona_v1 import FACT_FIELDS
    from customer_intake_v1 import build_customer_intake, build_fact_candidate_artifact, _candidate
    from show_customer_status_v1 import resolve_current_persona
    if action not in {"correct", "rebase"} or not reason.strip():
        raise RuntimeError("Explicit amendment action and reason are required")
    if action == "rebase" and scope != "speaker":
        raise RuntimeError("Only Speaker Business bindings can be rebased")
    allowed = SPEAKER_FIELDS if scope == "speaker" else set(FACT_FIELDS) - (SPEAKER_FIELDS - {"public_display_name"})
    if not isinstance(changes, list) or len(changes) > 40 or any(
            not isinstance(v, dict) or set(v) != {"field", "value", "evidence"}
            or not isinstance(v["evidence"], str) or len(v["evidence"]) > 8000
            or len(json.dumps(v["value"], ensure_ascii=False)) > 16000 for v in changes):
        raise RuntimeError("Invalid amendment field, value or evidence shape")
    changes = copy.deepcopy(changes)
    if len({v.get("field") for v in changes}) != len(changes) or any(
            v.get("field") not in set(amendable_fields(scope)) or not str(v.get("evidence") or "").strip()
            or v.get("value") in (None, "", []) for v in changes):
        raise RuntimeError("Correction requires distinct valid fields, values and source evidence")
    if action == "correct" and not changes:
        raise RuntimeError("Select at least one field to correct")
    if action == "rebase" and changes:
        raise RuntimeError("Changed personal facts require correction, not unchanged-evidence rebase")
    base = root / "data" / ("customer_intakes" if scope == "business" else "speaker_intakes") / business_id
    if scope == "speaker":
        base /= identity
    if Path(plan_path).exists():
        plan = read(plan_path)
    else:
        numbers = [int(p.name[7:]) for p in base.glob("intake_*") if re.fullmatch(r"intake_\d{4}", p.name)]
        intake_id = f"intake_{max(numbers, default=0)+1:04d}"
        refs = []
        original = read(selected["path"]) if selected else None
        if selected:
            refs.append({"path": str(selected["path"].resolve()), "sha256": file_sha(selected["path"])})
        prior_candidates = None
        prior_intake = None
        if intake_dir:
            intake_path = intake_dir / ("speaker_intake_v1.json" if scope == "speaker" else "customer_intake_v1.json")
            if intake_path.is_file():
                prior_intake = read(intake_path)
                refs.append({"path": str(intake_path.resolve()), "sha256": file_sha(intake_path)})
            for filename in (("reviewed_speaker_fact_candidates_v1.json", "speaker_fact_candidates_v1.json") if scope == "speaker"
                    else ("reviewed_persona_fact_candidates_v1.json", "persona_fact_candidates_v1.json")):
                p = intake_dir / filename
                if p.is_file():
                    prior_candidates = read(p)
                    refs.append({"path": str(p.resolve()), "sha256": file_sha(p)})
                    break
        business = resolve_current_persona(root, business_id, "business") if scope == "speaker" else None
        if action == "rebase" and selected and int((original.get("business_persona_ref") or {}).get("revision") or 0) >= business["revision"]:
            raise RuntimeError("Speaker already references the current Business")
        proposals = []
        if original:
            proposals = [{"field": field, "value": fact["value"], "evidence":
                "既有档案来源：" + "; ".join(fact.get("source_refs") or []), "previously_reviewed": True}
                for field, fact in original.get("facts", {}).items()
                if field in allowed and fact.get("state") == "known"]
        by_field = {v["field"]: v for v in proposals}
        if prior_candidates:
            # Preserve unresolved changes as pending; rebase must not silently
            # discard them in favour of the old approved Persona.
            by_field.update({v["target_field"]: {"field": v["target_field"], "value": v["normalized_value"],
                "evidence": v.get("source_excerpt") or reason,
                "previously_reviewed": v.get("candidate_state") == "known_candidate"}
                for v in prior_candidates.get("fact_candidates", []) if v.get("target_field") in allowed
                and v.get("normalized_value") not in (None, "", [])})
        by_field.update({v["field"]: v for v in changes})
        proposals = list(by_field.values())
        if not proposals:
            raise RuntimeError("No saved evidence is available for this amendment")
        plan = {"version": VERSION, "operation_id": operation_id, "scope": scope, "identity": identity,
            "business_id": business_id, "intake_id": intake_id, "action": action, "reason": reason,
            "actor": actor, "at": at, "source_refs": refs, "proposals": proposals,
            "replacement_fields": [v["field"] for v in changes],
            "source_candidate": {"path": str(selected["path"].resolve()), "sha256": file_sha(selected["path"])}
                if selected and (original.get("lifecycle") or {}).get("approved") is False else None,
            "business_ref": {"persona_id": business_id, "revision": business["revision"],
                "content_sha256": business["content_sha256"]} if business else None,
            "speaker_type": (original.get("speaker_type") or "generic") if original else
                ((prior_intake or {}).get("speaker_selection") or {}).get("speaker_type", "generic")}
        write_once(plan_path, plan)
    directory = base / plan["intake_id"]
    answers = [{"answer_id": f"AMEND-{i:03d}", "topic": v["field"], "answer_text": v["evidence"],
        "input_actor": "operator", "source_type": "human_review_amendment",
        "source_ref": f"review_operation:{operation_id}#{i}", "confirmation_basis": "pending_human_review"}
        for i, v in enumerate(plan["proposals"], 1)]
    intake = build_customer_intake(intake_id=plan["intake_id"], intake_type="gap_supplement",
        provisional_business_id=identity if scope == "business" else None, business_ref=plan["business_ref"],
        input_actor="operator", input_sources=[{"source_type": "human_review_amendment", "source_ref": operation_id}],
        raw_answers=answers, speaker_selection={"speaker_type": plan["speaker_type"]},
        created_by=actor, source_lineage={"review_amendment_operation": operation_id, "source_refs": plan["source_refs"]}, created_at=at)
    items = [_candidate(candidate_id=f"AMEND-{i:03d}", scope=scope, target_field=v["field"],
        value=v["value"], raw_answer=answer, excerpt=v["evidence"], state="known_candidate" if v.get("previously_reviewed") else "requires_review",
        review_note="本轮复核提议，尚未形成已批准事实。") for i, (v, answer) in enumerate(zip(plan["proposals"], answers), 1)]
    candidates = build_fact_candidate_artifact(intake, items, created_at=at)
    write_once(directory / "review_amendment_v1.json", plan)
    write_once(directory / ("speaker_intake_v1.json" if scope == "speaker" else "customer_intake_v1.json"), intake)
    write_once(directory / ("speaker_fact_candidates_v1.json" if scope == "speaker" else "persona_fact_candidates_v1.json"), candidates)
    request = {"business_id": business_id, "speaker_id": identity if scope == "speaker" else None,
        "intake_id": plan["intake_id"], "intake_type": "review_amendment", "created_by": actor, "created_at": at,
        "customer_name": next((v["value"] for v in plan["proposals"] if v["field"] == "public_display_name"), identity),
        "speaker_name": next((v["value"] for v in plan["proposals"] if v["field"] == "public_display_name"), identity),
        "public_role": next((v["value"] for v in plan["proposals"] if v["field"] == "public_role"), "身份待确认"),
        "speaker_type": plan["speaker_type"], "materials": reason,
        "authority": {"human_review_required": True, "model_call_performed": False, "persona_approved": False}}
    write_once(directory / ("speaker_onboarding_request_v1.json" if scope == "speaker" else "customer_onboarding_request_v1.json"), request)
    if plan["source_candidate"]:
        path = Path(plan["source_candidate"]["path"])
        write_once(path.parent / "review_disposition_v1.json", {"version": VERSION, "action": "return_for_review",
            "candidate_sha256": plan["source_candidate"]["sha256"], "actor": actor, "at": at,
            "amendment_path": str((directory / "review_amendment_v1.json").resolve()),
            "amendment_sha256": file_sha(directory / "review_amendment_v1.json")})
    return {"intake_id": plan["intake_id"], "status": "fact_review_required", "model_call_performed": False}
