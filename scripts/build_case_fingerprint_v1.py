from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "case-fingerprint-v1.0-draft"
BUILDER_VERSION = "build_case_fingerprint_v1.py@0.1"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ratio(n: float, d: float) -> float | None:
    if not d:
        return None
    return round(n / d, 6)


def count_roles(shots: list[dict[str, Any]]) -> tuple[Counter, Counter]:
    primary = Counter()
    secondary = Counter()

    for shot in shots:
        interpretation = shot.get("interpretation", {})
        p = interpretation.get("primary_role")
        if p:
            primary[str(p)] += 1

        for role in interpretation.get("secondary_roles", []) or []:
            secondary[str(role)] += 1

    return primary, secondary


def summarize_numeric(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
        }

    return {
        "count": len(values),
        "min": round(min(values), 6),
        "max": round(max(values), 6),
        "mean": round(statistics.mean(values), 6),
        "median": round(statistics.median(values), 6),
    }


def verify_storyboard_artifact(
    case: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    storyboard_meta = case.get("storyboard", {}).get("artifact", {})
    raw_path = storyboard_meta.get("path")

    if not raw_path:
        raise RuntimeError(
            "Canonical Case does not contain storyboard.artifact.path."
        )

    path = Path(raw_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(
            f"Referenced storyboard artifact does not exist: {path}"
        )

    expected_hash = storyboard_meta.get("sha256")
    if expected_hash:
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise RuntimeError(
                "Storyboard artifact hash does not match the approved Case. "
                "Do not mine patterns from a silently changed artifact.\n"
                f"Expected: {expected_hash}\n"
                f"Actual:   {actual_hash}"
            )

    return path, read_json(path)


def main() -> None:
    started = time.perf_counter()

    parser = argparse.ArgumentParser(
        description=(
            "Build a deterministic Pattern-Mining Fingerprint from one approved Case. "
            "No AI call and no reusable Pattern generation happens in this stage."
        )
    )
    parser.add_argument(
        "--case",
        required=True,
        help="Path to approved case_v1.json",
    )
    parser.add_argument(
        "--output-root",
        default=None,
        help="Default: <project>/data/fingerprints",
    )
    args = parser.parse_args()

    case_path = Path(args.case).expanduser().resolve()
    if not case_path.exists():
        raise FileNotFoundError(case_path)

    case = read_json(case_path)
    case_id = str(case.get("case_id") or "")

    errors: list[str] = []
    warnings: list[str] = []

    lifecycle = case.get("lifecycle", {})
    validation = case.get("validation", {})
    quality = case.get("quality", {})

    if not case_id:
        errors.append("Case has no case_id.")

    if lifecycle.get("status") != "approved":
        errors.append(
            f"Case status must be approved, got {lifecycle.get('status')!r}."
        )

    if lifecycle.get("approved") is not True:
        errors.append("Case lifecycle.approved is not true.")

    if validation.get("passed") is not True:
        errors.append("Case validation.passed is not true.")

    if quality.get("human_review_completed") is not True:
        errors.append(
            "Case does not record human_review_completed=true."
        )

    if errors:
        print("\nCASE FINGERPRINT BUILD BLOCKED")
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(2)

    storyboard_path, storyboard = verify_storyboard_artifact(case)

    if str(storyboard.get("case_id")) != case_id:
        raise RuntimeError(
            "Referenced storyboard case_id does not match approved Case."
        )

    narration_track = list(storyboard.get("narration_track") or [])
    shots = list(storyboard.get("shots") or [])

    if not narration_track:
        raise RuntimeError(
            "Storyboard has no narration_track. "
            "Pattern Mining requires Reverse Storyboard V1.1 or later."
        )

    if not shots:
        raise RuntimeError("Storyboard contains no Shots.")

    primary_roles, secondary_roles = count_roles(shots)

    shot_durations = [
        float(x.get("duration") or 0)
        for x in shots
    ]

    narration_durations = [
        float(x.get("duration") or 0)
        for x in narration_track
    ]

    video_duration = float(
        case.get("identity", {}).get("duration_seconds")
        or max(float(x.get("end") or 0) for x in shots)
    )

    narration_total_seconds = sum(narration_durations)
    narration_density = ratio(
        narration_total_seconds,
        video_duration,
    )

    shots_under_1s = sum(
        1 for x in shot_durations if x < 1.0
    )
    shots_under_0_5s = sum(
        1 for x in shot_durations if x < 0.5
    )

    onscreen_text_shots = 0
    multi_info_state_shots = 0
    info_state_count = 0
    multi_narration_shots = 0

    narration_to_shots: dict[str, list[str]] = defaultdict(list)

    text_relation_counts = Counter()
    scene_relation_counts = Counter()

    role_sequence = []

    for shot in shots:
        shot_id = str(shot["shot_id"])
        evidence = shot.get("evidence", {})
        interpretation = shot.get("interpretation", {})

        role_sequence.append(
            str(interpretation.get("primary_role") or "other")
        )

        if any(
            str(x).strip()
            for x in evidence.get("onscreen_text_sequence", []) or []
        ):
            onscreen_text_shots += 1

        states = list(evidence.get("information_states", []) or [])
        info_state_count += len(states)
        if len(states) > 1:
            multi_info_state_shots += 1

        narration_links = list(evidence.get("narration_links", []) or [])
        if len(narration_links) > 1:
            multi_narration_shots += 1

        for link in narration_links:
            sid = str(link["segment_id"])
            narration_to_shots[sid].append(shot_id)

        t_rel = interpretation.get("audio_to_visual_text")
        s_rel = interpretation.get("audio_to_visual_scene")
        if t_rel:
            text_relation_counts[str(t_rel)] += 1
        if s_rel:
            scene_relation_counts[str(s_rel)] += 1

    narration_multi_shot = {
        segment_id: shot_refs
        for segment_id, shot_refs in narration_to_shots.items()
        if len(shot_refs) > 1
    }

    structure_sequence = list(
        storyboard.get(
            "video_understanding", {}
        ).get("structure_sequence", [])
        or []
    )

    structure_signature = ">".join(
        str(x.get("stage") or "other")
        for x in structure_sequence
    )

    hook_candidate = storyboard.get(
        "video_understanding", {}
    ).get("hook_candidate", {}) or {}

    hook_modalities = []
    for key in ("audio", "visual_text", "visual_scene"):
        if str(hook_candidate.get(key, "")).strip():
            hook_modalities.append(key)

    proof_shots = []
    cta_shots = []

    for shot in shots:
        interpretation = shot.get("interpretation", {})
        primary = interpretation.get("primary_role")
        secondary = interpretation.get("secondary_roles", []) or []

        if interpretation.get(
            "proof_assessment", {}
        ).get("is_proof") is True:
            proof_shots.append(str(shot["shot_id"]))

        if primary == "CTA" or "CTA" in secondary:
            cta_shots.append(str(shot["shot_id"]))

    case_hash = sha256_file(case_path)
    storyboard_hash = sha256_file(storyboard_path)

    fingerprint = {
        "schema_version": SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "case_id": case_id,
        "source_case": {
            "path": str(case_path),
            "sha256": case_hash,
            "status": lifecycle.get("status"),
            "approved": lifecycle.get("approved"),
            "approved_at": lifecycle.get("approved_at"),
            "approved_by": lifecycle.get("approved_by"),
        },
        "identity": {
            "analysis_profile": case.get(
                "identity", {}
            ).get("analysis_profile"),
            "industry": case.get(
                "identity", {}
            ).get("industry"),
            "duration_seconds": video_duration,
        },
        "content_features": {
            "content_goal_candidate": storyboard.get(
                "video_understanding", {}
            ).get("content_goal_candidate"),
            "claims": storyboard.get(
                "video_understanding", {}
            ).get("claims", []),
            "verified_proof_count": len(
                storyboard.get(
                    "video_understanding", {}
                ).get("verified_proofs", [])
                or []
            ),
            "proof_shot_refs": proof_shots,
            "has_verified_proof": bool(proof_shots),
            "cta_shot_refs": cta_shots,
            "has_explicit_cta": bool(cta_shots),
        },
        "narration_features": {
            "segment_count": len(narration_track),
            "total_speech_seconds": round(
                narration_total_seconds, 6
            ),
            "speech_to_video_ratio": narration_density,
            "segment_duration_stats": summarize_numeric(
                narration_durations
            ),
            "segments_spanning_multiple_shots": {
                "count": len(narration_multi_shot),
                "segment_refs": narration_multi_shot,
            },
        },
        "visual_shot_features": {
            "shot_count": len(shots),
            "shot_duration_stats": summarize_numeric(
                shot_durations
            ),
            "shots_under_1s": shots_under_1s,
            "shots_under_1s_ratio": ratio(
                shots_under_1s, len(shots)
            ),
            "shots_under_0_5s": shots_under_0_5s,
            "shots_under_0_5s_ratio": ratio(
                shots_under_0_5s, len(shots)
            ),
            "primary_role_sequence": role_sequence,
            "primary_role_counts": dict(primary_roles),
            "secondary_role_counts": dict(secondary_roles),
            "onscreen_text_shot_count": onscreen_text_shots,
            "onscreen_text_shot_ratio": ratio(
                onscreen_text_shots, len(shots)
            ),
            "information_state_count": info_state_count,
            "shots_with_multiple_information_states": (
                multi_info_state_shots
            ),
        },
        "audio_visual_features": {
            "text_relation_counts": dict(
                text_relation_counts
            ),
            "scene_relation_counts": dict(
                scene_relation_counts
            ),
            "shots_linked_to_multiple_narration_segments": (
                multi_narration_shots
            ),
            "narration_and_shots_are_separate_tracks": True,
            "shot_to_narration_cardinality": "many_to_many",
        },
        "structure_features": {
            "structure_signature": structure_signature,
            "structure_sequence": structure_sequence,
            "hook_modalities": hook_modalities,
            "hook_candidate": hook_candidate,
            "audio_role": storyboard.get(
                "video_understanding", {}
            ).get("audio_role"),
            "visual_text_role": storyboard.get(
                "video_understanding", {}
            ).get("visual_text_role"),
            "visual_scene_role": storyboard.get(
                "video_understanding", {}
            ).get("visual_scene_role"),
            "audio_visual_strategy": storyboard.get(
                "video_understanding", {}
            ).get("audio_visual_strategy"),
        },
        "pattern_mining_contract": {
            "eligible_for_pattern_mining": True,
            "this_artifact_is_not_a_pattern": True,
            "no_pattern_claim_from_single_case": True,
            "no_effectiveness_claim_without_performance_data": True,
            "cross_industry_reuse_not_inferred_from_one_case": True,
        },
        "quality": {
            "source_case_human_approved": True,
            "editing_grade": bool(
                case.get("quality", {}).get("editing_grade")
            ),
            "boundary_precision": case.get(
                "shot_evidence", {}
            ).get("boundary_precision"),
            "warnings": case.get(
                "quality", {}
            ).get("warnings", []),
        },
        "provenance": {
            "approved_case_sha256": case_hash,
            "storyboard_path": str(storyboard_path),
            "storyboard_sha256": storyboard_hash,
            "built_at": now_iso(),
            "ai_call_performed": False,
        },
    }

    elapsed = time.perf_counter() - started
    fingerprint["timing"] = {
        "build_elapsed_seconds": round(elapsed, 6)
    }

    project_root = Path(__file__).resolve().parents[1]
    output_root = (
        Path(args.output_root).expanduser().resolve()
        if args.output_root
        else project_root / "data" / "fingerprints"
    )

    output_dir = output_root / case_id
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = (
        output_dir / "case_fingerprint_v1.json"
    )
    json_path.write_text(
        json.dumps(
            fingerprint,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    summary = [
        "# Case Fingerprint V1",
        "",
        f"- Case ID: `{case_id}`",
        f"- Approved source case: `True`",
        f"- Profile: `{fingerprint['identity']['analysis_profile']}`",
        f"- Industry: `{fingerprint['identity']['industry']}`",
        f"- Duration: `{video_duration:.3f}s`",
        "",
        "## Pattern-ready Features",
        "",
        f"- Narration segments: `{len(narration_track)}`",
        f"- Shots: `{len(shots)}`",
        f"- Structure: `{structure_signature}`",
        f"- Primary role sequence: `{' > '.join(role_sequence)}`",
        f"- On-screen-text shot ratio: `{fingerprint['visual_shot_features']['onscreen_text_shot_ratio']}`",
        f"- Narration segments spanning multiple shots: `{len(narration_multi_shot)}`",
        f"- Verified Proof: `{bool(proof_shots)}`",
        f"- Explicit CTA: `{bool(cta_shots)}`",
        "",
        "## Guardrails",
        "",
        "- This is a Case Fingerprint, not a reusable Pattern.",
        "- One Case cannot establish a reusable Pattern.",
        "- Repetition is not effectiveness; performance evidence is a separate layer.",
        "- Cross-industry reuse is not inferred from one Case.",
        "",
        f"Build elapsed: `{elapsed:.3f}s`",
    ]

    summary_path = (
        output_dir / "case_fingerprint_v1_summary.md"
    )
    summary_path.write_text(
        "\n".join(summary),
        encoding="utf-8",
    )

    print()
    print("CASE FINGERPRINT V1 PASS")
    print(f"Case ID: {case_id}")
    print("Approved source case: True")
    print("Eligible for pattern mining: True")
    print(f"Narration segments: {len(narration_track)}")
    print(f"Shots: {len(shots)}")
    print(f"Structure: {structure_signature}")
    print(
        "Narration segments spanning multiple shots: "
        f"{len(narration_multi_shot)}"
    )
    print(f"Verified proof: {bool(proof_shots)}")
    print(f"Explicit CTA: {bool(cta_shots)}")
    print("AI call performed: False")
    print(f"Build elapsed: {elapsed:.3f}s")
    print(f"JSON: {json_path}")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()
