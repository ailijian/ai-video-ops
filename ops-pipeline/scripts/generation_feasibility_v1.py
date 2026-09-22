from __future__ import annotations

from pathlib import Path
from typing import Any

from match_generation_sources_v1 import build_source_plan
from resolve_generation_source_plan_v1 import resolve_matching_universe


def preview_generation_feasibility(
    *,
    pipeline_root: Path,
    business_persona_path: Path,
    speaker_persona_path: Path,
    profile_registry_path: Path,
    target_profile: str,
    quantity: int,
    reuse_intent: str = "novel_content",
    content_intent: str = "mixed",
    platform: str = "douyin",
    constraints: dict[str, Any] | None = None,
    selected_content: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a read-only production-feasibility projection.

    No Generation Request or Source Plan artifact is created. Formal matching
    and preview matching both call ``build_source_plan`` and therefore share
    Pattern eligibility, Case eligibility, Fingerprint lineage, and Profile
    Compatibility rules.
    """

    pipeline_root = pipeline_root.expanduser().resolve()
    universe = resolve_matching_universe(pipeline_root)
    context = {
        "target_profile": target_profile,
        "profile": target_profile,
        "reuse_intent": reuse_intent,
        "content_intent": content_intent,
        "quantity": quantity,
        "platform": platform,
        "cta_intent": "none",
        "constraints": dict(constraints or {}),
        "selected_content": selected_content,
    }

    # Speaker identity is part of the read-only matching context. It is read
    # from the Approved artifact only; no new authority is inferred here.
    from match_generation_sources_v1 import read_json  # local to keep module small

    speaker = read_json(speaker_persona_path.expanduser().resolve())
    context["speaker_persona"] = speaker.get("persona_id")
    context["speaker_persona_revision"] = speaker.get("revision")

    plan = build_source_plan(
        persona_path=business_persona_path,
        request_path=None,
        pattern_paths=universe["pattern_paths"],
        case_paths=universe["case_paths"],
        fingerprint_paths=universe["fingerprint_paths"],
        speaker_persona_path=speaker_persona_path,
        profile_registry_path=profile_registry_path,
        creative_coverage_report_path=universe[
            "creative_coverage_report_path"
        ],
        profile_compatibility_approval_path=universe[
            "profile_compatibility_approval_path"
        ],
        request_context=context,
    )
    projection = dict(plan["feasibility"])
    projection["authority"] = {
        **(projection.get("authority") or {}),
        "generation_request_created": False,
        "source_plan_written": False,
        "matching_core": "match_generation_sources_v1.build_source_plan",
    }
    return projection
