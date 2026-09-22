"""Canonical Novel News beat generation and Human Review.

Repurpose News remains owned by news_delivery_v1.py. This operation consumes
an immutable Generation Request with one selected, novel opportunity and the
shared deterministic Generation Source Plan.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from close_generation_export_v1 import _empty_ledger, _build_fact_atoms
from content_quality_v1 import (
    LEDGER_SCHEMA_VERSION, STRONG_MEMORY_STATUSES,
    build_exported_semantic_ledger_update, canonical_sha256,
    replace_ledger_after_export,
)
from generate_mix_scripts_v1 import default_transport, safe_persona_projection, safe_speaker_projection
from privacy_projection_v1 import assert_safe_for_external_model, project_value
from news_delivery_v1 import (
    NewsDeliveryError, _append_presentation_history, _validate_title_against_fact,
    export_dynamic_news_xlsx,
)
from show_customer_status_v1 import sha256_file

SCHEMA = "novel-news-beat-plan-v1.0"
REVIEW_SCHEMA = "novel-news-human-review-v1.0"
PRICE_PATTERN = "pcv1_news_price_offer_led_micro_information"
SCENE_PATTERN = "pcv1_news_scene_contrast"
MIN_BEATS = 4
MAX_BEATS = 8


class NovelNewsError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NovelNewsError("NEWS_NOVEL_ARTIFACT_INVALID", f"Cannot read {path}") from exc
    if not isinstance(value, dict):
        raise NovelNewsError("NEWS_NOVEL_ARTIFACT_INVALID", f"Not a JSON object: {path}")
    return value


def _write_new(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _paths(root: Path, request_id: str) -> dict[str, Path]:
    if not request_id.startswith("gen_") or not request_id[4:].isalnum():
        raise NovelNewsError("NEWS_NOVEL_REQUEST_ID_INVALID", "Invalid Generation Request ID.")
    return {
        "request": root / "data/generation_requests" / request_id / "generation_request_v1.json",
        "source_plan": root / "data/production_plans" / request_id / "generation_source_plan_v1.json",
        "plan": root / "data/generation_batches" / request_id / "novel_news_beat_plan_v1.json",
        "review": root / "data/generation_batches" / request_id / "novel_news_human_review_v1.json",
        "approved": root / "data/generation_batches" / request_id / "approved_novel_news_v1.json",
        "receipt": root / "data/generation_batches" / request_id / "novel_news_export_receipt_v1.json",
        "closure": root / "data/generation_batches" / request_id / "novel_news_export_closure_v1.json",
    }


def _structural_source_projection(
    root: Path, pattern_ref: dict[str, Any], case_refs: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    pattern_id = str(pattern_ref.get("pattern_id") or "")
    if not re.fullmatch(r"[a-z0-9_]+", pattern_id):
        raise NovelNewsError("NEWS_NOVEL_PATTERN_LINEAGE_INVALID", "Selected Pattern ID is invalid.")
    pattern_path = root / "data/patterns/approved" / pattern_id / "pattern_v1.json"
    if not pattern_path.is_file() or sha256_file(pattern_path) != pattern_ref.get("approved_pattern_sha"):
        raise NovelNewsError("NEWS_NOVEL_PATTERN_LINEAGE_INVALID", "Selected Approved Pattern changed after source planning.")
    pattern = _read(pattern_path)
    if pattern.get("pattern_id") != pattern_id or pattern.get("status") != "approved":
        raise NovelNewsError("NEWS_NOVEL_PATTERN_LINEAGE_INVALID", "Selected Pattern is not Approved.")
    definition = pattern.get("definition") or {}
    pattern_projection = {
        "pattern_id": pattern_id,
        "invariants": definition.get("invariants") or [],
        "semantic_relation_guard": definition.get("semantic_relation_guard") or {},
        "scope_limitation": (pattern.get("scope") or {}).get("scope_limitation"),
    }
    supported_ids = set((pattern.get("scope") or {}).get("supported_case_ids") or [])
    case_projections: list[dict[str, Any]] = []
    for case_ref in case_refs:
        case_id = str(case_ref.get("case_id") or "")
        if not re.fullmatch(r"[0-9]+", case_id) or case_id not in supported_ids:
            raise NovelNewsError("NEWS_NOVEL_CASE_LINEAGE_INVALID", "Case is outside Approved Pattern support.")
        fingerprint_path = root / "data/fingerprints" / case_id / "case_fingerprint_v1.json"
        if not fingerprint_path.is_file() or sha256_file(fingerprint_path) != case_ref.get("fingerprint_sha"):
            raise NovelNewsError("NEWS_NOVEL_CASE_LINEAGE_INVALID", "Selected Case Fingerprint changed after source planning.")
        fingerprint = _read(fingerprint_path)
        if (
            fingerprint.get("case_id") != case_id
            or fingerprint.get("fingerprint_scope") != "case_structural_evidence_only"
            or (fingerprint.get("authority") or {}).get("case_specific_facts_transferred") is not False
            or fingerprint.get("source_case_sha256") != case_ref.get("approved_case_sha")
        ):
            raise NovelNewsError("NEWS_NOVEL_CASE_LINEAGE_INVALID", "Selected Fingerprint is not valid structural evidence.")
        carrier = fingerprint.get("semantic_carrier_features") or {}
        visual = fingerprint.get("visual_state_features") or {}
        case_projections.append({
            "case_id": case_id,
            "semantic_carrier_type": carrier.get("carrier_type"),
            "continuous_narration_required": carrier.get("continuous_narration_required"),
            "observed_micro_beat_count": carrier.get("micro_beat_count"),
            "observed_visual_state_count": visual.get("ordered_state_count"),
            "text_visual_relationship": visual.get("text_visual_relationship"),
        })
    return pattern_projection, case_projections


def _source_context(root: Path, request_id: str) -> dict[str, Any]:
    paths = _paths(root, request_id)
    request = _read(paths["request"])
    source_plan = _read(paths["source_plan"])
    selected = request.get("selected_content") or {}
    pattern_refs = source_plan.get("selected_patterns") or []
    case_refs = source_plan.get("eligible_case_pool") or []
    if (
        request.get("target_profile") != "news"
        or request.get("reuse_intent") != "novel_content"
        or request.get("quantity") != 1
        or not selected.get("concept_id")
        or source_plan.get("request_id") != request_id
        or (source_plan.get("request") or {}).get("request_sha") != sha256_file(paths["request"])
        or (source_plan.get("coverage") or {}).get("status") != "supported"
        or len(pattern_refs) != 1
        or not case_refs
    ):
        raise NovelNewsError("NEWS_NOVEL_SOURCE_COVERAGE_UNSUPPORTED", "Approved Novel News source coverage is required.")
    pattern_id = pattern_refs[0]["pattern_id"]
    if pattern_id == SCENE_PATTERN:
        validation_path = paths["request"].with_name("scene_contrast_real_validation_approval_v1.json")
        validation = _read(validation_path) if validation_path.is_file() else {}
        if not (
            request.get("controlled_scene_validation") is True
            and validation.get("schema_version") == "scene-contrast-real-validation-approval-v1.0"
            and validation.get("request_id") == request_id
            and validation.get("request_sha256") == sha256_file(paths["request"])
            and validation.get("human_gate") is True
            and validation.get("correspondence_confirmed") is True
        ):
            raise NovelNewsError("NEWS_SCENE_PRODUCTION_VALIDATION_REQUIRED", "Scene Contrast requires a separate Human-authorized controlled validation.")
    elif pattern_id != PRICE_PATTERN or "pricing_facts" not in selected.get("primary_fact_refs", []):
        raise NovelNewsError("NEWS_NOVEL_PATTERN_SCOPE_INVALID", "Price / Offer must be the primary semantic anchor.")
    lineage = request.get("lineage") or {}
    persona_ref = lineage.get("business_persona_ref") or {}
    speaker_ref = lineage.get("speaker_persona_ref") or {}
    persona_path = Path(str(persona_ref.get("path") or ""))
    speaker_path = Path(str(speaker_ref.get("path") or ""))
    for ref, path in ((persona_ref, persona_path), (speaker_ref, speaker_path)):
        if not path.is_file() or sha256_file(path) != ref.get("file_sha256"):
            raise NovelNewsError("NEWS_NOVEL_PERSONA_LINEAGE_INVALID", "Approved Persona changed after Request creation.")
    persona = _read(persona_path)
    speaker = _read(speaker_path)
    safe_business = safe_persona_projection(persona)
    safe_speaker = safe_speaker_projection(speaker)
    atoms = _build_fact_atoms(persona, sha256_file(persona_path), speaker, sha256_file(speaker_path))
    safe_fields = set(safe_business["facts"])
    allowed_fields = set(selected.get("primary_fact_refs") or []) | set(selected.get("supporting_fact_refs") or [])
    usable_atoms = {
        item["fact_atom_id"]: {
            **item,
            "original_known_fact": str(project_value(item["original_known_fact"], "safe_verbatim")),
        } for item in atoms
        if item.get("field") in (safe_fields & allowed_fields)
    }
    primary_atoms = set(selected.get("primary_fact_atom_refs") or [])
    if pattern_id == PRICE_PATTERN and (not primary_atoms or not primary_atoms <= set(usable_atoms)):
        raise NovelNewsError("NEWS_NOVEL_PRICE_AUTHORITY_INVALID", "Primary price Fact Atom is not Approved and privacy-safe.")
    state_a_atoms = set(selected.get("state_a_fact_atom_refs") or [])
    state_b_atoms = set(selected.get("state_b_fact_atom_refs") or [])
    if pattern_id == SCENE_PATTERN and (
        not state_a_atoms or not state_b_atoms or state_a_atoms & state_b_atoms
        or not state_a_atoms <= set(usable_atoms) or not state_b_atoms <= set(usable_atoms)
        or not selected.get("approved_state_correspondence_refs")
    ):
        raise NovelNewsError("NEWS_SCENE_CORRESPONDENCE_INVALID", "State A/B must cite distinct Approved Customer Fact Atoms.")
    pattern_structure, case_structures = _structural_source_projection(root, pattern_refs[0], case_refs)
    return {
        "paths": paths, "request": request, "source_plan": source_plan,
        "selected": selected, "pattern_id": pattern_id,
        "persona": persona, "speaker": speaker,
        "safe_business": safe_business, "safe_speaker": safe_speaker,
        "usable_atoms": usable_atoms, "primary_atoms": primary_atoms,
        "state_a_atoms": state_a_atoms, "state_b_atoms": state_b_atoms,
        "all_atoms": atoms,
        "pattern_structure": pattern_structure, "case_structures": case_structures,
    }


def _normalize_beats(raw: Any, context: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not MIN_BEATS <= len(raw) <= MAX_BEATS:
        raise NovelNewsError("NEWS_NOVEL_BEAT_COUNT_INVALID", "One News video requires 4–8 ordered beats.")
    atoms = context["usable_atoms"]
    normalized: list[dict[str, Any]] = []
    seen_text: set[str] = set()
    for order, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise NovelNewsError("NEWS_NOVEL_BEAT_INVALID", "Beat must be an object.")
        text = str(item.get("text") or "").strip()
        role = str(item.get("semantic_role") or "").strip()
        visual = str(item.get("visual_anchor") or "").strip()
        duration = str(item.get("duration_guidance") or "").strip()
        refs = item.get("source_fact_refs") or []
        if not text or not role or not visual or not duration or not isinstance(refs, list) or len(refs) != 1:
            raise NovelNewsError("NEWS_NOVEL_BEAT_INVALID", "Beat requires role, text, visual anchor, duration and one Fact Atom ref.")
        atom_id = str(refs[0])
        atom = atoms.get(atom_id)
        if atom is None:
            raise NovelNewsError("NEWS_NOVEL_UNSUPPORTED_FACT", "Beat refers to a Fact Atom outside Approved Customer Truth.")
        if text in seen_text:
            raise NovelNewsError("NEWS_NOVEL_PADDING", "Duplicate micro-information beat is not allowed.")
        try:
            _validate_title_against_fact(text, str(atom["original_known_fact"]))
        except NewsDeliveryError as exc:
            raise NovelNewsError("NEWS_NOVEL_UNGROUNDED_BEAT", str(exc)) from exc
        source_compact = re.sub(r"[\W_]+", "", str(atom["original_known_fact"]))
        text_compact = re.sub(r"[\W_]+", "", text)
        if not text_compact or text_compact not in source_compact:
            raise NovelNewsError(
                "NEWS_NOVEL_UNGROUNDED_BEAT",
                "Beat wording must be an exact grounded excerpt of its approved Fact Atom.",
            )
        if context["pattern_id"] == PRICE_PATTERN and order == 1 and (atom_id not in context["primary_atoms"] or role != "price_offer_first_semantic_anchor"):
            raise NovelNewsError("NEWS_NOVEL_PATTERN_INVARIANT", "First beat must retain the selected Price / Offer anchor.")
        if context["pattern_id"] == SCENE_PATTERN and (
            (order == 1 and (role != "state_a" or atom_id not in context["state_a_atoms"]))
            or (order == len(raw) and (role != "state_b" or atom_id not in context["state_b_atoms"]))
        ):
            raise NovelNewsError("NEWS_SCENE_PATTERN_INVARIANT", "First and last beats must preserve approved State A → State B correspondence.")
        seen_text.add(text)
        normalized.append({
            "beat_id": f"B{order:03d}", "order": order,
            "semantic_role": role, "text": text,
            "visual_anchor": visual, "duration_guidance": duration,
            "source_fact_refs": [atom_id],
            "evidence_lineage": [{
                "fact_atom_id": atom_id,
                "source_field": atom["field"],
                "approved_persona_sha256": atom["persona_sha256"],
                "source_refs": atom.get("source_refs") or [],
            }],
        })
    return normalized


def generate_novel_news_plan(
    *, pipeline_root: Path, request_id: str,
    transport: Callable[[str], dict[str, Any]] | None = None,
    generated_by: str | None = None,
) -> dict[str, Any]:
    root = pipeline_root.expanduser().resolve()
    context = _source_context(root, request_id)
    plan_path = context["paths"]["plan"]
    if plan_path.is_file():
        plan = _read(plan_path)
        if plan.get("request_sha256") != sha256_file(context["paths"]["request"]):
            raise NovelNewsError("NEWS_NOVEL_PLAN_LINEAGE_CONFLICT", "Existing Plan has different Request lineage.")
        return plan
    pattern_instruction = (
        "First beat must be the selected price/offer anchor; preserve qualifiers such as 通常/约/左右/免费."
        if context["pattern_id"] == PRICE_PATTERN else
        "First beat must cite an approved State A atom with role state_a. Last beat must cite a distinct approved State B atom with role state_b. Do not invent an A/B relationship."
    )
    prompt = json.dumps({
        "task": "Produce exactly 4–8 ordered Chinese News micro-information beats as JSON. Each text must quote its approved Fact Atom verbatim or use a contiguous excerpt; never add or rearrange factual words. Do not create any new Customer Fact. Do not import Case facts. " + pattern_instruction + " Every beat cites exactly one allowed Fact Atom ID. Return {\"beats\":[{\"semantic_role\":...,\"text\":...,\"visual_anchor\":...,\"duration_guidance\":...,\"source_fact_refs\":[atom_id]}]}.",
        "selected_opportunity": context["selected"],
        "approved_business_facts": context["safe_business"],
        "approved_speaker_facts": context["safe_speaker"],
        "approved_pattern_structure_only": context["pattern_structure"],
        "eligible_case_fingerprint_structure_only": context["case_structures"],
        "allowed_fact_atoms": [
            {"fact_atom_id": atom_id, "field": atom["field"], "fact": atom["original_known_fact"]}
            for atom_id, atom in context["usable_atoms"].items()
        ],
    }, ensure_ascii=False)
    assert_safe_for_external_model(prompt)
    remote_transport = transport is None
    if transport is None:
        import os
        transport = default_transport(os.getenv("DEEPSEEK_MODEL") or "deepseek-chat")
    response = transport(prompt)
    payload = response.get("payload") or response
    beats = _normalize_beats(payload.get("beats"), context)
    plan = {
        "schema_version": SCHEMA, "request_id": request_id,
        "created_at": _now(), "status": "review_required",
        "generated_by": generated_by,
        "request_sha256": sha256_file(context["paths"]["request"]),
        "source_plan_sha256": sha256_file(context["paths"]["source_plan"]),
        "selected_concept_id": context["selected"]["concept_id"],
        "selected_pattern_id": context["pattern_id"],
        "micro_information_beats": beats,
        "authority": {"human_review_required": True, "case_facts_transferred": False, "business_facts_copied_to_speaker": False},
        "model_call": {"remote": remote_transport, "response_sha256": response.get("response_sha256"), "usage": response.get("usage") or {}},
    }
    _write_new(plan_path, plan)
    return plan


def review_novel_news_plan(
    *, pipeline_root: Path, request_id: str,
    decisions: list[dict[str, Any]], reviewer: str,
) -> dict[str, Any]:
    context = _source_context(pipeline_root.expanduser().resolve(), request_id)
    paths = context["paths"]
    plan = _read(paths["plan"])
    if plan.get("schema_version") != SCHEMA or plan.get("request_sha256") != sha256_file(paths["request"]):
        raise NovelNewsError("NEWS_NOVEL_PLAN_INVALID", "Plan lineage is invalid.")
    if paths["approved"].is_file():
        raise NovelNewsError("NEWS_NOVEL_ALREADY_APPROVED", "Human Review is immutable; do not submit it twice.")
    original = plan["micro_information_beats"]
    by_id = {str(item.get("beat_id")): item for item in decisions}
    if len(by_id) != len(original) or set(by_id) != {item["beat_id"] for item in original}:
        raise NovelNewsError("NEWS_NOVEL_REVIEW_INCOMPLETE", "Every beat requires one Human decision.")
    selected: list[dict[str, Any]] = []
    for beat in original:
        decision = by_id[beat["beat_id"]]
        action = decision.get("decision")
        if action not in {"approved", "revised", "rejected"}:
            raise NovelNewsError("NEWS_NOVEL_REVIEW_INVALID", "Unknown Human decision.")
        if action == "rejected":
            continue
        revised = dict(beat)
        if action == "revised":
            revised["text"] = str(decision.get("revised_text") or "").strip()
        selected.append(revised)
    if not MIN_BEATS <= len(selected) <= MAX_BEATS:
        raise NovelNewsError("NEWS_NOVEL_REVIEW_BEAT_COUNT", "Approved video still requires 4–8 beats.")
    approved_beats = _normalize_beats(selected, context)
    approved = {
        "schema_version": "approved-novel-news-v1.0", "request_id": request_id,
        "status": "approved_for_export", "reviewed_at": _now(),
        "reviewed_by": reviewer, "human_gate": True,
        "plan_sha256": sha256_file(paths["plan"]),
        "micro_information_beats": approved_beats,
        "selected_pattern_id": context["pattern_id"],
        "selected_concept_id": context["selected"]["concept_id"],
    }
    review_artifact = {"schema_version": REVIEW_SCHEMA, "request_id": request_id, "reviewed_by": reviewer, "reviewed_at": approved["reviewed_at"], "decisions": decisions}
    if paths["review"].is_file():
        prior = _read(paths["review"])
        if any(prior.get(key) != review_artifact[key] for key in ("schema_version", "request_id", "reviewed_by", "decisions")):
            raise NovelNewsError("NEWS_NOVEL_REVIEW_CONFLICT", "Existing Human Review has different decisions.")
        approved["reviewed_at"] = prior.get("reviewed_at") or approved["reviewed_at"]
    else:
        _write_new(paths["review"], review_artifact)
    _write_new(paths["approved"], approved)
    return approved


def _template(root: Path) -> Path:
    registry = _read(root / "data/production_profiles/production_profile_registry_v1.json")
    contract = ((registry.get("profiles") or {}).get("news") or {}).get("export_contract") or {}
    recorded = Path(str(contract.get("template_path") or ""))
    candidate = recorded if recorded.is_file() else root / "output" / recorded.name
    if not candidate.is_file() or sha256_file(candidate) != contract.get("template_sha256"):
        raise NovelNewsError("NEWS_NOVEL_TEMPLATE_LINEAGE_INVALID", "Registered News Excel template is missing or changed.")
    return candidate


def export_novel_news(
    *, pipeline_root: Path, request_id: str, exported_by: str,
) -> dict[str, Any]:
    root = pipeline_root.expanduser().resolve()
    context = _source_context(root, request_id)
    paths = context["paths"]
    approved = _read(paths["approved"])
    if (
        approved.get("schema_version") != "approved-novel-news-v1.0"
        or approved.get("status") != "approved_for_export"
        or approved.get("human_gate") is not True
        or approved.get("plan_sha256") != sha256_file(paths["plan"])
    ):
        raise NovelNewsError("NEWS_NOVEL_REVIEW_AUTHORITY_INVALID", "Human-approved News beats are required for export.")
    beats = _normalize_beats(approved.get("micro_information_beats"), context)
    business_id = str(context["request"]["persona_id"])
    ledger_path = root / "data/content_ledgers" / business_id / "content_ledger_v1.json"
    content_id = request_id + "-N001"
    if ledger_path.is_file():
        current_ledger = _read(ledger_path)
        if current_ledger.get("schema_version") != LEDGER_SCHEMA_VERSION or current_ledger.get("business_id") != business_id:
            raise NovelNewsError("NEWS_NOVEL_LEDGER_INVALID", "Canonical business Content Ledger is invalid.")
        if not any(item.get("content_id") == content_id for item in current_ledger.get("entries") or []):
            if context["pattern_id"] == PRICE_PATTERN:
                from novel_news_opportunity_v1 import price_novelty_status
                primary_atom = context["usable_atoms"][next(iter(context["primary_atoms"]))]
                still_novel = price_novelty_status(primary_atom, context["selected"], current_ledger) == "novel"
            else:
                from content_quality_v1 import novelty_evaluation
                still_novel = not novelty_evaluation(context["selected"], list(current_ledger.get("entries") or [])).get("hard_duplicate")
            if not still_novel:
                raise NovelNewsError(
                    "NEWS_NOVEL_OPPORTUNITY_NO_LONGER_NOVEL",
                    "Another approved content export has already communicated this selected opportunity.",
                )
    template = _template(root)
    output_path = root / "output" / f"News新内容_{request_id}.xlsx"
    titles = [item["text"] for item in beats]
    if not output_path.is_file():
        export_dynamic_news_xlsx(template_path=template, output_path=output_path, titles=titles)
    else:
        from news_delivery_v1 import _xlsx_sheet_values
        if _xlsx_sheet_values(output_path, row_number=5, max_columns=len(titles)) != titles:
            raise NovelNewsError("NEWS_NOVEL_EXPORT_CONFLICT", "Existing Excel differs from Human-approved beat order.")
    if not paths["receipt"].is_file():
        _write_new(paths["receipt"], {
            "schema_version": "novel-news-excel-export-receipt-v1.0",
            "request_id": request_id, "reuse_intent": "novel_content",
            "output_path": str(output_path), "output_sha256": sha256_file(output_path),
            "approved_ref": {"path": str(paths["approved"]), "sha256": sha256_file(paths["approved"])},
            "validation_passed": True, "exported_by": exported_by,
        })
    receipt = _read(paths["receipt"])
    if receipt.get("output_sha256") != sha256_file(output_path) or (receipt.get("approved_ref") or {}).get("sha256") != sha256_file(paths["approved"]):
        raise NovelNewsError("NEWS_NOVEL_EXPORT_LINEAGE_CONFLICT", "Export receipt no longer matches approved beats and Excel.")

    exported_at = datetime.fromtimestamp(output_path.stat().st_mtime, tz=timezone.utc).isoformat()
    entry = {
        "content_id": content_id, "concept_ref": context["selected"]["concept_id"],
        "business_id": business_id, "speaker_id": context["request"]["speaker_persona"],
        "production_profile": "news", "profile": "news", "reuse_intent": "novel_content",
        "batch_ref": request_id, "status": "exported",
        "semantic_signature": context["selected"]["semantic_signature"],
        "central_claim": context["selected"]["central_claim"],
        "title": titles[0], "narration": "。".join(titles),
        "primary_fact_refs": context["selected"]["primary_fact_refs"],
        "supporting_fact_refs": context["selected"]["supporting_fact_refs"],
        "primary_fact_atom_refs": context["selected"]["primary_fact_atom_refs"],
        "fact_atom_refs": sorted({ref for beat in beats for ref in beat["source_fact_refs"]}),
        "approved_at": approved["reviewed_at"], "exported_at": exported_at,
        "new_semantic_content_count_delta": 1,
        "micro_information_beats": beats,
        "source_request_ref": {"path": str(paths["request"]), "sha256": sha256_file(paths["request"])},
        "approved_review_ref": {"path": str(paths["approved"]), "sha256": sha256_file(paths["approved"])},
        "export_receipt_ref": {"path": str(paths["receipt"]), "sha256": sha256_file(paths["receipt"])},
    }
    ledger_existed = ledger_path.is_file()
    ledger = _read(ledger_path) if ledger_existed else _empty_ledger(business_id=business_id, created_at=context["request"]["created_at"])
    if ledger.get("schema_version") != LEDGER_SCHEMA_VERSION or ledger.get("business_id") != business_id:
        raise NovelNewsError("NEWS_NOVEL_LEDGER_INVALID", "Canonical business Content Ledger is invalid.")
    existing = [item for item in ledger.get("entries") or [] if item.get("content_id") == content_id]
    if existing:
        if len(existing) != 1 or existing[0].get("source_request_ref") != entry["source_request_ref"]:
            raise NovelNewsError("NEWS_NOVEL_LEDGER_CONFLICT", "Existing semantic entry has different Request lineage.")
    else:
        if context["pattern_id"] == PRICE_PATTERN:
            from novel_news_opportunity_v1 import price_novelty_status
            primary_atom = context["usable_atoms"][next(iter(context["primary_atoms"]))]
            still_novel = price_novelty_status(primary_atom, context["selected"], ledger) == "novel"
        else:
            from content_quality_v1 import novelty_evaluation
            still_novel = not novelty_evaluation(context["selected"], list(ledger.get("entries") or [])).get("hard_duplicate")
        if not still_novel:
            raise NovelNewsError(
                "NEWS_NOVEL_OPPORTUNITY_NO_LONGER_NOVEL",
                "Another approved content export has already communicated this selected opportunity.",
            )
        updated = build_exported_semantic_ledger_update(
            ledger, [entry], context["all_atoms"], exported_at=exported_at
        )
        updated["validation"] = {
            "passed": True, "entry_count": len(updated["entries"]),
            "strong_memory_count": sum(item.get("status") in STRONG_MEMORY_STATUSES for item in updated["entries"]),
            "latest_export_request_id": request_id,
        }
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        if ledger_existed:
            replace_ledger_after_export(ledger_path, ledger, updated)
        else:
            _write_new(ledger_path, updated)
    presentation_id = request_id + "-P001"
    presentation = {
        "presentation_id": presentation_id, "business_id": business_id,
        "speaker_id": context["request"]["speaker_persona"], "request_id": request_id,
        "production_profile": "news", "reuse_intent": "novel_content",
        "semantic_novelty": False, "semantic_content_created_separately": True,
        "source_content_ref": content_id, "selected_pattern_ref": context["pattern_id"],
        "status": "exported", "approved_at": approved["reviewed_at"], "exported_at": exported_at,
        "new_semantic_content_count_delta": 0, "novel_capacity_delta": 0,
        "communicated_information_units_created": False,
        "approved_titles": titles,
        "approval_ref": {"path": str(paths["approved"]), "sha256": sha256_file(paths["approved"])},
        "export_ref": {"path": str(output_path), "sha256": sha256_file(output_path)},
    }
    _append_presentation_history(ledger_path=ledger_path, source_content_id=content_id, entry=presentation)
    if not paths["closure"].is_file():
        _write_new(paths["closure"], {
            "schema_version": "novel-news-export-closure-v1.0", "request_id": request_id,
            "content_id": content_id, "presentation_id": presentation_id,
            "semantic_entry_count_delta": 1, "presentation_semantic_entry_count_delta": 0,
            "approved_sha256": sha256_file(paths["approved"]),
            "output_sha256": sha256_file(output_path),
            "ledger_sha256_after": sha256_file(ledger_path),
            "validation": {"passed": True, "case_fact_transfer": False},
        })
    closure = _read(paths["closure"])
    if closure.get("output_sha256") != sha256_file(output_path) or closure.get("semantic_entry_count_delta") != 1:
        raise NovelNewsError("NEWS_NOVEL_CLOSURE_INVALID", "Novel News export closure is invalid.")
    return {"request_id": request_id, "output_path": str(output_path), "output_name": output_path.name,
            "content_id": content_id, "presentation_id": presentation_id,
            "new_semantic_content_count_delta": 1, "remote_model_called": False}


def novel_news_status(*, pipeline_root: Path, request_id: str) -> dict[str, Any]:
    paths = _paths(pipeline_root.expanduser().resolve(), request_id)
    request = _read(paths["request"])
    if request.get("target_profile") != "news" or not request.get("selected_content"):
        raise NovelNewsError("NEWS_NOVEL_REQUEST_INVALID", "Not a Novel News Request.")
    source = _read(paths["source_plan"]) if paths["source_plan"].is_file() else None
    coverage = (source or {}).get("coverage") or {}
    context = _source_context(pipeline_root.expanduser().resolve(), request_id) if coverage.get("status") == "supported" else None
    stage = "source_plan" if not paths["source_plan"].is_file() else "generation"
    if source and coverage.get("status") != "supported":
        stage = "blocked"
    if paths["plan"].is_file():
        stage = "review"
    if paths["approved"].is_file():
        stage = "export"
    if paths["closure"].is_file():
        stage = "completed"
    return {
        "request_id": request_id, "mode": "novel_content", "stage": stage,
        "business_id": request.get("persona_id"), "speaker_id": request.get("speaker_persona"),
        "selected_content": request["selected_content"],
        "source_coverage": coverage if source else None,
        "beats": (_read(paths["plan"]).get("micro_information_beats") or []) if paths["plan"].is_file() else [],
        "approved_beats": (_read(paths["approved"]).get("micro_information_beats") or []) if paths["approved"].is_file() else [],
        "source_facts": {
            atom_id: atom["original_known_fact"]
            for atom_id, atom in (context["usable_atoms"] if context else {}).items()
        },
        "export": _read(paths["receipt"]) if paths["receipt"].is_file() else None,
        "created_by_user_id": request.get("created_by_user_id"),
        "created_by_phone": request.get("created_by_phone"),
    }


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("status", "generate", "review", "export"))
    parser.add_argument("--pipeline-root", type=Path, required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--actor")
    args = parser.parse_args()
    try:
        if args.operation == "status":
            result = novel_news_status(pipeline_root=args.pipeline_root, request_id=args.request_id)
        elif args.operation == "generate":
            result = generate_novel_news_plan(pipeline_root=args.pipeline_root, request_id=args.request_id, generated_by=args.actor)
        elif args.operation == "review":
            incoming = json.load(sys.stdin)
            result = review_novel_news_plan(
                pipeline_root=args.pipeline_root, request_id=args.request_id,
                decisions=incoming["decisions"], reviewer=str(args.actor or ""),
            )
        else:
            result = export_novel_news(pipeline_root=args.pipeline_root, request_id=args.request_id, exported_by=str(args.actor or ""))
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
    except (NovelNewsError, NewsDeliveryError, OSError, KeyError, ValueError) as exc:
        print(json.dumps({"ok": False, "code": getattr(exc, "code", "NEWS_NOVEL_OPERATION_FAILED"), "message": str(exc)}, ensure_ascii=False))
        raise SystemExit(2) from exc
