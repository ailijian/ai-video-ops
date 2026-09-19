from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_audio_word_timeline_v1 as audio_builder  # noqa: E402
import approve_case_v1 as case_approver  # noqa: E402
import build_case_fingerprint_v1 as fingerprint_builder  # noqa: E402
import build_case_v1 as case_builder  # noqa: E402
import build_narration_review_v1 as narration_builder  # noqa: E402
import build_privacy_projection_v1 as privacy_builder  # noqa: E402
import build_shot_boundaries_v1 as shot_builder  # noqa: E402
import case_analysis_v1 as case_analysis  # noqa: E402
import generate_reverse_storyboard as storyboard_builder  # noqa: E402
from speech_evidence_v1 import (  # noqa: E402
    SPEECH_DETECTED,
    SPEECH_NOT_DETECTED,
    SPEECH_UNCERTAIN,
    classify_transcription_speech_evidence,
)


CASE_ID = "7682442957798161531"


def write_json(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run_main(monkeypatch: pytest.MonkeyPatch, module, args: list[str]) -> None:
    monkeypatch.setattr(sys, "argv", [str(module.__file__), *args])
    module.main()


def raw_transcription(*, segments: list, discarded: list | None = None) -> dict:
    return {
        "source_file": "fixture.mp4",
        "model": "large-v3",
        "device": "cpu",
        "compute_type": "int8",
        "language": "zh",
        "language_probability": 0.99,
        "duration": 4.0,
        "discarded_segments": discarded or [],
        "segments": segments,
    }


def test_speech_evidence_classification_is_evidence_based() -> None:
    assert (
        classify_transcription_speech_evidence(raw_transcription(segments=[{}]))
        == SPEECH_DETECTED
    )
    assert (
        classify_transcription_speech_evidence(raw_transcription(segments=[]))
        == SPEECH_NOT_DETECTED
    )
    assert (
        classify_transcription_speech_evidence(
            raw_transcription(segments=[], discarded=[{"reason": "guard"}])
        )
        == SPEECH_UNCERTAIN
    )


def test_detected_speech_still_requires_word_timestamps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = write_json(
        tmp_path / "transcript_segments.json",
        raw_transcription(
            segments=[{"start": 0.0, "end": 1.0, "text": "有声音", "words": []}]
        ),
    )
    with pytest.raises(SystemExit) as exc:
        run_main(
            monkeypatch,
            audio_builder,
            [
                "--case-id",
                CASE_ID,
                "--audio",
                str(raw),
                "--output-root",
                str(tmp_path / "audio"),
            ],
        )
    assert exc.value.code == 2


def test_detected_speech_timeline_behavior_is_preserved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_dir = tmp_path / "transcription"
    raw = write_json(
        raw_dir / "transcript_segments.json",
        raw_transcription(
            segments=[
                {
                    "start": 0.25,
                    "end": 1.25,
                    "text": "正常语音",
                    "words": [
                        {
                            "start": 0.25,
                            "end": 1.25,
                            "word": "正常语音",
                            "probability": 0.99,
                        }
                    ],
                }
            ]
        ),
    )
    (raw_dir / "transcript_raw.txt").write_text("正常语音", encoding="utf-8")
    output = tmp_path / "audio"

    run_main(
        monkeypatch,
        audio_builder,
        [
            "--case-id",
            CASE_ID,
            "--audio",
            str(raw),
            "--output-root",
            str(output),
        ],
    )

    timeline = read_json(output / "audio_word_timeline_v1.json")
    assert timeline["speech_evidence_status"] == SPEECH_DETECTED
    assert timeline["transcript_raw"] == "正常语音"
    assert len(timeline["segments"]) == 1
    assert len(timeline["words"]) == 1
    assert timeline["coverage"]["speech_start"] == 0.25
    assert timeline["coverage"]["speech_end"] == 1.25


def test_discarded_only_transcription_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = write_json(
        tmp_path / "transcript_segments.json",
        raw_transcription(
            segments=[],
            discarded=[{"reason": "implausible_speech_rate", "text": "可疑片段"}],
        ),
    )
    with pytest.raises(RuntimeError, match="speech evidence is uncertain"):
        run_main(
            monkeypatch,
            audio_builder,
            [
                "--case-id",
                CASE_ID,
                "--audio",
                str(raw),
                "--output-root",
                str(tmp_path / "audio"),
            ],
        )


def build_speechless_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Path]:
    speechless_raw = raw_transcription(segments=[])
    speechless_raw["initial_prompt"] = "下载标题不能成为语音事实"
    raw_path = write_json(
        tmp_path / "transcript_segments.json",
        speechless_raw,
    )
    audio_root = tmp_path / "audio"
    run_main(
        monkeypatch,
        audio_builder,
        [
            "--case-id",
            CASE_ID,
            "--audio",
            str(raw_path),
            "--output-root",
            str(audio_root),
        ],
    )
    audio_path = audio_root / "audio_word_timeline_v1.json"
    audio = read_json(audio_path)
    assert audio["speech_evidence_status"] == SPEECH_NOT_DETECTED
    assert audio["segments"] == []
    assert audio["words"] == []
    assert audio["transcript_raw"] == ""
    assert "下载标题不能成为语音事实" not in json.dumps(
        audio, ensure_ascii=False
    )
    assert audio["coverage"]["speech_start"] is None
    assert audio["coverage"]["speech_end"] is None

    frame_ids = [f"frame_{index:09d}ms.jpg" for index in range(4)]
    visual_path = write_json(
        tmp_path / "visual_timeline_v1.json",
        {
            "case_id": CASE_ID,
            "coverage": {
                "coverage_label": "candidate_complete",
                "candidate_frame_count": 4,
                "analyzed_frame_count": 4,
            },
            "authority": {"ocr_and_observation": "qwen3-vl"},
            "frames": [
                {
                    "frame_id": frame_id,
                    "timestamp_seconds": float(index),
                    "ocr_raw": f"画面文字{index}",
                    "scene_summary": f"视觉场景{index}",
                    "visual_change_from_previous": "" if index == 0 else "连续画面",
                    "information_change": "NO",
                }
                for index, frame_id in enumerate(frame_ids)
            ],
        },
    )
    manifest_path = write_json(
        tmp_path / "visual_evidence_manifest.json",
        {
            "case_id": CASE_ID,
            "duration_seconds": 4.0,
            "frames": [
                {"filename": frame_id, "reasons": []} for frame_id in frame_ids
            ],
        },
    )
    privacy_root = tmp_path / "privacy"
    run_main(
        monkeypatch,
        privacy_builder,
        [
            "--case-id",
            CASE_ID,
            "--visual-v1",
            str(visual_path),
            "--audio-v1",
            str(audio_path),
            "--output-root",
            str(privacy_root),
        ],
    )
    privacy_path = privacy_root / "privacy_projection_v1.json"
    privacy = read_json(privacy_path)
    assert privacy["speech_evidence_status"] == SPEECH_NOT_DETECTED
    assert all(
        record["source_ref"] != "audio_word_timeline_v1.json"
        for record in privacy["annotations"]
    )

    monkeypatch.setattr(
        narration_builder,
        "get_client",
        lambda: (_ for _ in ()).throw(AssertionError("unexpected narration model call")),
    )
    narration_root = tmp_path / "narration"
    run_main(
        monkeypatch,
        narration_builder,
        [
            "--case-id",
            CASE_ID,
            "--audio-v1",
            str(audio_path),
            "--visual-v1",
            str(visual_path),
            "--privacy-projection",
            str(privacy_path),
            "--output-root",
            str(narration_root),
        ],
    )
    narration_path = narration_root / "narration_review_v1.json"
    narration = read_json(narration_path)
    assert narration["review_mode"] == "no_detected_speech"
    assert narration["segments"] == []
    assert "画面文字" not in narration["reviewed_transcript_raw"]
    assert "下载标题" not in narration["reviewed_transcript_raw"]
    assert narration["manual_review"]["required"] is False
    assert narration["summary"]["remote_model_calls"] == 0
    assert narration["timing"]["current_run_model_compute_seconds"] == 0.0

    decisions = [
        {
            "frame_id": frame_id,
            "boundary_before": index == 0,
            "reason_type": "video_start" if index == 0 else "same_shot_motion",
            "reason": "视频开始" if index == 0 else "连续画面",
            "confidence": "high",
        }
        for index, frame_id in enumerate(frame_ids)
    ]

    class FakeCompletions:
        def create(self, **_kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps({"decisions": decisions}, ensure_ascii=False)
                        )
                    )
                ],
                usage=SimpleNamespace(
                    prompt_tokens=1,
                    completion_tokens=1,
                    total_tokens=2,
                ),
            )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions())
    )
    monkeypatch.setattr(shot_builder, "get_client", lambda: fake_client)
    shots_root = tmp_path / "shots"
    run_main(
        monkeypatch,
        shot_builder,
        [
            "--case-id",
            CASE_ID,
            "--visual-v1",
            str(visual_path),
            "--visual-manifest",
            str(manifest_path),
            "--audio-v1",
            str(audio_path),
            "--privacy-projection",
            str(privacy_path),
            "--output-root",
            str(shots_root),
        ],
    )
    shots_path = shots_root / "shot_boundaries_v1_1.json"
    shots = read_json(shots_path)
    assert shots["validation"]["audio_word_count"] == 0
    assert shots["validation"]["all_audio_words_assigned_exactly_once"] is True
    assert all(shot["audio_projection"]["word_refs"] == [] for shot in shots["shots"])

    annotation = {
        "shot_id": "S001",
        "primary_role": "context",
        "secondary_roles": [],
        "narrative_function": "展示可观察的视觉结构",
        "audio_to_visual_text": "independent",
        "audio_to_visual_scene": "independent",
        "proof_assessment": {
            "is_proof": False,
            "proof_type": None,
            "supports_claim": "",
            "basis": "",
        },
        "confidence": "high",
        "uncertainties": [],
    }
    reuse_path = write_json(
        tmp_path / "reuse_storyboard.json",
        {
            "shots": [{"interpretation": annotation}],
            "video_understanding": {
                "content_goal_candidate": "视觉内容候选",
                "hook_candidate": {
                    "audio": "",
                    "visual_text": "画面文字",
                    "visual_scene": "视觉场景",
                },
                "audio_role": "no_detected_speech",
                "visual_text_role": "提供画面文字",
                "visual_scene_role": "提供视觉结构",
                "audio_visual_strategy": "visual_only_evidence",
                "structure_sequence": [
                    {
                        "stage": "setup",
                        "shot_refs": ["S001"],
                        "description": "视觉开场",
                    }
                ],
                "claims": [],
                "verified_proofs": [],
                "uncertainties": ["未检测到可用语音证据"],
            },
        },
    )
    monkeypatch.setattr(
        storyboard_builder,
        "call_model_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unexpected storyboard model call")
        ),
    )
    storyboard_root = tmp_path / "storyboard"
    run_main(
        monkeypatch,
        storyboard_builder,
        [
            "--shot-boundaries",
            str(shots_path),
            "--audio-v1",
            str(audio_path),
            "--narration-review",
            str(narration_path),
            "--privacy-projection",
            str(privacy_path),
            "--reuse-existing",
            str(reuse_path),
            "--output-root",
            str(storyboard_root),
        ],
    )
    storyboard_path = storyboard_root / "reverse_storyboard_v1.json"
    storyboard = read_json(storyboard_path)
    assert storyboard["speech_evidence_status"] == SPEECH_NOT_DETECTED
    assert storyboard["narration_track"] == []
    assert storyboard["validation"]["narration_segment_count"] == 0

    video_path = tmp_path / f"source_{CASE_ID}.mp4"
    video_path.write_bytes(b"fixture-media")
    candidate_root = tmp_path / "candidate"
    run_main(
        monkeypatch,
        case_builder,
        [
            "--case-id",
            CASE_ID,
            "--profile",
            "mix",
            "--industry",
            "测试行业",
            "--video",
            str(video_path),
            "--audio-v1",
            str(audio_path),
            "--narration-review",
            str(narration_path),
            "--visual-manifest",
            str(manifest_path),
            "--visual-v1",
            str(visual_path),
            "--shot-boundaries",
            str(shots_path),
            "--storyboard-v1",
            str(storyboard_path),
            "--privacy-projection",
            str(privacy_path),
            "--source-url",
            f"https://www.douyin.com/video/{CASE_ID}",
            "--output-root",
            str(candidate_root),
        ],
    )
    candidate_path = candidate_root / CASE_ID / "case_v1.json"
    candidate = read_json(candidate_path)
    assert candidate["audio_evidence"]["speech_evidence_status"] == "not_detected"
    assert candidate["audio_evidence"]["has_speech_evidence"] is False
    assert candidate["audio_evidence"]["segment_count"] == 0
    assert candidate["audio_evidence"]["word_count"] == 0
    assert candidate["narration_evidence"]["segment_count"] == 0
    assert candidate["lifecycle"]["status"] == "review_required"
    assert candidate["lifecycle"]["approved"] is False
    assert candidate["quality"]["human_review_required"] is True

    return {
        "raw": raw_path,
        "audio": audio_path,
        "visual": visual_path,
        "manifest": manifest_path,
        "privacy": privacy_path,
        "narration": narration_path,
        "shots": shots_path,
        "storyboard": storyboard_path,
        "candidate": candidate_path,
        "video": video_path,
    }


def test_no_detected_speech_full_canonical_chain_and_model_accounting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = build_speechless_chain(tmp_path, monkeypatch)

    repo = tmp_path / "repo"
    pipeline = repo / "ops-pipeline"
    downloader = repo / "douyin-downloader"
    pipeline.mkdir(parents=True)
    downloader.mkdir(parents=True)
    operation = case_analysis.Orchestrator(
        pipeline_root=pipeline,
        repo_root=repo,
        downloader_root=downloader,
        source_url=f"https://www.douyin.com/video/{CASE_ID}",
        attempt_id="attempt_speechless_001",
        profile="mix",
        industry="测试行业",
        reanalyze=False,
    )
    attempt = operation.attempt_root
    target_video = attempt / f"source_{CASE_ID}.mp4"
    target_video.parent.mkdir(parents=True, exist_ok=True)
    target_video.write_bytes(artifacts["video"].read_bytes())
    target_metadata = write_json(
        attempt / "source_metadata_v1.json",
        {"aweme_id": CASE_ID, "desc": "fixture"},
    )
    acquisition = {
        "schema_version": "case-source-acquisition-v1.0",
        "case_id": CASE_ID,
        "stable_video_id": CASE_ID,
        "source_url": f"https://www.douyin.com/video/{CASE_ID}",
        "platform": "douyin",
        "video": str(target_video),
        "metadata": str(target_metadata),
        "source_video_sha256": hashlib.sha256(target_video.read_bytes()).hexdigest(),
        "media_rights_granted": False,
        "production_footage_pool_eligible": False,
    }
    write_json(attempt / "source_acquisition_v1.json", acquisition)

    destinations = {
        "raw": attempt
        / "evidence"
        / "transcription"
        / target_video.stem
        / "transcript_segments.json",
        "audio": attempt / "evidence" / "audio_v1" / "audio_word_timeline_v1.json",
        "visual": attempt
        / "evidence"
        / "visual"
        / CASE_ID
        / "visual_v1"
        / "visual_timeline_v1.json",
        "manifest": attempt
        / "evidence"
        / "visual"
        / CASE_ID
        / "visual_evidence_manifest.json",
        "privacy": attempt / "evidence" / "privacy" / "privacy_projection_v1.json",
        "narration": attempt / "evidence" / "narration" / "narration_review_v1.json",
        "shots": attempt / "evidence" / "shots" / "shot_boundaries_v1_1.json",
        "storyboard": attempt / "evidence" / "storyboard" / "reverse_storyboard_v1.json",
        "candidate": attempt / "candidate_cases" / CASE_ID / "case_v1.json",
    }
    for key, destination in destinations.items():
        value = read_json(artifacts[key])
        if key == "raw":
            value["source_file"] = str(target_video)
        write_json(destination, value)

    monkeypatch.setattr(
        operation,
        "run_command",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("all canonical checkpoints should be recovered")
        ),
    )
    cleanup_calls: list[str] = []
    monkeypatch.setattr(
        case_analysis,
        "cleanup_successful_attempt",
        lambda *_args, **_kwargs: cleanup_calls.append("cleanup"),
    )

    state = operation.run()

    assert state["status"] == "awaiting_review"
    assert state["speech_evidence_status"] == "not_detected"
    assert state["model_call_accounting"]["narration_remote_calls"] == 0
    assert cleanup_calls == ["cleanup"]
    structure_boundaries = [
        item["boundary"]
        for item in state["model_calls"]
        if item["stage"] == "structure"
    ]
    assert "privacy_safe_narration_review" not in structure_boundaries
    assert structure_boundaries == [
        "privacy_safe_shot_boundary_selection",
        "privacy_safe_reverse_storyboard",
    ]

    approved_candidate = destinations["candidate"]
    run_main(
        monkeypatch,
        case_approver,
        [
            "--case",
            str(approved_candidate),
            "--reviewer",
            "fixture-human-reviewer",
            "--note",
            "Explicit human approval fixture.",
        ],
    )
    approved = read_json(approved_candidate)
    receipt = read_json(approved_candidate.parent / "approval_receipt.json")
    assert approved["lifecycle"]["approved"] is True
    assert approved["validation"]["auto_approved"] is False
    assert approved["quality"]["human_review_completed"] is True
    assert receipt["human_gate"] is True

    fingerprint_root = tmp_path / "fingerprints"
    run_main(
        monkeypatch,
        fingerprint_builder,
        [
            "--case",
            str(approved_candidate),
            "--output-root",
            str(fingerprint_root),
        ],
    )
    fingerprint = read_json(
        fingerprint_root / CASE_ID / "case_fingerprint_v1.json"
    )
    assert fingerprint["narration_features"]["speech_evidence_status"] == "not_detected"
    assert fingerprint["narration_features"]["segment_count"] == 0
    assert fingerprint["narration_features"]["total_speech_seconds"] == 0
