"""Generate one canonical Mix Generation Batch from the final V1.1.1 Content Plan.

Authority chain:
Generation Request -> Generation Source Plan -> Content Plan V1 candidate pool
-> Content Plan V1.1 -> final Content Plan V1.1.1 -> in-memory generation projection
-> existing generate_mix_scripts_v1.generate_batch -> Generation Batch -> STOP.

Only Script Generation may call the remote model in this stage. This operation never
approves content, never exports Excel, and never writes the Content Ledger.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Callable

import resolve_generation_content_plan_v1 as content_plan_runtime
from content_quality_v1 import (
    PLAN_SCHEMA_VERSION,
    canonical_sha256,
    fact_atom_matches_text,
    normalize_text,
    presentation_signature,
    text_similarity,
    resolve_effective_content_gate_decision,
    write_new_json,
)
from customer_onboarding_analysis_v1 import load_deepseek_runtime_config
from generate_mix_scripts_v1 import (
    SCHEMA_VERSION as GENERATION_BATCH_SCHEMA_VERSION,
    generate_batch,
    read_json as generator_read_json,
    validate_content_plan_input,
    write_batch,
    write_review_pack_for_existing_batch,
)
from generation_request_handoff_v1 import _business_generation_lock
import generation_recovery_v1 as recovery


FINAL_CONTENT_PLAN_SCHEMA = "content-plan-v1.1.1"
SCRIPT_GENERATION_CONTRACT_SCHEMA = "script-generation-contract-v1.0"


class GenerationBatchResolutionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GenerationBatchResolutionError(
            "GENERATION_BATCH_ARTIFACT_INVALID",
            f"Cannot read JSON artifact: {path}",
        ) from exc
    if not isinstance(value, dict):
        raise GenerationBatchResolutionError(
            "GENERATION_BATCH_ARTIFACT_INVALID",
            f"Artifact must be a JSON object: {path}",
        )
    return value


def sha256_file(path: Path) -> str:
    return content_plan_runtime.sha256_file(path)


def final_plan_paths(
    pipeline_root: Path,
    request_id: str,
) -> tuple[Path, Path, Path]:
    root = pipeline_root / "data" / "content_plans" / request_id
    return (
        root / "content_plan_v1.json",
        root / "content_plan_v1_1.json",
        root / "content_plan_v1_1_1.json",
    )


def load_and_validate_final_content_plan(
    *,
    pipeline_root: Path,
    request_id: str,
    request: dict[str, Any],
    context: dict[str, Any],
    closure_memory: dict[str, Any],
    runtime_contract: dict[str, Any],
) -> tuple[
    Path,
    dict[str, Any],
    Path,
    dict[str, Any],
    Path,
    dict[str, Any],
]:
    v1_path, v1_1_path, final_path = final_plan_paths(
        pipeline_root,
        request_id,
    )
    for path, label in (
        (v1_path, "Content Plan V1"),
        (v1_1_path, "Content Plan V1.1"),
        (final_path, "Content Plan V1.1.1"),
    ):
        if not path.is_file():
            raise GenerationBatchResolutionError(
                "FINAL_CONTENT_PLAN_REQUIRED",
                f"{label} is required before Script Generation: {path}",
            )

    v1_plan = read_json(v1_path)
    v1_1_plan = read_json(v1_1_path)
    final_plan = read_json(final_path)

    if final_plan.get("schema_version") != FINAL_CONTENT_PLAN_SCHEMA:
        raise GenerationBatchResolutionError(
            "FINAL_CONTENT_PLAN_INVALID",
            "Script Generation requires content-plan-v1.1.1.",
        )
    if str(final_plan.get("request_id") or "") != request_id:
        raise GenerationBatchResolutionError(
            "FINAL_CONTENT_PLAN_LINEAGE_MISMATCH",
            "Final Content Plan request_id does not match the Generation Request.",
        )

    try:
        content_plan_runtime.validate_final_plan(
            plan=final_plan,
            request=context["request"],
            v1_1_path=v1_1_path,
            closure_memory=closure_memory,
            runtime_contract=runtime_contract,
        )
    except Exception as exc:
        raise GenerationBatchResolutionError(
            "FINAL_CONTENT_PLAN_VALIDATION_FAILED",
            f"Final V1.1.1 Content Plan failed canonical validation: {exc}",
        ) from exc

    lineage = final_plan.get("lineage") or {}
    preserved = lineage.get("preserved_source_artifacts") or {}
    if preserved.get("content_plan_v1") != sha256_file(v1_path):
        raise GenerationBatchResolutionError(
            "FINAL_CONTENT_PLAN_LINEAGE_MISMATCH",
            "Final Content Plan does not preserve the current V1 candidate-plan SHA.",
        )
    if lineage.get("source_v1_1_content_plan_sha256") != sha256_file(v1_1_path):
        raise GenerationBatchResolutionError(
            "FINAL_CONTENT_PLAN_LINEAGE_MISMATCH",
            "Final Content Plan does not reference the current V1.1 plan SHA.",
        )

    remote_source = final_plan.get("source_remote_planning") or {}
    if remote_source.get("source_content_plan_v1_sha256") != sha256_file(v1_path):
        raise GenerationBatchResolutionError(
            "FINAL_CONTENT_PLAN_LINEAGE_MISMATCH",
            "Final Content Plan remote-planning lineage does not match V1.",
        )

    selected = final_plan.get("selected_concepts") or []
    capacity = final_plan.get("capacity") or {}
    if not isinstance(selected, list) or not selected:
        raise GenerationBatchResolutionError(
            "FINAL_CONTENT_PLAN_EMPTY",
            "Final Content Plan has no production-eligible selected Concepts.",
        )
    if int(capacity.get("selected_quantity") or 0) != len(selected):
        raise GenerationBatchResolutionError(
            "FINAL_CONTENT_PLAN_QUANTITY_INVALID",
            "Final Content Plan selected quantity is inconsistent.",
        )
    if capacity.get("padding_generated") is not False:
        raise GenerationBatchResolutionError(
            "FINAL_CONTENT_PLAN_PADDING_FORBIDDEN",
            "Final Content Plan must not contain Padding.",
        )
    for concept in selected:
        if concept.get("v1_1_1_gate_decision") != "high_quality_novel":
            raise GenerationBatchResolutionError(
                "FINAL_CONTENT_PLAN_INVALID_SELECTION",
                (
                    "Final Content Plan contains a Concept that did not pass "
                    "the V1.1.1 gate."
                ),
            )
        material = concept.get("material_information_gain_v1_1_1") or {}
        if material.get("material_information_gain") is not True:
            raise GenerationBatchResolutionError(
                "FINAL_CONTENT_PLAN_INVALID_SELECTION",
                "Selected Concept lacks Material Information Gain.",
            )

    return v1_path, v1_plan, v1_1_path, v1_1_plan, final_path, final_plan


def _source_plan_rotation(source_plan: dict[str, Any]) -> list[str]:
    eligible = {
        str(item.get("case_id") or "")
        for item in source_plan.get("eligible_case_pool") or []
        if str(item.get("case_id") or "")
    }
    rotation = [
        str(case_id)
        for case_id in (source_plan.get("rotation") or {}).get(
            "case_rotation_order",
            [],
        )
        if str(case_id)
    ]
    if not rotation:
        rotation = sorted(eligible)
    if not rotation or any(case_id not in eligible for case_id in rotation):
        raise GenerationBatchResolutionError(
            "SCRIPT_CASE_ROTATION_INVALID",
            "Generation Source Plan Case rotation cannot be resolved safely.",
        )
    return rotation


def _material_atom_index(
    closure_memory: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    catalog = closure_memory.get("fact_atom_catalog") or []
    if not isinstance(catalog, list):
        raise GenerationBatchResolutionError(
            "SCRIPT_FACT_ATOM_AUTHORITY_INVALID",
            "V1.1.1 closure memory has no valid Fact Atom catalog.",
        )
    by_id: dict[str, dict[str, Any]] = {}
    for atom in catalog:
        if not isinstance(atom, dict):
            continue
        atom_id = str(atom.get("fact_atom_id") or "")
        if atom_id:
            by_id[atom_id] = atom
    return by_id


def build_generation_content_plan_projection(
    *,
    context: dict[str, Any],
    source_plan: dict[str, Any],
    v1_plan: dict[str, Any],
    final_plan: dict[str, Any],
    final_plan_path: Path,
    closure_memory: dict[str, Any],
    runtime_contract: dict[str, Any],
) -> dict[str, Any]:
    """Create a non-persisted V1-compatible view backed by final V1.1.1 Authority."""
    selected_source = final_plan.get("selected_concepts") or []
    rotation = _source_plan_rotation(source_plan)
    atom_by_id = _material_atom_index(closure_memory)
    selected_pattern_id = str(
        ((source_plan.get("selected_patterns") or [{}])[0]).get("pattern_id") or ""
    )
    if not selected_pattern_id:
        raise GenerationBatchResolutionError(
            "SCRIPT_PATTERN_AUTHORITY_INVALID",
            "Generation Source Plan has no selected Approved Pattern.",
        )

    material_centers_by_concept: dict[str, list[str]] = {}
    for concept in selected_source:
        concept_id = str(concept.get("concept_id") or "")
        material = concept.get("material_information_gain_v1_1_1") or {}
        refs = [
            str(ref)
            for ref in material.get("novel_primary_fact_atom_refs") or []
            if str(ref)
        ]
        if not concept_id or not refs:
            raise GenerationBatchResolutionError(
                "SCRIPT_MATERIAL_CENTER_REQUIRED",
                f"Selected Concept lacks a novel primary Fact Atom: {concept_id or '<missing>'}",
            )
        missing = [ref for ref in refs if ref not in atom_by_id]
        if missing:
            raise GenerationBatchResolutionError(
                "SCRIPT_FACT_ATOM_AUTHORITY_INVALID",
                "Selected Concept references missing Fact Atom(s): " + ", ".join(missing),
            )
        material_centers_by_concept[concept_id] = refs

    selected: list[dict[str, Any]] = []
    for index, source in enumerate(selected_source):
        concept = copy.deepcopy(source)
        concept_id = str(concept["concept_id"])
        case_id = rotation[index % len(rotation)]
        own_refs = material_centers_by_concept[concept_id]
        other_refs = sorted(
            {
                ref
                for other_id, refs in material_centers_by_concept.items()
                if other_id != concept_id
                for ref in refs
                if ref not in own_refs
            }
        )

        own_centers = [
            {
                "fact_atom_ref": ref,
                "normalized_meaning": atom_by_id[ref].get("normalized_meaning"),
                "original_known_fact": atom_by_id[ref].get("original_known_fact"),
            }
            for ref in own_refs
        ]
        other_centers = [
            {
                "fact_atom_ref": ref,
                "normalized_meaning": atom_by_id[ref].get("normalized_meaning"),
                "original_known_fact": atom_by_id[ref].get("original_known_fact"),
            }
            for ref in other_refs
        ]

        constraints = copy.deepcopy(concept.get("generation_constraints") or {})
        constraints.update(
            {
                "final_quality_baseline": "v1.1.1",
                "one_primary_material_center_only": True,
                "must_express_selected_material_centers": own_centers,
                "must_not_absorb_other_selected_material_centers": other_centers,
                "do_not_merge_with_another_selected_concept": True,
                "case_facts_must_not_transfer": True,
                "case_is_structural_reference_only": True,
            }
        )

        concept["case_structural_ref"] = case_id
        concept["pattern_ref"] = selected_pattern_id
        concept["primary_fact_atom_refs"] = list(
            (concept.get("material_information_gain_v1_1_1") or {}).get(
                "primary_fact_atom_refs",
                [],
            )
        )
        concept["new_information_units"] = list(own_refs)
        concept["generation_constraints"] = constraints
        concept["legacy_v1_novelty_summary"] = copy.deepcopy(
            concept.get("novelty_summary")
        )
        concept["novelty_summary"] = {
            "decision": "novel",
            "hard_duplicate": False,
            "uncertain": False,
            "policy": "content_quality_v1_1_1_material_information_gain",
            "material_information_gain": True,
            "reason": (
                concept.get("material_information_gain_v1_1_1") or {}
            ).get("reason"),
        }
        concept["editorial_score_summary"] = copy.deepcopy(
            concept.get("editorial_score_v1_1_1") or {}
        )
        concept["presentation_signature"] = presentation_signature(
            concept,
            final_plan.get("speaker_id"),
            final_plan.get("speaker_type"),
        )
        selected.append(concept)

    final_capacity = final_plan.get("capacity") or {}
    projection = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "quality_engine_version": final_plan.get("quality_engine_version"),
        "created_at": final_plan.get("created_at"),
        "request_id": final_plan.get("request_id"),
        "business_id": final_plan.get("business_id"),
        "speaker_id": final_plan.get("speaker_id"),
        "speaker_type": final_plan.get("speaker_type"),
        "profile": final_plan.get("profile") or context["request"].get("profile"),
        "target_profile": final_plan.get("target_profile")
        or context["request"].get("target_profile")
        or context["request"].get("profile"),
        "reuse_intent_contract": copy.deepcopy(
            v1_plan.get("reuse_intent_contract") or {}
        ),
        "candidate_pool": {
            "configured_size": (v1_plan.get("candidate_pool") or {}).get(
                "configured_size"
            ),
            "received_size": (v1_plan.get("candidate_pool") or {}).get(
                "received_size"
            ),
            "authority_valid_size": len(selected),
            "candidates": selected,
        },
        "editorial_ranking": {
            "policy": "final_v1_1_1_generation_projection",
            "minimum_editorial_score": (
                final_plan.get("editorial_ranking_v1_1_1") or {}
            ).get("minimum_editorial_score"),
            "ranked_high_quality_novel_candidates": selected,
        },
        "capacity": {
            "requested_quantity": final_capacity.get("requested_quantity"),
            "high_quality_novel_capacity": final_capacity.get(
                "high_quality_novel_capacity"
            ),
            "selected_quantity": len(selected),
            "status": final_capacity.get("status"),
            "padding_generated": False,
        },
        "selected_concepts": selected,
        "batch_editorial_summary": {
            "quality_baseline": "v1.1.1",
            "selected_count": len(selected),
            "average_editorial_score": (
                round(
                    sum(
                        float(
                            (item.get("editorial_score_v1_1_1") or {}).get(
                                "weighted_total"
                            )
                            or 0
                        )
                        for item in selected
                    )
                    / len(selected),
                    4,
                )
                if selected
                else 0.0
            ),
            "material_information_gain_required": True,
        },
        "planning_call": copy.deepcopy(v1_plan.get("planning_call") or {}),
        "lineage": {
            "persona": {
                "path": str(context["paths"]["persona"]),
                "sha256": sha256_file(context["paths"]["persona"]),
            },
            "speaker_persona": {
                "path": str(context["paths"]["speaker_persona"]),
                "sha256": sha256_file(context["paths"]["speaker_persona"]),
            },
            "request": {
                "path": str(context["paths"]["request"]),
                "sha256": sha256_file(context["paths"]["request"]),
            },
            "source_plan": {
                "path": str(context["paths"]["source_plan"]),
                "sha256": sha256_file(context["paths"]["source_plan"]),
            },
            "content_ledger_sha256": canonical_sha256(closure_memory),
            "approved_pattern_id": selected_pattern_id,
            "eligible_case_ids": _source_plan_rotation(source_plan),
            "final_content_plan_v1_1_1": {
                "path": str(final_plan_path.resolve()),
                "sha256": sha256_file(final_plan_path),
            },
        },
        "authority": {
            "final_v1_1_1_selection_is_topic_authority": True,
            "case_assignment_after_final_selection": True,
            "case_facts_transferred": False,
            "pattern_effectiveness_used": False,
            "external_research_used": False,
            "human_approval_performed": False,
        },
        "validation": {
            "passed": True,
            "selected_not_greater_than_requested": len(selected)
            <= int(final_capacity.get("requested_quantity") or 0),
            "no_padding": True,
            "all_selected_high_quality_novel": True,
            "case_assignment_after_selection": True,
        },
        "planning_runtime_contract": runtime_contract,
        "generation_projection": {
            "schema_version": "content-plan-generation-projection-v1.0",
            "canonical_final_content_plan_sha256": sha256_file(final_plan_path),
            "persisted": False,
            "purpose": "compatibility_view_for_existing_mix_script_generator",
        },
    }

    try:
        validate_content_plan_input(
            context,
            projection,
            closure_memory,
        )
    except Exception as exc:
        raise GenerationBatchResolutionError(
            "SCRIPT_GENERATION_PROJECTION_INVALID",
            f"Final V1.1.1 generation projection failed canonical validation: {exc}",
        ) from exc

    return projection


def _material_text_spans(value: Any) -> list[str]:
    """Bounded text spans for deterministic evidence checks.

    Full narration is retained, while sentences/clauses and adjacent clause pairs
    avoid the false-negative behavior of comparing one short Fact Atom against an
    entire long narration.
    """
    text = str(value or "").strip()
    if not text:
        return []
    parts = [
        item.strip()
        for item in re.split(r"[。！？!?；;，,：:\n]+", text)
        if normalize_text(item)
    ]
    spans = [text, *parts]
    spans.extend(
        parts[index] + parts[index + 1]
        for index in range(len(parts) - 1)
    )
    unique: list[str] = []
    seen: set[str] = set()
    for item in spans:
        key = normalize_text(item)
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _distinctive_material_evidence(
    target_text: Any,
    contrast_texts: list[Any],
    narration: Any,
) -> dict[str, Any]:
    """Find target-only lexical evidence instead of shared category wording.

    This is deliberately contrastive: shared words such as "皮肤/毛发/状态" do not
    prove that one selected Concept absorbed another. We only count matched runs
    that exist in the target material center but not in any other selected center.
    """
    target = normalize_text(target_text)
    contrast = [normalize_text(value) for value in contrast_texts if normalize_text(value)]
    text = normalize_text(narration)
    if not target or not text:
        return {
            "strong": False,
            "phrases": [],
            "matched_distinctive_characters": 0,
        }

    matcher = __import__("difflib").SequenceMatcher(None, target, text)
    phrases: list[str] = []
    for block in matcher.get_matching_blocks():
        if block.size < 2:
            continue
        phrase = target[block.a : block.a + block.size]
        if any(phrase in other for other in contrast):
            continue
        phrases.append(phrase)

    # Remove phrases fully contained in a longer retained phrase.
    phrases = sorted(set(phrases), key=lambda value: (-len(value), value))
    retained: list[str] = []
    for phrase in phrases:
        if any(phrase in old for old in retained):
            continue
        retained.append(phrase)

    matched_chars = sum(len(value) for value in retained)
    strong = (
        any(len(value) >= 4 for value in retained)
        or sum(len(value) >= 2 for value in retained) >= 2
        or matched_chars >= 5
    )
    return {
        "strong": strong,
        "phrases": retained,
        "matched_distinctive_characters": matched_chars,
    }


def _atom_narration_evidence(
    atom: dict[str, Any],
    narration: Any,
) -> dict[str, Any]:
    spans = _material_text_spans(narration)
    matches: list[dict[str, Any]] = []
    best_similarity = 0.0
    for span in spans:
        matched, explicitness = fact_atom_matches_text(atom, span)
        similarity = text_similarity(
            atom.get("normalized_meaning") or atom.get("original_known_fact"),
            span,
        )
        best_similarity = max(best_similarity, float(similarity))
        if matched:
            matches.append(
                {
                    "span": span,
                    "explicitness": explicitness,
                    "similarity": similarity,
                }
            )
    return {
        "deterministic_match": bool(matches),
        "matches": matches,
        "best_similarity": round(best_similarity, 6),
    }


def validate_material_center_preservation(
    *,
    batch: dict[str, Any],
    projection: dict[str, Any],
    closure_memory: dict[str, Any],
) -> dict[str, Any]:
    """Validate final-topic preservation without pretending lexical matching is semantics.

    Hard machine authority already guarantees exact final central_claim and semantic
    signature. Here we add:
      - deterministic narration evidence when available;
      - contrastive detection that one selected script clearly absorbs another
        selected Concept's distinctive material center;
      - a Human Review flag, rather than a false hard failure, when a natural
        paraphrase cannot be deterministically matched to its own Fact Atom.
    """
    atom_by_id = _material_atom_index(closure_memory)
    concept_by_id = {
        str(item.get("concept_id") or ""): item
        for item in projection.get("selected_concepts") or []
    }
    selected_ids = list(concept_by_id)
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    human_review_flags: list[str] = []

    for item in batch.get("contents") or []:
        concept_id = str(item.get("concept_ref") or "")
        concept = concept_by_id.get(concept_id)
        if concept is None:
            errors.append(f"unknown_generated_concept:{concept_id}")
            continue

        narration = str(item.get("narration") or "")
        constraints = concept.get("generation_constraints") or {}
        own_centers = constraints.get("must_express_selected_material_centers") or []
        other_centers = constraints.get(
            "must_not_absorb_other_selected_material_centers"
        ) or []

        other_texts = [
            str(center.get("normalized_meaning") or center.get("original_known_fact") or "")
            for center in other_centers
        ]

        own_results: list[dict[str, Any]] = []
        own_deterministic = True
        for center in own_centers:
            atom_id = str(center.get("fact_atom_ref") or "")
            atom = atom_by_id.get(atom_id)
            if atom is None:
                errors.append(f"selected_material_atom_missing:{concept_id}:{atom_id}")
                own_deterministic = False
                continue

            evidence = _atom_narration_evidence(atom, narration)
            distinctive = _distinctive_material_evidence(
                atom.get("normalized_meaning") or atom.get("original_known_fact"),
                other_texts,
                narration,
            )
            deterministic = (
                evidence["deterministic_match"] or distinctive["strong"]
            )
            own_results.append(
                {
                    "fact_atom_ref": atom_id,
                    "deterministic_narration_match": deterministic,
                    "fact_atom_match": evidence,
                    "contrastive_distinctive_evidence": distinctive,
                }
            )
            if not deterministic:
                own_deterministic = False

        if not own_deterministic:
            flag = (
                "material_center_narration_semantic_match_requires_human_review:"
                + concept_id
            )
            human_review_flags.append(flag)
            item_flags = set(item.get("potential_review_flags") or [])
            item_flags.add("material_center_narration_semantic_match_uncertain")
            item["potential_review_flags"] = sorted(item_flags)

        cross_results: list[dict[str, Any]] = []
        cross_pass = True
        own_texts = [
            str(center.get("normalized_meaning") or center.get("original_known_fact") or "")
            for center in own_centers
        ]
        for center in other_centers:
            atom_id = str(center.get("fact_atom_ref") or "")
            atom = atom_by_id.get(atom_id)
            if atom is None:
                errors.append(f"other_selected_material_atom_missing:{concept_id}:{atom_id}")
                cross_pass = False
                continue

            evidence = _atom_narration_evidence(atom, narration)
            distinctive = _distinctive_material_evidence(
                atom.get("normalized_meaning") or atom.get("original_known_fact"),
                own_texts,
                narration,
            )
            absorbed = (
                evidence["deterministic_match"] and distinctive["strong"]
            ) or distinctive["strong"]
            cross_results.append(
                {
                    "fact_atom_ref": atom_id,
                    "absorbed": absorbed,
                    "fact_atom_match": evidence,
                    "contrastive_distinctive_evidence": distinctive,
                }
            )
            if absorbed:
                cross_pass = False
                flag = (
                    "cross_concept_material_overlap_requires_human_review:"
                    + concept_id
                    + ":"
                    + atom_id
                )
                human_review_flags.append(flag)
                item_flags = set(item.get("potential_review_flags") or [])
                item_flags.add(
                    "cross_concept_material_overlap_requires_human_review"
                )
                item["potential_review_flags"] = sorted(item_flags)

        records.append(
            {
                "concept_ref": concept_id,
                "own_material_centers": own_results,
                "own_material_center_metadata_preserved": True,
                "own_material_center_deterministic_narration_match": own_deterministic,
                "other_selected_material_centers": cross_results,
                "cross_concept_material_center_isolation_passed": cross_pass,
            }
        )

    generated_ids = [
        str(item.get("concept_ref") or "") for item in batch.get("contents") or []
    ]
    if len(generated_ids) != len(set(generated_ids)):
        errors.append("duplicate_generated_concept_ref")
    if any(concept_id not in selected_ids for concept_id in generated_ids):
        errors.append("generated_concept_outside_final_selection")

    return {
        "passed": not errors,
        "records": records,
        "errors": sorted(set(errors)),
        "human_review_flags": sorted(set(human_review_flags)),
        "deterministic_narration_match_is_not_semantic_authority": True,
        "hard_authority_basis": (
            "exact_final_central_claim_and_semantic_signature_plus_fact_authority"
        ),
        "cross_concept_overlap_is_human_review_signal": True,
    }

def augment_and_validate_batch(
    *,
    batch: dict[str, Any],
    context: dict[str, Any],
    request: dict[str, Any],
    final_plan_path: Path,
    final_plan: dict[str, Any],
    projection: dict[str, Any],
    closure_memory: dict[str, Any],
    v1_path: Path,
    v1_1_path: Path,
) -> dict[str, Any]:
    if batch.get("schema_version") != GENERATION_BATCH_SCHEMA_VERSION:
        raise GenerationBatchResolutionError(
            "GENERATION_BATCH_SCHEMA_INVALID",
            "Generated Batch schema_version is invalid.",
        )
    if str(batch.get("request_id") or "") != str(request.get("request_id") or ""):
        raise GenerationBatchResolutionError(
            "GENERATION_BATCH_LINEAGE_MISMATCH",
            "Generated Batch request_id does not match the Generation Request.",
        )
    if str(batch.get("profile") or "") != "mix":
        raise GenerationBatchResolutionError(
            "GENERATION_BATCH_PROFILE_INVALID",
            "Script Generation V1 currently supports Mix only.",
        )

    selected = projection.get("selected_concepts") or []
    selected_ids = [str(item.get("concept_id") or "") for item in selected]
    generated_ids = [
        str(item.get("concept_ref") or "") for item in batch.get("contents") or []
    ]
    if any(concept_id not in selected_ids for concept_id in generated_ids):
        raise GenerationBatchResolutionError(
            "GENERATION_BATCH_CONCEPT_SUBSTITUTION",
            "Generated Batch contains a Concept outside the final V1.1.1 selection.",
        )

    projection_sha = canonical_sha256(projection)
    expected_ledger_sha = canonical_sha256(closure_memory)
    batch_plan_ref = batch.get("content_plan_ref") or {}
    if batch_plan_ref.get("sha256") != projection_sha:
        raise GenerationBatchResolutionError(
            "GENERATION_BATCH_LINEAGE_MISMATCH",
            "Generated Batch does not reference the in-memory generation projection.",
        )
    if (
        ((batch.get("lineage") or {}).get("content_ledger") or {}).get("sha256")
        != expected_ledger_sha
    ):
        raise GenerationBatchResolutionError(
            "GENERATION_BATCH_LINEAGE_MISMATCH",
            "Generated Batch historical-memory SHA does not match V1.1.1 closure memory.",
        )

    final_by_id = {
        str(item.get("concept_id") or ""): item
        for item in final_plan.get("selected_concepts") or []
    }
    projection_by_id = {
        str(item.get("concept_id") or ""): item for item in selected
    }
    for item in batch.get("contents") or []:
        concept_id = str(item.get("concept_ref") or "")
        final_concept = final_by_id[concept_id]
        projection_concept = projection_by_id[concept_id]
        if item.get("central_claim") != final_concept.get("central_claim"):
            raise GenerationBatchResolutionError(
                "GENERATION_BATCH_TOPIC_DRIFT",
                f"Generated script changed the final Central Claim: {concept_id}",
            )
        if item.get("semantic_signature") != final_concept.get("semantic_signature"):
            raise GenerationBatchResolutionError(
                "GENERATION_BATCH_TOPIC_DRIFT",
                f"Generated script changed the final Semantic Signature: {concept_id}",
            )
        if str((item.get("case_reference") or {}).get("case_id") or "") != str(
            projection_concept.get("case_structural_ref") or ""
        ):
            raise GenerationBatchResolutionError(
                "GENERATION_BATCH_CASE_LINEAGE_MISMATCH",
                f"Generated script Case assignment drifted: {concept_id}",
            )
        item["editorial_summary"] = copy.deepcopy(
            final_concept.get("editorial_score_v1_1_1") or {}
        )
        item["material_information_gain_v1_1_1"] = copy.deepcopy(
            final_concept.get("material_information_gain_v1_1_1") or {}
        )
        item["final_quality_gate"] = final_concept.get("v1_1_1_gate_decision")

    atom_validation = validate_material_center_preservation(
        batch=batch,
        projection=projection,
        closure_memory=closure_memory,
    )
    if not atom_validation["passed"]:
        raise GenerationBatchResolutionError(
            "GENERATION_BATCH_MATERIAL_CENTER_DRIFT",
            "Script Material Information boundary failed: "
            + "; ".join(atom_validation["errors"]),
        )

    batch["script_generation_contract"] = {
        "schema_version": SCRIPT_GENERATION_CONTRACT_SCHEMA,
        "quality_baseline": "v1.1.1",
        "final_content_plan_ref": {
            "path": str(final_plan_path.resolve()),
            "sha256": sha256_file(final_plan_path),
            "schema_version": final_plan.get("schema_version"),
        },
        "generation_projection_sha256": projection_sha,
        "content_memory_sha256": expected_ledger_sha,
        "selected_concept_ids": selected_ids,
        "case_assignment_policy": "source_plan_rotation_after_final_v1_1_1_selection",
        "material_center_validation": atom_validation,
        "stop_boundary": "generation_batch_ready_for_human_review",
    }
    lineage = batch.setdefault("lineage", {})
    lineage["candidate_content_plan_v1"] = {
        "path": str(v1_path.resolve()),
        "sha256": sha256_file(v1_path),
    }
    lineage["content_plan_v1_1"] = {
        "path": str(v1_1_path.resolve()),
        "sha256": sha256_file(v1_1_path),
    }
    lineage["final_content_plan_v1_1_1"] = {
        "path": str(final_plan_path.resolve()),
        "sha256": sha256_file(final_plan_path),
    }
    lineage["generation_content_plan_projection"] = {
        "persisted": False,
        "sha256": projection_sha,
    }

    batch.setdefault("authority", {}).update(
        {
            "final_content_plan_v1_1_1_is_script_topic_authority": True,
            "script_generation_performed": True,
            "human_review_required": True,
            "auto_approved": False,
            "content_ledger_written": False,
            "excel_exported": False,
        }
    )
    batch.setdefault("validation", {}).update(
        {
            "final_content_plan_v1_1_1_preserved": True,
            "no_concept_substitution": set(generated_ids).issubset(selected_ids),
            "one_output_max_per_concept": len(generated_ids) == len(set(generated_ids)),
            "material_centers_preserved": atom_validation["passed"],
            "material_center_narration_match_human_review_flags": atom_validation.get(
                "human_review_flags", []
            ),
            "cross_concept_material_center_isolation_passed": all(
                record["cross_concept_material_center_isolation_passed"]
                for record in atom_validation["records"]
            ),
            "no_auto_approval": True,
            "no_excel_export": True,
            "content_ledger_unchanged": True,
        }
    )
    from creative_style_v1 import bind_batch
    bind_batch(batch, request, context["persona"], context.get("speaker_persona"), selected)
    subset = recovery.accepted_subset(batch, selected_ids)
    if subset is not None:
        batch['accepted_subset'] = subset
    return batch


def validate_existing_batch(
    *,
    batch: dict[str, Any],
    batch_path: Path,
    request: dict[str, Any],
    final_plan_path: Path,
    final_plan: dict[str, Any],
    projection: dict[str, Any],
    closure_memory: dict[str, Any],
) -> None:
    from creative_style_v1 import validate_batch
    validate_batch(batch)
    if batch.get("schema_version") != GENERATION_BATCH_SCHEMA_VERSION:
        raise GenerationBatchResolutionError(
            "GENERATION_BATCH_SCHEMA_INVALID",
            "Existing Generation Batch schema is invalid.",
        )
    if str(batch.get("request_id") or "") != str(request.get("request_id") or ""):
        raise GenerationBatchResolutionError(
            "GENERATION_BATCH_LINEAGE_MISMATCH",
            "Existing Generation Batch belongs to another Request.",
        )

    contract = batch.get("script_generation_contract") or {}
    final_ref = contract.get("final_content_plan_ref") or {}
    if final_ref.get("sha256") != sha256_file(final_plan_path):
        raise GenerationBatchResolutionError(
            "GENERATION_BATCH_LINEAGE_MISMATCH",
            "Existing Generation Batch references a different final Content Plan.",
        )
    if contract.get("generation_projection_sha256") != canonical_sha256(projection):
        raise GenerationBatchResolutionError(
            "GENERATION_BATCH_LINEAGE_MISMATCH",
            "Existing Generation Batch generation-projection SHA has drifted.",
        )
    if contract.get("content_memory_sha256") != canonical_sha256(closure_memory):
        raise GenerationBatchResolutionError(
            "GENERATION_BATCH_LINEAGE_MISMATCH",
            "Existing Generation Batch historical-memory SHA has drifted.",
        )

    selected_ids = [
        str(item.get("concept_id") or "")
        for item in final_plan.get("selected_concepts") or []
    ]
    generated_ids = [
        str(item.get("concept_ref") or "") for item in batch.get("contents") or []
    ]
    if any(value not in selected_ids for value in generated_ids):
        raise GenerationBatchResolutionError(
            "GENERATION_BATCH_CONCEPT_SUBSTITUTION",
            "Existing Generation Batch contains a non-selected Concept.",
        )
    if len(generated_ids) != len(set(generated_ids)):
        raise GenerationBatchResolutionError(
            "GENERATION_BATCH_CONCEPT_SUBSTITUTION",
            "Existing Generation Batch duplicates a selected Concept.",
        )
    if batch.get('accepted_subset') is not None:
        recovery.ready_for_review(batch, selected_ids)

    atom_validation = validate_material_center_preservation(
        batch=batch,
        projection=projection,
        closure_memory=closure_memory,
    )
    if not atom_validation["passed"]:
        raise GenerationBatchResolutionError(
            "GENERATION_BATCH_MATERIAL_CENTER_DRIFT",
            "Existing Generation Batch no longer satisfies Material Information boundaries.",
        )
    if not batch_path.is_file():
        raise GenerationBatchResolutionError(
            "GENERATION_BATCH_NOT_FOUND",
            "Existing Generation Batch path disappeared during validation.",
        )


def candidate_cache_path(
    pipeline_root: Path,
    request_id: str,
) -> Path:
    return (
        pipeline_root
        / "data"
        / "metrics"
        / "generation_requests"
        / request_id
        / "script_generation_candidate_batch_v1.json"
    )


from profile_compatibility_consumers_v1_1 import guarded as compatibility_guarded


@compatibility_guarded
def persist_candidate_batch(
    *,
    path: Path,
    request_id: str,
    final_plan_path: Path,
    projection: dict[str, Any],
    closure_memory: dict[str, Any],
    batch: dict[str, Any],
) -> None:
    artifact = {
        "schema_version": "script-generation-candidate-batch-v1.0",
        "request_id": request_id,
        "status": "diagnostic_candidate_not_canonical_generation_batch",
        "ledger_worthy": False,
        "human_approval_performed": False,
        "excel_exported": False,
        "final_content_plan_sha256": sha256_file(final_plan_path),
        "generation_projection_sha256": canonical_sha256(projection),
        "content_memory_sha256": canonical_sha256(closure_memory),
        "batch": batch,
    }
    if path.is_file():
        existing = read_json(path)
        if canonical_sha256(existing) != canonical_sha256(artifact):
            raise GenerationBatchResolutionError(
                "SCRIPT_GENERATION_CANDIDATE_CONFLICT",
                "A different diagnostic Script Generation candidate already exists.",
            )
        return
    try:
        if path.name == 'candidate.json':
            recovery.write_once(path, artifact)
        else:
            write_new_json(path, artifact)
    except FileExistsError:
        existing = read_json(path)
        if canonical_sha256(existing) != canonical_sha256(artifact):
            raise GenerationBatchResolutionError(
                "SCRIPT_GENERATION_CANDIDATE_CONFLICT",
                "Script Generation candidate was created concurrently with different content.",
            )


def load_candidate_batch(
    *,
    path: Path,
    request_id: str,
    final_plan_path: Path,
    projection: dict[str, Any],
    closure_memory: dict[str, Any],
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    artifact = read_json(path)
    if (
        artifact.get("schema_version")
        != "script-generation-candidate-batch-v1.0"
        or str(artifact.get("request_id") or "") != request_id
        or artifact.get("final_content_plan_sha256") != sha256_file(final_plan_path)
        or artifact.get("generation_projection_sha256")
        != canonical_sha256(projection)
        or artifact.get("content_memory_sha256")
        != canonical_sha256(closure_memory)
        or artifact.get("ledger_worthy") is not False
    ):
        raise GenerationBatchResolutionError(
            "SCRIPT_GENERATION_CANDIDATE_LINEAGE_MISMATCH",
            "Diagnostic Script Generation candidate lineage is invalid.",
        )
    batch = artifact.get("batch")
    if not isinstance(batch, dict):
        raise GenerationBatchResolutionError(
            "SCRIPT_GENERATION_CANDIDATE_INVALID",
            "Diagnostic Script Generation candidate has no Batch object.",
        )
    return batch

def result_from_batch(
    *,
    batch_path: Path,
    review_path: Path,
    batch: dict[str, Any],
    selected_concept_ids: list[str],
    recovered: bool,
    remote_model_called: bool,
    candidate_recovered: bool = False,
) -> dict[str, Any]:
    generated_ids = [
        str(item.get("concept_ref") or "") for item in batch.get("contents") or []
    ]
    attempts = list(batch.get("generation_attempts") or [])
    ready = recovery.ready_for_review(batch, selected_concept_ids)
    return {
        "ok": True,
        "request_id": batch.get("request_id"),
        "status": batch.get("status"),
        "generation_batch_path": str(batch_path.resolve()),
        "generation_batch_sha256": sha256_file(batch_path),
        "review_pack_path": str(review_path.resolve()),
        "quality_baseline": "v1.1.1",
        "selected_concept_ids": selected_concept_ids,
        "generated_concept_ids": generated_ids,
        "planned_quantity": len(selected_concept_ids),
        "generated_count": len(generated_ids),
        "model": batch.get("model"),
        "historical_remote_model_call_count": len(attempts),
        "remote_model_called": remote_model_called,
        "candidate_recovered": candidate_recovered,
        "recovered": recovered,
        "script_generation_performed": True,
        "generation_batch_created": not recovered,
        "ready_for_human_review": ready,
        "human_review_required": True,
        "human_approval_performed": False,
        "content_ledger_written": False,
        "excel_exported": False,
    }


def generation_snapshot(pipeline_root: Path, request_id: str, *, _partial_human_admission=False) -> dict[str, Any]:
    """Read-only native readiness. Artifact presence never grants review permission."""
    root = Path(pipeline_root).resolve()
    state = recovery.graph(root, request_id)
    path = state['batch']
    present = path.is_file()
    batch = read_json(path) if present else {}
    if present and (batch.get('schema_version') != GENERATION_BATCH_SCHEMA_VERSION or batch.get('request_id') != request_id):
        raise GenerationBatchResolutionError('GENERATION_BATCH_SCHEMA_INVALID', 'Invalid Generation Batch identity')
    ids = [str(x.get('concept_ref') or '') for x in batch.get('contents') or []]
    contract = batch.get('script_generation_contract') or {}
    selected = contract.get('selected_concept_ids') or []
    ready = bool(present and recovery.ready_for_review(batch, selected))
    execution_completed = ready
    generation_completed = ready and batch.get('validation', {}).get('passed') is True
    if ready:
        final = root / 'data/content_plans' / request_id / 'content_plan_v1_1_1.json'
        final_ref = contract.get('final_content_plan_ref') or {}
        if not final.is_file() or final_ref.get('sha256') != sha256_file(final):
            raise GenerationBatchResolutionError('GENERATION_BATCH_LINEAGE_MISMATCH', 'Final plan identity changed')
        if [str(x.get('concept_id') or '') for x in read_json(final).get('selected_concepts') or []] != selected:
            raise GenerationBatchResolutionError('GENERATION_BATCH_CONCEPT_SUBSTITUTION', 'Final selection changed')
        # Recheck exact historical source files, without substituting today's memory
        # for the frozen snapshot after a legitimate export has appended the Ledger.
        def lineage_refs(value):
            if isinstance(value, dict):
                expected = value.get('sha256') or value.get('file_sha256')
                if value.get('path') and expected:
                    yield value['path'], expected
                for child in value.values():
                    yield from lineage_refs(child)
            elif isinstance(value, list):
                for child in value:
                    yield from lineage_refs(child)
        for name, expected in lineage_refs(batch.get('lineage') or {}):
            source = Path(name).resolve()
            if not source.is_relative_to(root) or not source.is_file() or sha256_file(source) != expected:
                raise GenerationBatchResolutionError('GENERATION_BATCH_LINEAGE_MISMATCH', 'Generation source SHA changed')
        receipt_path = recovery.request_root(root, request_id) / 'generation_batch_approval_receipt.json'
        review_path = recovery.request_root(root, request_id) / 'generation_human_review_v2.json'
        partial_human = review_path.is_file() and not receipt_path.is_file()
        if partial_human:
            # Only native Human recovery may use this source for a write. The
            # ordinary Reader never treats a half Human bundle as approval or
            # re-enters planning memory through incomplete Approved history.
            human = read_json(review_path)
            if (human.get('schema_version') != 'generation-batch-review-v2.0' or
                    human.get('request_id') != request_id or human.get('batch_sha256') != sha256_file(path)):
                raise GenerationBatchResolutionError('GENERATION_BATCH_LINEAGE_MISMATCH', 'Partial Human review binds another source')
            if not _partial_human_admission:
                ready = False
        elif not receipt_path.is_file():
            inputs = generation_inputs(root, request_id)
            validate_existing_batch(batch=batch, batch_path=path, request=inputs['request'],
                final_plan_path=inputs['final_plan_path'], final_plan=inputs['final_plan'],
                projection=inputs['projection'], closure_memory=inputs['closure_memory'])
        else:
            approved_source = read_json(receipt_path).get('source_batch') or {}
            if Path(approved_source.get('path') or '').resolve() != path.resolve() or approved_source.get('sha256') != sha256_file(path):
                raise GenerationBatchResolutionError('GENERATION_BATCH_LINEAGE_MISMATCH', 'Human history does not bind this Batch')
    pending = state['pending']
    terminal = state['result']
    if pending:
        ready = False
        execution_completed = False
        generation_completed = False
    recovery_state = ('human_receipt_pending' if present and (recovery.request_root(root, request_id) / 'generation_human_review_v2.json').is_file() and not (recovery.request_root(root, request_id) / 'generation_batch_approval_receipt.json').is_file() else 'pending' if pending else ('review_required' if ready else
        ((terminal or {}).get('outcome') or ('retry_available' if present and recovery.transport_failure(batch) else 'not_generated' if not present else 'blocked'))))
    review_path = path.parent / 'generation_review_pack_v1.md'
    recover_artifacts = ready and not review_path.is_file()
    if recover_artifacts:
        ready = False
        recovery_state = 'review_pack_missing'
    if not review_path.is_file():
        generation_completed = False
        execution_completed = False
    try:
        recovery.require_unreviewed(root, request_id)
        retry_available = bool(present and recovery.transport_failure(read_json(state['anchor'])) and not ready)
    except recovery.RecoveryError:
        retry_available = False
    return {'reader_version': recovery.READER, 'artifact_present': present,
        # Source/graph checks above establish a persisted machine result. A
        # partial Human bundle suppresses review admission, never the already
        # completed execution or its explicit unfilled quantity.
        'execution_completed':execution_completed,
        'generation_completed':generation_completed,
        'ready_for_human_review': ready, 'recovery_state': recovery_state,
        'batch_ref': recovery.ref(root, path) if present else None,
        'head_ref': state['head_ref'],
        'review_pack_ref': recovery.ref(root, review_path) if review_path.is_file() else None,
        'pending_operation_id': pending['operation_id'] if pending else None,
        'pending_intent_sha256': recovery.file_sha(recovery.operation_root(root, request_id, pending['operation_id']) / 'intent.json') if pending else None,
        'can_retry': retry_available,
        'can_recover_artifacts': recover_artifacts,
        'batch': batch}


def generation_inputs(pipeline_root: Path, request_id: str):
    request_path, request, source_plan_path, source_plan = (
        content_plan_runtime.read_request_and_source_plan(
            pipeline_root,
            request_id,
        )
    )
    if request.get('lifecycle', {}).get('status') != 'created':
        raise GenerationBatchResolutionError('CONTENT_PLANNING_LIFECYCLE_CLOSED', 'Request lifecycle does not admit generation')
    quality_contract, quality_contract_source = (
        content_plan_runtime.content_quality_contract(request)
    )
    base_memory, content_memory_source = (
        content_plan_runtime.resolve_base_planning_memory(
            pipeline_root,
            request,
        )
    )
    context = content_plan_runtime.build_context(
        pipeline_root=pipeline_root,
        request_path=request_path,
        request=request,
        source_plan_path=source_plan_path,
        source_plan=source_plan,
        quality_contract=quality_contract,
    )
    runtime_contract = content_plan_runtime.build_runtime_contract(
        request_path=request_path,
        source_plan_path=source_plan_path,
        base_planning_memory=base_memory,
        content_memory_source=content_memory_source,
        quality_contract=quality_contract,
        quality_contract_source=quality_contract_source,
    )
    closure_memory = content_plan_runtime.build_closure_memory(
        base_memory=base_memory,
        context=context,
        content_memory_source=content_memory_source,
    )

    (
        v1_path,
        v1_plan,
        v1_1_path,
        _v1_1_plan,
        final_plan_path,
        final_plan,
    ) = load_and_validate_final_content_plan(
        pipeline_root=pipeline_root,
        request_id=request_id,
        request=request,
        context=context,
        closure_memory=closure_memory,
        runtime_contract=runtime_contract,
    )

    from creative_style_v1 import validate_concept
    for concept in final_plan.get("selected_concepts") or []:
        validate_concept(request, concept, context.get("speaker_persona"), context.get("persona"))
    projection = build_generation_content_plan_projection(
        context=context,
        source_plan=source_plan,
        v1_plan=v1_plan,
        final_plan=final_plan,
        final_plan_path=final_plan_path,
        closure_memory=closure_memory,
        runtime_contract=runtime_contract,
    )
    selected_concept_ids = [
        str(item.get("concept_id") or "")
        for item in projection.get("selected_concepts") or []
    ]

    return locals()


def recovery_bindings(root, inputs):
    from show_customer_status_v1 import resolve_current_persona, resolve_speaker_persona
    business = resolve_current_persona(root, inputs['request']['persona_id'], 'business')
    speaker_id = inputs['request'].get('speaker_persona')
    speaker = resolve_speaker_persona(root, business, speaker_id) if speaker_id else None
    lineage = inputs['request'].get('lineage') or {}
    if (business['file_sha256'] != (lineage.get('business_persona_ref') or {}).get('file_sha256')
            or (speaker and speaker['file_sha256'] != (lineage.get('speaker_persona_ref') or {}).get('file_sha256'))):
        raise recovery.RecoveryError('GENERATION_RECOVERY_SOURCE_CHANGED', 'Request does not bind the current approved Business/Speaker')
    ledger = root / 'data/content_ledgers' / inputs['request']['persona_id'] / 'content_ledger_v1.json'
    def snapshot_value(value):
        if isinstance(value, Path):
            return str(value.resolve())
        if isinstance(value, dict):
            return {key: snapshot_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [snapshot_value(item) for item in value]
        if isinstance(value, set):
            return sorted(snapshot_value(item) for item in value)
        return value
    return {'request_ref': recovery.ref(root, inputs['request_path']),
        'source_plan_ref': recovery.ref(root, inputs['source_plan_path']),
        'final_plan_ref': recovery.ref(root, inputs['final_plan_path']),
        'generation_projection_sha256': canonical_sha256(inputs['projection']),
        'content_memory_sha256': canonical_sha256(inputs['closure_memory']),
        'source_context_sha256': canonical_sha256(snapshot_value(inputs['context'])),
        'current_authority_sha256': canonical_sha256({'business': business['file_sha256'],
            'speaker': speaker['file_sha256'] if speaker else None,
            'constraints': business.get('production_constraints')}),
        'live_content_ledger_ref': recovery.ref(root, ledger) if ledger.is_file() else None,
        'selected_concept_ids': inputs['selected_concept_ids'],
        'compatibility_binding_sha256': canonical_sha256(inputs['source_plan'].get('profile_compatibility_v1_1'))}


def require_retry_scope(root, request_id, state, inputs):
    recovery.require_unreviewed(root, request_id)
    if not recovery.transport_failure(read_json(state['anchor'])):
        raise recovery.RecoveryError('GENERATION_RECOVERY_SCOPE_UNSUPPORTED', 'Only zero-output transport failure may retry')
    validate_existing_batch(batch=read_json(state['anchor']), batch_path=state['anchor'],
        request=inputs['request'], final_plan_path=inputs['final_plan_path'], final_plan=inputs['final_plan'],
        projection=inputs['projection'], closure_memory=inputs['closure_memory'])
    if state['result'] and state['result']['outcome'] == 'review_required':
        raise recovery.RecoveryError('GENERATION_RECOVERY_SCOPE_UNSUPPORTED', 'Successful generation cannot be replaced')


@compatibility_guarded
def preview_generation_recovery(*, pipeline_root, request_id, operation_id, actor, database_path, session_fingerprint):
    root = Path(pipeline_root).resolve()
    request = content_plan_runtime.read_request_and_source_plan(root, request_id)[1]
    with _business_generation_lock(root, request['persona_id']):
        state = recovery.graph(root, request_id)
        inputs = generation_inputs(root, request_id)
        require_retry_scope(root, request_id, state, inputs)
        if state['pending']:
            raise recovery.RecoveryError('GENERATION_RECOVERY_PENDING', 'Resume pending operation before a new retry')
        proof = recovery.authorization(database_path, actor, session_fingerprint)
        intent = {'schema_version': recovery.INTENT, 'request_id': request_id, 'operation_id': operation_id,
            'parent_ref': state['head_ref'], 'anchor_ref': recovery.ref(root, state['anchor']),
            'bindings': recovery_bindings(root, inputs), 'actor': actor, 'authorization': proof,
            'authorization_context_digest': recovery.digest({'actor': actor, 'authorization': proof})}
        # Preview is outside the effective attempt graph and grants no execution.
        preview = root / 'data/generation_recovery_previews' / request_id / operation_id / 'intent.json'
        recovery.operation_root(root, request_id, operation_id)  # validate identifiers first
        recovery.publish(preview, intent, recovery.INTENT)
        return {'operation_id': operation_id, 'preview_sha256': recovery.file_sha(preview), 'reader_version': recovery.READER}


@compatibility_guarded
def confirm_generation_recovery(*, pipeline_root, request_id, operation_id, preview_sha256, actor):
    root = Path(pipeline_root).resolve()
    directory = recovery.operation_root(root, request_id, operation_id)
    preview = root / 'data/generation_recovery_previews' / request_id / operation_id / 'intent.json'
    intent = recovery.check(recovery.read(preview), recovery.INTENT)
    if recovery.file_sha(preview) != preview_sha256 or intent['actor'] != actor:
        raise recovery.RecoveryError('GENERATION_RECOVERY_CONFLICT', 'Preview or caller does not match')
    request = content_plan_runtime.read_request_and_source_plan(root, request_id)[1]
    with _business_generation_lock(root, request['persona_id']):
        state = recovery.graph(root, request_id)
        if (directory / 'intent.json').exists():
            if recovery.read(directory / 'intent.json') != intent:
                raise recovery.RecoveryError('GENERATION_RECOVERY_CONFLICT', 'Conflicting operation payload')
            # Exact delivery replay grants no new execution authority. The
            # original worker independently rechecks the frozen authorization
            # and sources, including a deny-only continuation after revocation.
            return recovery.ref(root, directory / 'intent.json')
        recovery.verify_authorization(intent)
        current = recovery_bindings(root, generation_inputs(root, request_id))
        if intent['bindings'] != current:
            raise recovery.RecoveryError('GENERATION_RECOVERY_SOURCE_CHANGED', 'Sources changed after preview')
        require_retry_scope(root, request_id, state, generation_inputs(root, request_id))
        if state['pending'] or intent['parent_ref'] != state['head_ref']:
            raise recovery.RecoveryError('GENERATION_RECOVERY_CONFLICT', 'Recovery parent changed')
        recovery.publish(directory / 'intent.json', intent, recovery.INTENT)
        return recovery.ref(root, directory / 'intent.json')


def execute_generation_recovery(root, request_id, operation_id, intent_sha256, inputs, transport, model, max_attempts):
    from contextlib import contextmanager
    is_batch = bool(inputs['request'].get('batch_admission_ref'))
    @contextmanager
    def local_fence(*, recheck=True):
        if not is_batch:
            yield
            return
        from novel_news_generation_recovery_v1 import mutation_fence
        from batch_provider_recovery_v1 import assert_current
        with mutation_fence(root), _business_generation_lock(root, inputs['request']['persona_id']):
            if recheck:
                assert_current(root, inputs['request'], 'script_generation')
                recovery.verify_authorization(intent)
                if intent['bindings'] != recovery_bindings(root, generation_inputs(root, request_id)):
                    raise recovery.RecoveryError('GENERATION_RECOVERY_SOURCE_CHANGED', 'Native retry source changed before local mutation')
            yield
    directory = recovery.operation_root(root, request_id, operation_id)
    intent_path = directory / 'intent.json'
    intent = recovery.check(recovery.read(intent_path), recovery.INTENT)
    if recovery.file_sha(intent_path) != intent_sha256:
        raise recovery.RecoveryError('GENERATION_RECOVERY_CONFLICT', 'Intent identity mismatch')
    state = recovery.graph(root, request_id)
    if intent['bindings'] != recovery_bindings(root, inputs):
        raise recovery.RecoveryError('GENERATION_RECOVERY_SOURCE_CHANGED', 'Frozen generation inputs changed')
    result_path = directory / 'result.json'
    if result_path.is_file():
        result = recovery.check(recovery.read(result_path), recovery.RESULT)
        if result['outcome'] != 'review_required':
            raise recovery.RecoveryError('GENERATION_RECOVERY_OUTCOME_UNKNOWN' if result['outcome'] == 'outcome_unknown' else 'GENERATION_BATCH_NOT_REVIEWABLE', result['outcome'])
        path = recovery.resolve_ref(root, result['batch_ref'])
        return result_from_batch(batch_path=path, review_path=recovery.resolve_ref(root, result['review_pack_ref']),
            batch=read_json(path), selected_concept_ids=inputs['selected_concept_ids'], recovered=True, remote_model_called=False)
    if not state['pending'] or state['pending'] != intent:
        raise recovery.RecoveryError('GENERATION_RECOVERY_GRAPH_INVALID', 'Operation is not the pending head')
    require_retry_scope(root, request_id, state, inputs)
    candidate_path = directory / 'candidate.json'
    batch_path, review_path = directory / 'generation_batch_v1.json', directory / 'generation_review_pack_v1.md'
    dispatch = directory / 'dispatch.json'

    def finish(outcome, ready):
        record = {'schema_version': recovery.RESULT, 'intent_ref': recovery.ref(root, intent_path),
            'parent_ref': intent['parent_ref'], 'outcome': outcome,
            'candidate_ref': recovery.ref(root, candidate_path) if candidate_path.is_file() else None,
            'batch_ref': recovery.ref(root, batch_path) if batch_path.is_file() else None,
            'review_pack_ref': recovery.ref(root, review_path) if review_path.is_file() else None,
            'validation': {'ready_for_human_review': ready}}
        with local_fence(recheck=outcome in ('review_required', 'transport_failed')):
            recovery.publish(result_path, record, recovery.RESULT)

    try:
        recovery.verify_authorization(intent)
    except recovery.RecoveryError:
        finish('blocked', False)
        raise
    candidate = load_candidate_batch(path=candidate_path, request_id=request_id,
        final_plan_path=inputs['final_plan_path'], projection=inputs['projection'], closure_memory=inputs['closure_memory'])
    remote_called = False
    if candidate is None and not batch_path.is_file():
        if dispatch.is_file():
            recovery.check(recovery.read(dispatch), recovery.DISPATCH)
            if recovery.read(dispatch)['intent_ref'] != recovery.ref(root, intent_path):
                raise recovery.RecoveryError('GENERATION_RECOVERY_GRAPH_INVALID', 'Dispatch intent mismatch')
            from batch_provider_recovery_v1 import effective_phase
            saved_response = is_batch and bool(list(effective_phase(root, inputs['request'], 'script_generation').glob('*/response.json')))
            if not saved_response:
                finish('outcome_unknown', False)
                raise recovery.RecoveryError('GENERATION_RECOVERY_OUTCOME_UNKNOWN', 'External outcome is unknown; no automatic call was made')
        runtime_model = model
        if transport is None:
            api_key, env_model = load_deepseek_runtime_config()
            os.environ['DEEPSEEK_API_KEY'], os.environ['DEEPSEEK_MODEL'] = api_key, env_model
            runtime_model = model or env_model
        with local_fence():
            recovery.publish(dispatch, {'schema_version': recovery.DISPATCH, 'intent_ref': recovery.ref(root, intent_path)}, recovery.DISPATCH)
        from batch_provider_recovery_v1 import dispatch_count
        before = dispatch_count(root, inputs['request'], 'script_generation')
        candidate = generate_batch(inputs['context'], model=runtime_model or 'explicit-transport-model', max_attempts=max_attempts, transport=transport,
            content_plan=inputs['projection'], content_ledger=inputs['closure_memory'],
            **({'native_style_mode':True} if inputs['request'].get('creative_style') else {}))
        with local_fence():
            persist_candidate_batch(path=candidate_path, request_id=request_id, final_plan_path=inputs['final_plan_path'],
                projection=inputs['projection'], closure_memory=inputs['closure_memory'], batch=candidate)
        remote_called = not is_batch or dispatch_count(root, inputs['request'], 'script_generation') > before
    if not batch_path.is_file():
        batch = augment_and_validate_batch(batch=candidate, context=inputs['context'], request=inputs['request'],
            final_plan_path=inputs['final_plan_path'], final_plan=inputs['final_plan'], projection=inputs['projection'],
            closure_memory=inputs['closure_memory'], v1_path=inputs['v1_path'], v1_1_path=inputs['v1_1_path'])
        batch['generation_recovery_v1'] = {'reader_version': recovery.READER, 'intent_ref': recovery.ref(root, intent_path)}
        with local_fence():
            recovery.write_once(batch_path, batch)
    batch = read_json(batch_path)
    validate_existing_batch(batch=batch, batch_path=batch_path, request=inputs['request'],
        final_plan_path=inputs['final_plan_path'], final_plan=inputs['final_plan'],
        projection=inputs['projection'], closure_memory=inputs['closure_memory'])
    from generate_mix_scripts_v1 import render_review_pack
    with local_fence():
        recovery.publish_text(review_path, render_review_pack(batch, recovery.file_sha(batch_path)))
    result = result_from_batch(batch_path=batch_path, review_path=review_path, batch=batch,
        selected_concept_ids=inputs['selected_concept_ids'], recovered=False, remote_model_called=remote_called)
    try:
        recovery.verify_authorization(intent)
    except recovery.RecoveryError:
        finish('blocked', False)
        raise
    # Re-read current inputs before publication; never activate a stale source result.
    try:
        unchanged = intent['bindings'] == recovery_bindings(root, generation_inputs(root, request_id))
    except (RuntimeError, ValueError, OSError) as exc:
        finish('blocked', False)
        raise recovery.RecoveryError('GENERATION_RECOVERY_SOURCE_CHANGED', 'Sources could not be revalidated before publication') from exc
    if not unchanged:
        finish('blocked', False)
        raise recovery.RecoveryError('GENERATION_RECOVERY_SOURCE_CHANGED', 'Sources changed before publication')
    if not result['ready_for_human_review'] and not recovery.transport_failure(batch):
        finish('blocked', False)
        raise recovery.RecoveryError('GENERATION_RECOVERY_SCOPE_UNSUPPORTED', 'Retry output needs unsupported recovery')
    if is_batch:
        from batch_provider_recovery_v1 import record_native_result
        with local_fence():
            record_native_result(root, inputs['request'], 'script_generation', batch_path)
    finish('review_required' if result['ready_for_human_review'] else 'transport_failed', result['ready_for_human_review'])
    return result


@compatibility_guarded
def resolve_generation_batch(
    *,
    pipeline_root: Path,
    request_id: str,
    transport: Callable[[str], dict[str, Any]] | None = None,
    model: str | None = None,
    max_attempts: int = 3,
    operation_id: str | None = None,
    intent_sha256: str | None = None,
) -> dict[str, Any]:
    pipeline_root = pipeline_root.expanduser().resolve()
    if bool(operation_id) != bool(intent_sha256):
        raise recovery.RecoveryError('GENERATION_RECOVERY_SCHEMA_INVALID', 'Operation and immutable intent SHA must be supplied together')
    if max_attempts < 1 or max_attempts > 3:
        raise GenerationBatchResolutionError(
            "SCRIPT_GENERATION_ATTEMPTS_INVALID",
            "max_attempts must be between 1 and 3.",
        )

    request_path, request, source_plan_path, source_plan = (
        content_plan_runtime.read_request_and_source_plan(
            pipeline_root,
            request_id,
        )
    )
    if str(request.get("target_profile") or request.get("profile") or "") != "mix":
        raise GenerationBatchResolutionError(
            "SCRIPT_GENERATION_PROFILE_UNSUPPORTED",
            "Script Generation V1 currently supports Mix only.",
        )
    business_id = str(request.get("persona_id") or "")
    if not business_id:
        raise GenerationBatchResolutionError(
            "GENERATION_REQUEST_INVALID",
            "Generation Request persona_id is missing.",
        )

    is_batch = bool(request.get('batch_admission_ref'))
    with (nullcontext() if is_batch else _business_generation_lock(pipeline_root, business_id)):
        inputs = generation_inputs(pipeline_root, request_id)
        if operation_id:
            return execute_generation_recovery(pipeline_root, request_id, operation_id, intent_sha256,
                inputs, transport, model, max_attempts)
        request_path = inputs["request_path"]
        request = inputs["request"]
        source_plan_path = inputs["source_plan_path"]
        source_plan = inputs["source_plan"]
        context = inputs["context"]
        runtime_contract = inputs["runtime_contract"]
        closure_memory = inputs["closure_memory"]
        v1_path = inputs["v1_path"]
        v1_plan = inputs["v1_plan"]
        v1_1_path = inputs["v1_1_path"]
        final_plan_path = inputs["final_plan_path"]
        final_plan = inputs["final_plan"]
        projection = inputs["projection"]
        selected_concept_ids = inputs["selected_concept_ids"]

        batch_root = pipeline_root / "data" / "generation_batches"
        batch_path = batch_root / request_id / "generation_batch_v1.json"
        review_path = batch_root / request_id / "generation_review_pack_v1.md"
        selected_attempt = recovery.graph(pipeline_root, request_id)
        if not selected_attempt['pending'] and selected_attempt['result'] and selected_attempt['result']['outcome'] in {'review_required','transport_failed'}:
            batch_path = selected_attempt['batch']
            review_path = batch_path.parent / 'generation_review_pack_v1.md'

        if batch_path.is_file():
            batch = read_json(batch_path)
            validate_existing_batch(
                batch=batch,
                batch_path=batch_path,
                request=request,
                final_plan_path=final_plan_path,
                final_plan=final_plan,
                projection=projection,
                closure_memory=closure_memory,
            )
            if not review_path.is_file():
                try:
                    from batch_provider_recovery_v1 import publication_fence
                    with publication_fence(pipeline_root, request, 'script_generation'):
                        write_review_pack_for_existing_batch(batch_path, review_path)
                except Exception as exc:
                    raise GenerationBatchResolutionError(
                        "GENERATION_REVIEW_PACK_RECOVERY_FAILED",
                        f"Could not recover derived Review Pack: {exc}",
                    ) from exc
            return result_from_batch(
                batch_path=batch_path,
                review_path=review_path,
                batch=batch,
                selected_concept_ids=selected_concept_ids,
                recovered=True,
                remote_model_called=False,
            )

        if review_path.exists():
            raise GenerationBatchResolutionError(
                "GENERATION_BATCH_PARTIAL_ARTIFACT_CONFLICT",
                "Review Pack exists without its canonical Generation Batch.",
            )

        candidate_path = candidate_cache_path(
            pipeline_root,
            request_id,
        )
        candidate_batch = load_candidate_batch(
            path=candidate_path,
            request_id=request_id,
            final_plan_path=final_plan_path,
            projection=projection,
            closure_memory=closure_memory,
        )
        candidate_recovered = candidate_batch is not None
        remote_model_called = False
        from batch_provider_recovery_v1 import dispatch_count
        dispatched_before = dispatch_count(pipeline_root, request, 'script_generation')

        if candidate_batch is not None:
            batch = copy.deepcopy(candidate_batch)
        else:
            resolved_model = str(model or "").strip()
            if transport is None:
                try:
                    api_key, env_model = load_deepseek_runtime_config()
                except Exception as exc:
                    raise GenerationBatchResolutionError(
                        "DEEPSEEK_RUNTIME_CONFIG_INVALID",
                        str(exc),
                    ) from exc
                os.environ["DEEPSEEK_API_KEY"] = api_key
                os.environ["DEEPSEEK_MODEL"] = env_model
                resolved_model = resolved_model or env_model
            elif not resolved_model:
                resolved_model = "test-script-generator"

            try:
                batch = generate_batch(
                    context,
                    model=resolved_model,
                    max_attempts=max_attempts,
                    transport=transport,
                    content_plan=projection,
                    content_ledger=closure_memory,
                    **({"native_style_mode": True} if request.get("creative_style") else {}),
                )
            except __import__('creation_batch_contract_v1').BatchError:
                raise
            except Exception as exc:
                raise GenerationBatchResolutionError(
                    "SCRIPT_GENERATION_FAILED",
                    f"Existing Mix Script Generator failed: {exc}",
                ) from exc

            # Persist the accepted/rejected remote result BEFORE wrapper-level
            # post-validation. If a later deterministic gate is too strict or
            # contains a bug, the real model output remains recoverable offline.
            from batch_provider_recovery_v1 import publication_fence
            with publication_fence(pipeline_root, request, 'script_generation'):
                persist_candidate_batch(
                    path=candidate_path, request_id=request_id, final_plan_path=final_plan_path,
                    projection=projection, closure_memory=closure_memory, batch=batch)
            remote_model_called = not is_batch or dispatch_count(pipeline_root, request, 'script_generation') > dispatched_before

        batch = augment_and_validate_batch(
            batch=batch,
            context=context,
            request=request,
            final_plan_path=final_plan_path,
            final_plan=final_plan,
            projection=projection,
            closure_memory=closure_memory,
            v1_path=v1_path,
            v1_1_path=v1_1_path,
        )

        try:
            from batch_provider_recovery_v1 import publication_fence
            with publication_fence(pipeline_root, request, 'script_generation'):
                written_batch_path, written_review_path, _ = write_batch(batch, batch_root)
                from batch_provider_recovery_v1 import record_native_result
                record_native_result(pipeline_root, request, 'script_generation', written_batch_path)
        except __import__('creation_batch_contract_v1').BatchError:
            raise
        except Exception as exc:
            raise GenerationBatchResolutionError(
                "GENERATION_BATCH_WRITE_FAILED",
                f"Could not persist immutable Generation Batch: {exc}",
            ) from exc

        written = read_json(written_batch_path)
        validate_existing_batch(
            batch=written,
            batch_path=written_batch_path,
            request=request,
            final_plan_path=final_plan_path,
            final_plan=final_plan,
            projection=projection,
            closure_memory=closure_memory,
        )
        return result_from_batch(
            batch_path=written_batch_path,
            review_path=written_review_path,
            batch=written,
            selected_concept_ids=selected_concept_ids,
            recovered=False,
            remote_model_called=remote_model_called,
            candidate_recovered=candidate_recovered,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate one Mix Generation Batch from final Content Plan V1.1.1."
        )
    )
    parser.add_argument("--request-id", required=True)
    parser.add_argument(
        "--pipeline-root",
        default=str(Path(__file__).resolve().parents[1]),
    )
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--operation-id")
    parser.add_argument("--intent-sha256")
    args = parser.parse_args()

    try:
        result = resolve_generation_batch(
            pipeline_root=Path(args.pipeline_root),
            request_id=str(args.request_id).strip(),
            max_attempts=args.max_attempts,
            operation_id=args.operation_id, intent_sha256=args.intent_sha256,
        )
    except (GenerationBatchResolutionError, recovery.RecoveryError,
            __import__('creation_batch_contract_v1').BatchError,
            __import__('creative_style_v1').CreativeStyleError,
            content_plan_runtime.ContentPlanResolutionError,
            content_plan_runtime.CompatibilityError) as exc:
        print(
            json.dumps(
                {"ok": False, "code": exc.code, "message": str(exc)},
                ensure_ascii=False,
            )
        )
        raise SystemExit(2) from exc

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
