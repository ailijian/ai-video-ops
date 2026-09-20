from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from privacy_projection_v1 import (
    build_case_privacy_gate,
    load_privacy_projection,
    project_safe_semantic,
    project_safe_verbatim,
)
from speech_evidence_v1 import (
    SPEECH_DETECTED,
    SPEECH_NOT_DETECTED,
    require_audio_speech_evidence,
)


SCHEMA_VERSION = "case-v1.1-draft"
BUILDER_VERSION = "build_case_v1.py@0.3"


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


def artifact(path: Path, *, hash_file: bool = True) -> dict[str, Any]:
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    stat = path.stat()
    out = {
        "path": str(path),
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc
        ).isoformat(),
    }
    if hash_file:
        out["sha256"] = sha256_file(path)
    return out


def first_match(directory: Path, patterns: list[str]) -> Path | None:
    matches: list[Path] = []
    for pattern in patterns:
        matches.extend(p for p in directory.glob(pattern) if p.is_file())
    unique_matches = set(matches)
    if not unique_matches:
        return None
    if len(unique_matches) > 1:
        candidates = ", ".join(sorted(p.name for p in unique_matches))
        raise RuntimeError(
            "Ambiguous Case companion discovery. Provide an explicit companion "
            f"path instead of relying on filename order. Candidates: {candidates}"
        )
    return unique_matches.pop()


def resolve_companion(
    explicit_path: Path | None,
    directory: Path,
    patterns: list[str],
) -> Path | None:
    if explicit_path is not None:
        resolved = explicit_path.expanduser().resolve()
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        return resolved
    return first_match(directory, patterns)


def companion_assets(
    video: Path,
    *,
    music: Path | None = None,
    cover: Path | None = None,
    metadata: Path | None = None,
) -> dict[str, Path | None]:
    parent = video.parent
    return {
        "music": resolve_companion(
            music,
            parent,
            ["*_music.mp3", "*music*.mp3", "*.m4a", "*.wav", "*.mp3"],
        ),
        "cover": resolve_companion(
            cover,
            parent,
            ["*_cover.jpg", "*cover*.jpg", "*.jpg", "*.jpeg", "*.png", "*.webp"],
        ),
        "metadata": resolve_companion(
            metadata,
            parent,
            ["*_data.json", "*data*.json", "*metadata*.json"],
        ),
    }


def opt_artifact(path: Path | None) -> dict[str, Any] | None:
    return artifact(path) if path is not None and path.exists() else None


def segment_id(segment: dict[str, Any]) -> str | None:
    value = segment.get("segment_id", segment.get("id"))
    return None if value is None else str(value)


def manual_review_closed(review: Any) -> bool:
    if not isinstance(review, dict):
        return False
    items = list(review.get("items") or [])
    item_count = int(review.get("item_count", len(items)) or 0)
    pending_count = int(review.get("pending_count", item_count) or 0)
    status = str(review.get("status") or "").strip().lower()
    explicit_closed = status in {"closed", "complete", "completed", "passed"}
    no_review_required = review.get("required") is False
    return (
        (explicit_closed or no_review_required)
        and item_count == 0
        and pending_count == 0
        and not items
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Canonical Case V1.1 from current validated Stage-2 artifacts."
    )
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--profile", choices=["news", "mix"])
    parser.add_argument("--operator-profile-hint", choices=["mix", "news", "hybrid", "uncertain"])
    parser.add_argument("--industry", required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--audio-v1", required=True)
    parser.add_argument("--narration-review", required=True)
    parser.add_argument("--visual-manifest", required=True)
    parser.add_argument("--visual-v1", required=True)
    parser.add_argument("--shot-boundaries", required=True)
    parser.add_argument("--storyboard-v1", required=True)
    parser.add_argument("--privacy-projection", required=True)
    parser.add_argument(
        "--music",
        help="Explicit companion music/audio path; required when discovery is ambiguous.",
    )
    parser.add_argument(
        "--cover",
        help="Explicit companion cover path; required when discovery is ambiguous.",
    )
    parser.add_argument(
        "--metadata",
        help="Explicit companion metadata path; required when discovery is ambiguous.",
    )
    parser.add_argument("--source-url", default=None)
    parser.add_argument("--output-root", default=None)
    parser.add_argument(
        "--defer-manual-review",
        action="store_true",
        help="Allow only unresolved narration/shot decisions in a provisional, human-review-required Case candidate.",
    )
    args = parser.parse_args()
    if bool(args.profile) == bool(args.operator_profile_hint):
        parser.error("Provide exactly one of --profile or --operator-profile-hint")

    case_id = args.case_id

    video = Path(args.video).expanduser().resolve()
    audio_path = Path(args.audio_v1).expanduser().resolve()
    narration_path = Path(args.narration_review).expanduser().resolve()
    visual_manifest_path = Path(args.visual_manifest).expanduser().resolve()
    visual_v1_path = Path(args.visual_v1).expanduser().resolve()
    shot_path = Path(args.shot_boundaries).expanduser().resolve()
    storyboard_path = Path(args.storyboard_v1).expanduser().resolve()
    privacy_path = Path(args.privacy_projection).expanduser().resolve()

    for p in (
        video,
        audio_path,
        narration_path,
        visual_manifest_path,
        visual_v1_path,
        shot_path,
        storyboard_path,
        privacy_path,
    ):
        if not p.exists():
            raise FileNotFoundError(p)

    audio = read_json(audio_path)
    narration = read_json(narration_path)
    visual_manifest = read_json(visual_manifest_path)
    visual = read_json(visual_v1_path)
    shot_data = read_json(shot_path)
    storyboard = read_json(storyboard_path)
    privacy_context = load_privacy_projection(
        privacy_path,
        expected_case_id=case_id,
    )

    errors: list[str] = []
    warnings: list[str] = []
    safe_audio_transcript = project_safe_semantic(
        audio.get("transcript_raw", "")
    )
    privacy_gate = build_case_privacy_gate(
        privacy_context=privacy_context,
        derived_artifact={
            "audio_transcript_safe_semantic": safe_audio_transcript,
            "storyboard": {
                "shots": storyboard.get("shots", []),
                "video_understanding": storyboard.get(
                    "video_understanding", {}
                ),
                "claims_semantics": storyboard.get("claims_semantics"),
            },
        },
    )
    privacy_policy_version = str(
        privacy_context.get("privacy_policy_version")
        or privacy_context.get("policy_version")
        or ""
    )
    privacy_gate["privacy_policy_version"] = privacy_policy_version
    privacy_gate["privacy_projection_ref"] = str(privacy_path)
    if privacy_gate["library_safe"] is not True:
        errors.append(
            "Case privacy gate is not library-safe; rebuild derived "
            "artifacts from Privacy-Safe Evidence."
        )

    for name, data in (
        ("audio_v1", audio),
        ("narration_review_v1", narration),
        ("visual_manifest", visual_manifest),
        ("visual_v1", visual),
        ("shot_boundaries", shot_data),
        ("storyboard_v1", storyboard),
    ):
        found = data.get("case_id")
        if found is not None and str(found) != case_id:
            errors.append(
                f"{name}.case_id={found!r} does not match {case_id!r}"
            )

    words = list(audio.get("words") or [])
    word_ids = [str(x["word_id"]) for x in words]
    if not audio.get("validation", {}).get("passed"):
        errors.append("audio_v1 validation is not passed.")
    try:
        speech_evidence_status = require_audio_speech_evidence(audio)
    except RuntimeError as exc:
        errors.append(str(exc))
        speech_evidence_status = None

    audio_segments = list(audio.get("segments") or [])
    narration_segments = list(narration.get("segments") or [])
    narration_validation = narration.get("validation", {})
    required_narration_validation = (
        "passed",
        "segment_count_preserved",
        "segment_order_preserved",
        "segment_timestamps_preserved",
        "word_refs_preserved",
        "raw_word_count_preserved",
    )
    for key in required_narration_validation:
        if narration_validation.get(key) is not True:
            errors.append(f"narration_review_v1 validation {key!r} is not true.")
    if narration_validation.get("raw_words_modified") is not False:
        errors.append("narration_review_v1 reports that raw words were modified.")
    narration_review_is_closed = manual_review_closed(
        narration.get("manual_review")
    )
    if not narration_review_is_closed and not args.defer_manual_review:
        errors.append("narration_review_v1 manual review is not closed.")
    if len(narration_segments) != len(audio_segments):
        errors.append(
            "Narration segment count differs from the Audio V1 segment count."
        )
    if speech_evidence_status == SPEECH_NOT_DETECTED:
        if narration.get("review_mode") != "no_detected_speech":
            errors.append(
                "narration_review_v1 is not in no_detected_speech mode."
            )
        if narration.get("speech_evidence_status") != SPEECH_NOT_DETECTED:
            errors.append(
                "narration_review_v1 speech evidence status does not match audio_v1."
            )

    narration_word_refs: list[str] = []
    for index, (source, reviewed) in enumerate(
        zip(audio_segments, narration_segments),
        start=1,
    ):
        source_id = segment_id(source)
        reviewed_id = segment_id(reviewed)
        if source_id is None or reviewed_id is None or source_id != reviewed_id:
            errors.append(
                f"Narration segment {index} ID does not match Audio V1."
            )
        for field in ("start", "end"):
            if field not in source or field not in reviewed:
                errors.append(
                    f"Narration segment {index} is missing {field!r}."
                )
                continue
            if abs(float(source[field]) - float(reviewed[field])) > 1e-6:
                errors.append(
                    f"Narration segment {index} {field} differs from Audio V1."
                )
        source_refs = [str(x) for x in source.get("word_refs", [])]
        reviewed_refs = [str(x) for x in reviewed.get("word_refs", [])]
        if source_refs != reviewed_refs:
            errors.append(
                f"Narration segment {index} word_refs differ from Audio V1."
            )
        narration_word_refs.extend(reviewed_refs)

    if narration_word_refs != word_ids:
        errors.append(
            "Narration Review word_refs do not preserve all Audio V1 words exactly once."
        )

    visual_cov = visual.get("coverage", {})
    candidate_count = int(visual_cov.get("candidate_frame_count") or 0)
    analyzed_count = int(visual_cov.get("analyzed_frame_count") or 0)

    if visual_cov.get("coverage_label") != "candidate_complete":
        errors.append("visual_v1 is not candidate_complete.")
    if candidate_count != analyzed_count:
        errors.append(
            f"visual coverage mismatch: {analyzed_count}/{candidate_count}"
        )

    visual_frame_ids = [
        str(x["frame_id"])
        for x in (visual.get("frames") or [])
    ]

    shot_validation = shot_data.get("validation", {})
    if not shot_validation.get("passed"):
        errors.append("shot_boundaries validation is not passed.")
    if not shot_validation.get("all_visual_frames_assigned_exactly_once"):
        errors.append("shot_boundaries did not preserve all visual frames exactly once.")
    if not shot_validation.get("all_audio_words_assigned_exactly_once"):
        errors.append("shot_boundaries did not preserve all audio words exactly once.")
    if (
        speech_evidence_status == SPEECH_NOT_DETECTED
        and shot_data.get("speech_evidence_status") != SPEECH_NOT_DETECTED
    ):
        errors.append("shot_boundaries speech evidence status does not match audio_v1.")
    boundary_review_is_closed = manual_review_closed(
        shot_data.get("manual_review")
    )
    if not boundary_review_is_closed and not args.defer_manual_review:
        errors.append("shot_boundaries manual review is not closed.")

    deterministic_shots = list(shot_data.get("shots") or [])
    if not deterministic_shots:
        errors.append("shot_boundaries contains no shots.")

    projected_words: list[str] = []
    projected_frames: list[str] = []

    for shot in deterministic_shots:
        projected_words.extend(
            str(x)
            for x in shot.get("audio_projection", {}).get("word_refs", [])
        )
        projected_frames.extend(
            str(x)
            for x in shot.get("visual_projection", {}).get("frame_refs", [])
        )

    if projected_words != word_ids:
        errors.append(
            "Canonical word projection/order mismatch between audio_v1 and shot_boundaries."
        )

    if projected_frames != visual_frame_ids:
        errors.append(
            "Canonical visual frame projection/order mismatch between visual_v1 and shot_boundaries."
        )

    board_validation = storyboard.get("validation", {})
    if not board_validation.get("passed"):
        errors.append("storyboard_v1 validation is not passed.")
    if board_validation.get("manual_review_closed") is not True and not args.defer_manual_review:
        errors.append("storyboard_v1 does not confirm closed Shot Boundary review.")
    if board_validation.get("narration_review_closed") is not True and not args.defer_manual_review:
        errors.append("storyboard_v1 does not confirm closed Narration review.")
    if args.defer_manual_review:
        if board_validation.get("narration_review_closed") is not narration_review_is_closed:
            errors.append("storyboard_v1 narration review state differs from narration evidence.")
        if board_validation.get("manual_review_closed") is not (
            narration_review_is_closed and boundary_review_is_closed
        ):
            errors.append("storyboard_v1 manual review state differs from source evidence.")
        for label, review in (
            ("narration", narration.get("manual_review")),
            ("shot", shot_data.get("manual_review")),
        ):
            if not isinstance(review, dict) or not isinstance(review.get("items"), list):
                errors.append(f"{label} review items are unavailable.")
            elif review.get("required") is True and not review["items"]:
                errors.append(f"{label} review has no actionable pending items.")
    if board_validation.get("pattern_not_generated") is not True:
        errors.append("storyboard_v1 did not preserve Pattern as not_performed.")
    if (
        speech_evidence_status == SPEECH_NOT_DETECTED
        and storyboard.get("speech_evidence_status") != SPEECH_NOT_DETECTED
    ):
        errors.append("storyboard_v1 speech evidence status does not match audio_v1.")

    board_shots = list(storyboard.get("shots") or [])
    det_ids = [str(x["shot_id"]) for x in deterministic_shots]
    board_ids = [str(x["shot_id"]) for x in board_shots]

    if det_ids != board_ids:
        errors.append("Storyboard shot IDs/order do not exactly match shot boundaries.")

    board_narration = list(storyboard.get("narration_track") or [])
    narration_ids = [segment_id(x) for x in narration_segments]
    board_narration_ids = [segment_id(x) for x in board_narration]
    if narration_ids != board_narration_ids:
        errors.append(
            "Storyboard narration IDs/order do not exactly match Narration Review."
        )

    det_by_id = {
        str(x["shot_id"]): x
        for x in deterministic_shots
    }

    for board_shot in board_shots:
        shot_id = str(board_shot["shot_id"])
        source = det_by_id.get(shot_id)
        if source is None:
            continue

        for field in ("start", "end", "duration"):
            if abs(float(board_shot[field]) - float(source[field])) > 1e-6:
                errors.append(
                    f"{shot_id}.{field} differs from shot boundary truth."
                )

        board_word_refs = list(
            board_shot.get("evidence", {}).get("audio_word_refs", [])
        )
        source_word_refs = list(
            source.get("audio_projection", {}).get("word_refs", [])
        )
        if board_word_refs != source_word_refs:
            errors.append(
                f"{shot_id} storyboard audio refs differ from shot boundary truth."
            )

        board_frame_refs = list(
            board_shot.get("evidence", {}).get("visual_frame_refs", [])
        )
        source_frame_refs = list(
            source.get("visual_projection", {}).get("frame_refs", [])
        )
        if board_frame_refs != source_frame_refs:
            errors.append(
                f"{shot_id} storyboard visual refs differ from shot boundary truth."
            )

    proof_shots = []
    for shot in board_shots:
        proof = shot.get("interpretation", {}).get("proof_assessment", {})
        if proof.get("is_proof") is True:
            proof_shots.append(str(shot["shot_id"]))

    verified_proofs = storyboard.get(
        "video_understanding", {}
    ).get("verified_proofs", [])

    claims = list(
        storyboard.get("video_understanding", {}).get("claims") or []
    )
    claims_semantics = storyboard.get("claims_semantics")
    if claims_semantics != (
        "candidate_unverified_unless_supported_by_verified_proofs"
    ):
        errors.append("Storyboard claims_semantics is not candidate/unverified.")
    strong_claim_statuses = {
        "verified",
        "evidence_backed",
        "evidence-backed",
        "proved",
        "proven",
    }
    for index, claim in enumerate(claims, start=1):
        status = str(claim.get("status") or "").strip().lower()
        if not verified_proofs and status in strong_claim_statuses:
            errors.append(
                f"Claim {index} is marked {status!r} without an effective verified proof."
            )

    if verified_proofs and not proof_shots:
        errors.append(
            "video_understanding has verified_proofs but no Shot was validated as proof."
        )

    gate_policy = str(
        privacy_gate.get("privacy_policy_version")
        or privacy_gate.get("policy_version")
        or ""
    )
    if not privacy_policy_version or gate_policy != privacy_policy_version:
        errors.append("Case privacy policy version does not match its projection.")
    if int(privacy_gate.get("unresolved_sensitive_items", -1)) != 0:
        errors.append("Case privacy gate has unresolved sensitive items.")
    if privacy_gate.get("derived_artifact_scan_passed") is not True:
        errors.append("Case derived artifact privacy scan did not pass.")

    boundary_precision = shot_data.get(
        "design_decision", {}
    ).get("current_boundary_precision", "unknown")

    if boundary_precision != "frame_exact":
        warnings.append(
            "Shot boundaries are candidate-frame approximate, not frame-exact editing cuts."
        )

    warnings.append(
        "Visual observation and Shot roles are AI-derived; human review remains required before Approved Case."
    )

    if errors:
        print("\nCASE V1.1 BUILD FAILED")
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(2)

    companions = companion_assets(
        video,
        music=Path(args.music) if args.music else None,
        cover=Path(args.cover) if args.cover else None,
        metadata=Path(args.metadata) if args.metadata else None,
    )

    duration = max(
        float(audio.get("duration_seconds") or 0),
        float(visual_manifest.get("duration_seconds") or 0),
        float(shot_data.get("duration_seconds") or 0),
    )

    case = {
        "schema_version": SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "case_id": case_id,
        "privacy_gate": privacy_gate,
        "lifecycle": {
            "status": "review_required",
            "approved": False,
            "retired": False,
            "built_at": now_iso(),
            "approval_rule": (
                "A human must review the original source against Reverse Storyboard V1 "
                "before this Case becomes eligible for production matching."
            ),
        },
        "identity": {
            "platform": "douyin",
            "source_url": args.source_url,
            "industry": args.industry,
            "duration_seconds": duration,
        },
        "source_evidence": {
            "video": artifact(video, hash_file=False),
            "music": opt_artifact(companions["music"]),
            "cover": opt_artifact(companions["cover"]),
            "metadata": opt_artifact(companions["metadata"]),
            "authority": "source",
        },
        "audio_evidence": {
            "speech_evidence_status": speech_evidence_status,
            "transcript_safe_semantic": safe_audio_transcript,
            "transcript_source_ref": {
                "path": str(audio_path),
                "field": "transcript_raw",
            },
            "segment_count": len(audio.get("segments") or []),
            "word_count": len(words),
            "has_speech": speech_evidence_status == SPEECH_DETECTED,
            "has_speech_evidence": speech_evidence_status == SPEECH_DETECTED,
            "artifact": artifact(audio_path),
            "engine": audio.get("engine"),
            "model": audio.get("model"),
            "authority": "faster-whisper + deterministic word timeline",
        },
        "narration_evidence": {
            "speech_evidence_status": speech_evidence_status,
            "segment_count": len(narration_segments),
            "changed_segment_count": sum(
                1 for segment in (
                    (storyboard.get("narration_track") or []) if args.defer_manual_review
                    else narration_segments
                )
                if segment.get("changed") is True
            ),
            "manual_review_closed": narration_review_is_closed,
            "reviewed_text_source_ref": {
                "path": str(storyboard_path) if args.defer_manual_review else str(narration_path),
                "field": "narration_track[*].text_safe_verbatim" if args.defer_manual_review else "segments[*].reviewed_text",
            },
            "artifact": artifact(narration_path),
            "authority": (
                "faster-whisper source ASR pending final Case review"
                if args.defer_manual_review and not narration_review_is_closed
                else "narration_review_v1"
            ),
        },
        "visual_evidence": {
            "candidate_frame_count": candidate_count,
            "analyzed_frame_count": analyzed_count,
            "coverage_label": visual_cov.get("coverage_label"),
            "artifact": artifact(visual_v1_path),
            "manifest_artifact": artifact(visual_manifest_path),
            "authority": {
                "frame_id_and_timestamp": "visual_manifest",
                "ocr_and_observation": visual.get(
                    "authority", {}
                ).get("ocr_and_observation", "qwen3-vl"),
            },
        },
        "shot_evidence": {
            "shot_count": len(deterministic_shots),
            "boundary_precision": boundary_precision,
            "artifact": artifact(shot_path),
            "authority": {
                "candidate_timestamps": "visual_candidate_frames",
                "boundary_selection": shot_data.get(
                    "design_decision", {}
                ).get("boundary_selector"),
                "audio_projection": "word_midpoint_exactly_once",
                "model_cannot_invent_timestamps": True,
            },
        },
        "storyboard": {
            "storyboard_type": "reverse",
            "shots": board_shots,
            "video_understanding": storyboard.get("video_understanding", {}),
            "claims_semantics": claims_semantics,
            "artifact": artifact(storyboard_path),
            "authority": storyboard.get("authority", {}),
            "model_interpretation_warning": (
                "Roles, narrative functions and video understanding are model-generated interpretation. "
                "Evidence refs, audio words, visual frames and Shot times remain authoritative."
            ),
        },
        "pattern_state": {
            "pattern_mining_performed": False,
            "pattern_candidates": [],
            "note": "V1 intentionally does not create reusable Patterns from a single Case.",
        },
        "quality": {
            "grade": "case_analysis",
            "editing_grade": False,
            "human_review_required": True,
            "proof_shot_ids": proof_shots,
            "verified_proof_count": len(
                verified_proofs if isinstance(verified_proofs, list) else []
            ),
            "claim_count": len(claims),
            "warnings": warnings,
        },
        "review_pending": {
            "mode": "deferred_to_final_case_review" if args.defer_manual_review else "none",
            "narration_item_count": len((narration.get("manual_review") or {}).get("items") or []),
            "shot_item_count": len((shot_data.get("manual_review") or {}).get("items") or []),
            "narration_sha256": sha256_file(narration_path),
            "shot_sha256": sha256_file(shot_path),
            "narration_items": [
                {
                    "segment_id": str(item.get("segment_id") or ""),
                    "source_text_safe_verbatim": project_safe_verbatim(item.get("source_text") or ""),
                    "suggested_text_safe_verbatim": project_safe_verbatim(item.get("reviewed_text") or ""),
                }
                for item in (narration.get("manual_review") or {}).get("items", [])
                if isinstance(item, dict)
            ],
            "requires_explicit_confirmation": not (
                narration_review_is_closed and boundary_review_is_closed
            ),
        },
        "timing": {
            "boundary_selection_seconds": shot_data.get(
                "timing", {}
            ).get("deepseek_boundary_selection_seconds"),
            "storyboard_model_seconds": storyboard.get(
                "timing", {}
            ).get("deepseek_storyboard_seconds"),
            "known_stage_seconds_total": round(
                float(
                    shot_data.get("timing", {}).get(
                        "deepseek_boundary_selection_seconds"
                    ) or 0
                )
                + float(
                    storyboard.get("timing", {}).get(
                        "deepseek_storyboard_seconds"
                    ) or 0
                ),
                6,
            ),
            "note": (
                "Qwen visual and Whisper timing are not backfilled here unless measured "
                "by their dedicated timing runs."
            ),
        },
        "validation": {
            "passed": True,
            "case_id_consistent": True,
            "audio_words_preserved_exactly_once": True,
            "speech_evidence_status_valid": True,
            "no_synthetic_speech_evidence": True,
            "visual_frames_preserved_exactly_once": True,
            "storyboard_shot_ids_match": True,
            "storyboard_times_match_shot_truth": True,
            "storyboard_audio_refs_match": True,
            "storyboard_visual_refs_match": True,
            "proof_consistency_valid": True,
            "narration_segments_match_audio_v1": True,
            "narration_word_refs_preserved_exactly_once": True,
            "narration_review_closed": narration_review_is_closed,
            "boundary_review_closed": boundary_review_is_closed,
            "privacy_gate_passed": True,
            "privacy_policy_version_match": True,
            "claims_remain_candidate_unverified": True,
            "pattern_not_generated": True,
            "human_approval_required": True,
            "auto_approved": False,
        },
        "source_artifacts": {
            "video": str(video),
            "audio_v1": str(audio_path),
            "narration_review_v1": str(narration_path),
            "visual_manifest": str(visual_manifest_path),
            "visual_v1": str(visual_v1_path),
            "shot_boundaries": str(shot_path),
            "privacy_projection_v1": str(privacy_path),
            "storyboard_v1": str(storyboard_path),
        },
        "provenance": {
            "audio_v1": artifact(audio_path),
            "narration_review_v1": artifact(narration_path),
            "visual_manifest": artifact(visual_manifest_path),
            "visual_v1": artifact(visual_v1_path),
            "shot_boundaries": artifact(shot_path),
            "storyboard_v1": artifact(storyboard_path),
            "privacy_projection_v1": artifact(privacy_path),
        },
    }
    if args.profile:
        case["identity"]["analysis_profile"] = args.profile
    if args.operator_profile_hint:
        case["operator_profile_hint"] = args.operator_profile_hint

    project_root = Path(__file__).resolve().parents[1]
    output_root = (
        Path(args.output_root).expanduser().resolve()
        if args.output_root
        else project_root / "data" / "cases"
    )
    output_dir = output_root / case_id
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "case_v1.json"
    json_path.write_text(
        json.dumps(case, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    md = [
        "# Canonical Case V1.1 Summary",
        "",
        f"- Case ID: `{case_id}`",
        f"- Status: `{case['lifecycle']['status']}`",
        f"- Approved: `{case['lifecycle']['approved']}`",
        f"- Profile: `{args.profile}`",
        f"- Industry: `{args.industry}`",
        f"- Duration: `{duration:.3f}s`",
        "",
        "## Coverage",
        "",
        f"- Audio segments: `{case['audio_evidence']['segment_count']}`",
        f"- Audio words: `{case['audio_evidence']['word_count']}`",
        f"- Narration Review segments: `{case['narration_evidence']['segment_count']}`",
        f"- Visual: `{analyzed_count}/{candidate_count}` (`{visual_cov.get('coverage_label')}`)",
        f"- Shots: `{len(deterministic_shots)}`",
        f"- Boundary precision: `{boundary_precision}`",
        f"- Verified Proofs: `{case['quality']['verified_proof_count']}`",
        "",
        "## Validation",
        "",
    ]

    for key, value in case["validation"].items():
        md.append(f"- {key}: `{value}`")

    md += [
        "",
        "## Human Review Gate",
        "",
        "- [ ] 原视频 Shot 数与 14 个逆向 Shot 基本一致，无明显漏镜头/假切镜。",
        "- [ ] OCR 关键文案与原视频一致。",
        "- [ ] 旁白整体内容与原视频一致；词级碎片只是时间重叠视图，不视为文案改写。",
        "- [ ] Shot Role 基本合理。",
        "- [ ] 没有把普通经营动作误标为 Proof。",
        "- [ ] 没有把人物身份、职业、店铺归属或商业成功当成事实。",
        "- [ ] 当前 Case 值得进入公司正式案例库。",
        "",
        "只有以上人工 Gate 通过后，才能显式把 Case 升级为 `approved`。",
        "",
        "## Known Limits",
        "",
    ]

    for warning in warnings:
        md.append(f"- {warning}")

    summary_path = output_dir / "case_v1_summary.md"
    summary_path.write_text("\n".join(md), encoding="utf-8")

    print()
    print("CASE V1.1 BUILD PASS")
    print(f"Case ID: {case_id}")
    print("Status: review_required")
    print("Approved: False")
    print(f"Audio words: {len(words)}")
    print(f"Narration segments: {len(narration_segments)}")
    print(f"Visual coverage: {analyzed_count}/{candidate_count}")
    print(f"Shots: {len(deterministic_shots)}")
    print(f"Boundary precision: {boundary_precision}")
    print(f"Verified proofs: {case['quality']['verified_proof_count']}")
    print(f"Known measured DeepSeek stages: {case['timing']['known_stage_seconds_total']:.2f}s")
    print(f"JSON: {json_path}")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()
