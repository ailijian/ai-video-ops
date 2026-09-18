from __future__ import annotations

import argparse
import hashlib
import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "news-slot-recommendation-v1.0"
ALGORITHM_VERSION = "news-slot-recommendation-v1.1"

MIN_SLOTS = 4
MAX_SLOTS = 8

ALLOWED_FIELDS = {
    "pricing_facts",
    "included_service_facts",
    "differentiators",
    "product_or_service_facts",
}

FIELD_BASE_SCORE = {
    "pricing_facts": 100,
    "included_service_facts": 72,
    "differentiators": 58,
    "product_or_service_facts": 44,
}

FIELD_AUTHORITY_PRIORITY = {
    "pricing_facts": 0,
    "included_service_facts": 1,
    "differentiators": 2,
    "product_or_service_facts": 3,
}

HIGH_VALUE_THRESHOLD = 55
STRONG_MEMORY_STATUSES = {"approved", "exported", "published"}


class NewsSlotRecommendationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NewsSlotRecommendationError(
            "NEWS_SLOT_SOURCE_INVALID",
            f"Cannot read JSON artifact: {path}",
        ) from exc
    if not isinstance(value, dict):
        raise NewsSlotRecommendationError(
            "NEWS_SLOT_SOURCE_INVALID",
            f"Artifact must be a JSON object: {path}",
        )
    return value


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def normalize_text(value: Any) -> str:
    return re.sub(
        r"[\W_]+",
        "",
        str(value or "").lower(),
        flags=re.UNICODE,
    )


def numeric_signature(value: Any) -> tuple[str, ...]:
    return tuple(re.findall(r"\d+(?:\.\d+)?", str(value or "")))


def _explicit_atom_refs(entry: dict[str, Any]) -> set[str]:
    refs: set[str] = set()

    for key in (
        "communicated_information_units",
        "information_units",
    ):
        for unit in entry.get(key) or []:
            if unit.get("explicitness") != "explicit":
                continue
            for ref in unit.get("fact_atom_refs") or []:
                refs.add(str(ref))

    # Compatibility with earlier ledger entries that already carried
    # primary Fact Atom refs before communicated-information enrichment.
    for ref in entry.get("primary_fact_atom_refs") or []:
        refs.add(str(ref))

    return refs


def _primary_atom_refs(entry: dict[str, Any]) -> set[str]:
    return {
        str(ref)
        for ref in entry.get("primary_fact_atom_refs") or []
    }


def _price_anchor_bonus(atom: dict[str, Any]) -> int:
    text = str(atom.get("original_known_fact") or "")
    if re.search(
        r"\d|元|块|折|价|套餐|优惠|免费|赠送",
        text,
    ):
        return 12
    return 0


def _candidate_score(
    atom: dict[str, Any],
    primary_atom_refs: set[str],
) -> tuple[int, list[str]]:
    field = str(atom.get("field") or "")
    atom_id = str(atom.get("fact_atom_id") or "")
    score = FIELD_BASE_SCORE.get(field, 0)
    reasons = [f"field:{field}"]

    if atom_id in primary_atom_refs:
        score += 20
        reasons.append("primary_historical_fact_atom")

    bonus = _price_anchor_bonus(atom)
    if bonus:
        score += bonus
        reasons.append("concrete_offer_or_price_signal")

    text = str(atom.get("original_known_fact") or "")
    if 2 <= len(text) <= 20:
        score += 3
        reasons.append("compact_display_candidate")

    return score, reasons


def _same_semantic_fact(
    left: dict[str, Any],
    right: dict[str, Any],
) -> bool:
    left_text = normalize_text(
        left.get("normalized_meaning")
        or left.get("original_known_fact")
    )
    right_text = normalize_text(
        right.get("normalized_meaning")
        or right.get("original_known_fact")
    )

    if not left_text or not right_text:
        return False
    if left_text == right_text:
        return True
    if left_text in right_text or right_text in left_text:
        return True

    left_numbers = numeric_signature(
        left.get("original_known_fact")
    )
    right_numbers = numeric_signature(
        right.get("original_known_fact")
    )
    similarity = SequenceMatcher(
        None,
        left_text,
        right_text,
    ).ratio()

    # Same price/range signal + highly similar Chinese meaning.
    if (
        left_numbers
        and left_numbers == right_numbers
        and similarity >= 0.66
    ):
        return True

    # Same free/included-service meaning, no numeric value required.
    if (
        "免费" in left_text
        and "免费" in right_text
        and similarity >= 0.72
    ):
        return True

    return False


def _dominant_candidate(
    left: dict[str, Any],
    right: dict[str, Any],
) -> dict[str, Any]:
    def key(item: dict[str, Any]) -> tuple[int, int, int, str]:
        return (
            FIELD_AUTHORITY_PRIORITY.get(
                str(item.get("field") or ""),
                99,
            ),
            -int(item.get("score") or 0),
            int(item.get("catalog_index") or 0),
            str(item.get("fact_atom_id") or ""),
        )

    return min((left, right), key=key)


def _deduplicate_candidates(
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []

    for candidate in candidates:
        duplicate_index = next(
            (
                index
                for index, existing in enumerate(kept)
                if _same_semantic_fact(existing, candidate)
            ),
            None,
        )

        if duplicate_index is None:
            kept.append(candidate)
            continue

        existing = kept[duplicate_index]
        dominant = _dominant_candidate(
            existing,
            candidate,
        )

        if dominant is existing:
            suppressed.append(
                {
                    **candidate,
                    "suppressed_as_duplicate_of": existing["fact_atom_id"],
                    "suppression_reason": (
                        "cross_field_semantic_duplicate_lower_authority"
                    ),
                }
            )
            continue

        suppressed.append(
            {
                **existing,
                "suppressed_as_duplicate_of": candidate["fact_atom_id"],
                "suppression_reason": (
                    "cross_field_semantic_duplicate_lower_authority"
                ),
            }
        )
        kept[duplicate_index] = candidate

    return kept, suppressed


def _claim_position(
    candidate: dict[str, Any],
    central_claim: str,
) -> int:
    claim = normalize_text(central_claim)
    if not claim:
        return 10**9

    text = str(
        candidate.get("original_known_fact")
        or candidate.get("normalized_meaning")
        or ""
    )
    numbers = numeric_signature(text)

    if numbers:
        positions = [
            claim.find(number.replace(".", ""))
            for number in numbers
        ]
        valid = [
            position
            for position in positions
            if position >= 0
        ]
        if valid:
            return min(valid)

    normalized = normalize_text(text)
    if normalized:
        direct = claim.find(normalized)
        if direct >= 0:
            return direct

    return 10**9


def _presentation_order(
    candidate: dict[str, Any],
    central_claim: str,
) -> tuple[int, int, int, int, str]:
    field = str(candidate.get("field") or "")
    return (
        0 if field == "pricing_facts" else 1,
        _claim_position(candidate, central_claim),
        FIELD_AUTHORITY_PRIORITY.get(field, 99),
        int(candidate.get("catalog_index") or 0),
        str(candidate.get("fact_atom_id") or ""),
    )


def build_recommendation(
    *,
    ledger: dict[str, Any],
    business_id: str,
    content_id: str,
) -> dict[str, Any]:
    if ledger.get("business_id") != business_id:
        raise NewsSlotRecommendationError(
            "NEWS_SLOT_LEDGER_BUSINESS_MISMATCH",
            "Content Ledger business_id does not match the requested business.",
        )

    entry = next(
        (
            item
            for item in ledger.get("entries") or []
            if str(item.get("content_id") or "") == content_id
        ),
        None,
    )
    if entry is None:
        raise NewsSlotRecommendationError(
            "NEWS_SLOT_SOURCE_CONTENT_NOT_FOUND",
            f"Historical content is not present in Content Ledger: {content_id}",
        )

    if str(entry.get("status") or "") not in STRONG_MEMORY_STATUSES:
        raise NewsSlotRecommendationError(
            "NEWS_SLOT_SOURCE_CONTENT_NOT_STRONG_MEMORY",
            "News repurpose requires Approved / Exported / Published historical content.",
        )

    explicit_refs = _explicit_atom_refs(entry)
    primary_refs = _primary_atom_refs(entry)

    catalog = [
        atom
        for atom in ledger.get("fact_atom_catalog") or []
        if isinstance(atom, dict)
        and atom.get("fact_atom_id")
    ]
    atom_by_id = {
        str(atom.get("fact_atom_id") or ""): atom
        for atom in catalog
    }
    catalog_position = {
        str(atom.get("fact_atom_id") or ""): index
        for index, atom in enumerate(catalog)
    }

    missing = sorted(
        ref
        for ref in explicit_refs
        if ref not in atom_by_id
        and not ref.endswith("::<field-level-authority>")
    )
    if missing:
        raise NewsSlotRecommendationError(
            "NEWS_SLOT_FACT_ATOM_LINEAGE_INCOMPLETE",
            "Historical content references Fact Atoms missing from the canonical Ledger: "
            + ", ".join(missing),
        )

    raw_candidates: list[dict[str, Any]] = []

    for ref in sorted(explicit_refs):
        atom = atom_by_id.get(ref)
        if atom is None:
            continue

        field = str(atom.get("field") or "")
        if field not in ALLOWED_FIELDS:
            continue

        score, reasons = _candidate_score(
            atom,
            primary_refs,
        )
        raw_candidates.append(
            {
                "fact_atom_id": ref,
                "field": field,
                "original_known_fact": atom.get("original_known_fact"),
                "normalized_meaning": atom.get("normalized_meaning"),
                "score": score,
                "score_reasons": reasons,
                "is_primary_historical_atom": ref in primary_refs,
                "is_price_or_offer_anchor": (
                    field == "pricing_facts"
                    and _price_anchor_bonus(atom) > 0
                ),
                "catalog_index": catalog_position.get(ref, 10**9),
            }
        )

    raw_candidates.sort(
        key=lambda item: (
            FIELD_AUTHORITY_PRIORITY.get(
                str(item.get("field") or ""),
                99,
            ),
            -int(item["score"]),
            int(item["catalog_index"]),
            str(item["fact_atom_id"]),
        )
    )

    candidates, suppressed = _deduplicate_candidates(
        raw_candidates
    )

    central_claim = str(
        entry.get("central_claim") or ""
    )
    candidates.sort(
        key=lambda item: _presentation_order(
            item,
            central_claim,
        )
    )

    price_candidates = [
        item
        for item in candidates
        if item["field"] == "pricing_facts"
    ]

    if not price_candidates:
        return {
            "schema_version": SCHEMA_VERSION,
            "algorithm_version": ALGORITHM_VERSION,
            "business_id": business_id,
            "source_content_id": content_id,
            "source_status": entry.get("status"),
            "source_title": entry.get("title"),
            "recommended_slot_count": 0,
            "slot_range": {
                "minimum": MIN_SLOTS,
                "maximum": MAX_SLOTS,
            },
            "status": "unsupported_no_price_offer_anchor",
            "selected_candidates": [],
            "eligible_candidate_count": len(candidates),
            "candidate_pool": candidates,
            "suppressed_duplicate_candidates": suppressed,
            "deterministic": True,
            "random_selection_used": False,
            "padding_generated": False,
        }

    high_value = [
        item
        for item in candidates
        if int(item["score"]) >= HIGH_VALUE_THRESHOLD
    ]

    if len(candidates) < MIN_SLOTS:
        selected = candidates
        status = "capacity_insufficient"
    else:
        target = max(
            MIN_SLOTS,
            min(MAX_SLOTS, len(high_value)),
        )
        target = min(target, len(candidates))
        selected = candidates[:target]
        status = "supported"

    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "business_id": business_id,
        "source_content_id": content_id,
        "source_status": entry.get("status"),
        "source_title": entry.get("title"),
        "source_central_claim": central_claim,
        "slot_range": {
            "minimum": MIN_SLOTS,
            "maximum": MAX_SLOTS,
        },
        "recommended_slot_count": len(selected),
        "status": status,
        "selection_policy": {
            "first_slot_must_be_price_or_offer_anchor": True,
            "first_price_anchor_follows_source_central_claim_order_when_recoverable": True,
            "cross_field_semantic_duplicates_collapsed": True,
            "higher_authority_field_wins_duplicate_resolution": True,
            "high_value_score_threshold": HIGH_VALUE_THRESHOLD,
            "select_all_high_value_until_maximum": True,
            "minimum_slots_filled_only_from_distinct_supported_fact_atoms": True,
            "random_selection_used": False,
            "duplicate_padding_allowed": False,
        },
        "selected_candidates": selected,
        "eligible_candidate_count": len(candidates),
        "raw_candidate_count": len(raw_candidates),
        "candidate_pool": candidates,
        "suppressed_duplicate_candidates": suppressed,
        "deterministic": True,
        "random_selection_used": False,
        "padding_generated": False,
        "lineage": {
            "ledger_sha256": canonical_sha256(ledger),
            "source_content_semantic_signature_sha256": canonical_sha256(
                entry.get("semantic_signature") or {}
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Recommend 4-8 News display slots deterministically "
            "from Strong Historical Content."
        )
    )
    parser.add_argument(
        "--pipeline-root",
        default=str(Path(__file__).resolve().parents[1]),
    )
    parser.add_argument(
        "--business-id",
        required=True,
    )
    parser.add_argument(
        "--content-id",
        required=True,
    )
    args = parser.parse_args()

    root = Path(args.pipeline_root).expanduser().resolve()
    ledger_path = (
        root
        / "data"
        / "content_ledgers"
        / args.business_id
        / "content_ledger_v1.json"
    )

    try:
        ledger = read_json(ledger_path)
        result = build_recommendation(
            ledger=ledger,
            business_id=str(args.business_id),
            content_id=str(args.content_id),
        )
    except NewsSlotRecommendationError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": exc.code,
                    "message": str(exc),
                },
                ensure_ascii=False,
            )
        )
        raise SystemExit(2) from exc

    print(
        json.dumps(
            {
                "ok": True,
                "read_only": True,
                "remote_model_called": False,
                "artifact_written": False,
                "recommendation": result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
