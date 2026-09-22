"""Read-only News opportunities from approved Customer Truth and business-wide history.

This is a projection, not a second Content Intelligence authority. It reuses
the canonical Fact Atom, semantic-signature and historical-exposure rules.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from content_quality_v1 import (
    build_fact_atom_catalog,
    fact_atom_matches_text,
    historical_exposure_evaluation,
    is_strong_memory,
    novelty_evaluation,
    semantic_signature,
)
from generate_mix_scripts_v1 import safe_persona_projection
from privacy_projection_v1 import assert_safe_for_external_model, project_value
from generation_feasibility_v1 import preview_generation_feasibility
from show_customer_status_v1 import (
    load_content_ledger,
    resolve_current_persona,
    resolve_speaker_persona,
    sha256_file,
)

PRICE_OR_OFFER = re.compile(r"(?:\d|[一二三四五六七八九十百千]+)(?:\s*(?:元|块|折|%))|(?:优惠|免费|赠送|套餐|报价|价格|收费)")
SUPPORT_FIELDS = ("included_service_facts", "product_or_service_facts", "differentiators")


def _was_communicated(atom: dict[str, Any], entries: list[dict[str, Any]]) -> bool:
    atom_id = str(atom["fact_atom_id"])
    for entry in entries:
        if not is_strong_memory(entry):
            continue
        explicit = [
            unit for unit in entry.get("communicated_information_units") or []
            if unit.get("explicitness") == "explicit"
        ]
        if any(atom_id in (unit.get("fact_atom_refs") or []) for unit in explicit):
            return True
        # Older ledger entries may have no atom IDs for the current Persona
        # revision. Exact underlying fact text still prevents cross-profile
        # repackaging from being counted as Novel.
        if any(
            fact_atom_matches_text(atom, unit.get("normalized_meaning"))[0]
            for unit in explicit
        ):
            return True
        if fact_atom_matches_text(
            atom,
            " ".join(str(entry.get(key) or "") for key in ("central_claim", "title", "narration")),
        )[0]:
            return True
        # Incomplete historical price lineage is uncertain, not fresh.
        if not explicit and "pricing_facts" in (entry.get("primary_fact_refs") or []):
            return True
    return False


def price_novelty_status(
    atom: dict[str, Any], concept: dict[str, Any], ledger: dict[str, Any]
) -> str:
    """Shared preview/export novelty gate against business-wide Strong Memory."""
    history = list(ledger.get("entries") or [])
    if not history:
        return "novel"
    catalog = list(ledger.get("fact_atom_catalog") or [])
    if not any(item.get("fact_atom_id") == atom["fact_atom_id"] for item in catalog):
        catalog.append(atom)
    historical = historical_exposure_evaluation(concept, {**ledger, "fact_atom_catalog": catalog})
    novelty = novelty_evaluation(concept, history)
    if _was_communicated(atom, history) or novelty.get("hard_duplicate"):
        return "already_communicated"
    return "uncertain" if historical.get("decision") == "uncertain" else "novel"


def project_novel_news_opportunities(
    *, pipeline_root: Path, business_id: str, speaker_id: str
) -> dict[str, Any]:
    pipeline_root = pipeline_root.expanduser().resolve()
    business = resolve_current_persona(pipeline_root, business_id, "business")
    speaker = resolve_speaker_persona(pipeline_root, business, speaker_id)
    persona = business["artifact"]
    safe_fields = set(safe_persona_projection(persona)["facts"])
    atoms = build_fact_atom_catalog(persona, sha256_file(business["path"]), safe_fields)
    ledger_path = pipeline_root / "data/content_ledgers" / business_id / "content_ledger_v1.json"
    ledger = load_content_ledger(pipeline_root, business_id)["artifact"] if ledger_path.is_file() else {"entries": [], "fact_atom_catalog": atoms}
    history = list(ledger.get("entries") or [])
    opportunities: list[dict[str, Any]] = []
    for atom in atoms:
        if atom["field"] != "pricing_facts":
            continue
        fact_text = str(project_value(atom.get("original_known_fact") or "", "safe_verbatim")).strip()
        if not PRICE_OR_OFFER.search(fact_text):
            continue
        assert_safe_for_external_model(fact_text)
        supporting = [field for field in SUPPORT_FIELDS if field in safe_fields]
        concept = {
            "concept_id": "news-price-" + hashlib.sha256(atom["fact_atom_id"].encode()).hexdigest()[:16],
            "content_job": "price_offer_explanation",
            "audience_need": "understand_approved_price_or_offer",
            "primary_topic": "price_offer",
            "central_claim": fact_text,
            "primary_fact_refs": ["pricing_facts"],
            "supporting_fact_refs": supporting,
            "primary_fact_atom_refs": [atom["fact_atom_id"]],
            "fact_atom_refs": [atom["fact_atom_id"]],
            "exclusive_anchor": {
                "kind": "authorized_customer_fact",
                "value": fact_text,
                "fact_refs": ["pricing_facts"],
            },
            "why_publish": "帮助顾客理解已确认的价格或优惠及其适用范围。",
            "source_fact_values": {"pricing_facts": fact_text},
            "source_fact_atom_refs": [atom["fact_atom_id"]],
        }
        concept["semantic_signature"] = semantic_signature(concept, business_id)
        concept["novelty_status"] = price_novelty_status(atom, concept, ledger)
        if concept["novelty_status"] == "novel":
            feasibility = preview_generation_feasibility(
                pipeline_root=pipeline_root,
                business_persona_path=business["path"],
                speaker_persona_path=speaker["path"],
                profile_registry_path=pipeline_root / "data/production_profiles/production_profile_registry_v1.json",
                target_profile="news", quantity=1, selected_content=concept,
            )
            concept["production_feasibility"] = feasibility
            concept["applicable_pattern_id"] = (
                "pcv1_news_price_offer_led_micro_information"
                if feasibility.get("status") == "supported" else None
            )
        else:
            concept["production_feasibility"] = {"status": "unsupported", "blocker_type": "CONTENT_NOT_NOVEL"}
            concept["applicable_pattern_id"] = None
        concept.pop("source_fact_values")  # values remain in Approved Persona, not the UI projection
        opportunities.append(concept)
    return {
        "schema_version": "novel-news-opportunity-projection-v1.0",
        "business_id": business_id,
        "speaker_id": speaker_id,
        "business_persona_revision": persona.get("revision"),
        "speaker_persona_revision": speaker["artifact"].get("revision"),
        "opportunities": opportunities,
        "available_novel_count": sum(item["novelty_status"] == "novel" for item in opportunities),
        "production_ready_count": sum(item["production_feasibility"].get("status") == "supported" for item in opportunities),
        "authority": {"generation_request_created": False, "source_plan_written": False, "content_ledger_written": False, "remote_model_called": False},
    }


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline-root", type=Path, required=True)
    parser.add_argument("--business-id", required=True)
    parser.add_argument("--speaker-id", required=True)
    args = parser.parse_args()
    try:
        projection = project_novel_news_opportunities(
            pipeline_root=args.pipeline_root,
            business_id=args.business_id,
            speaker_id=args.speaker_id,
        )
        print(json.dumps({"ok": True, "projection": projection}, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "code": getattr(exc, "code", "NEWS_NOVEL_PREVIEW_FAILED"), "message": str(exc)}, ensure_ascii=False))
        raise SystemExit(2) from exc
