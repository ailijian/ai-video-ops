from __future__ import annotations

from typing import Any


SPEECH_DETECTED = "detected"
SPEECH_NOT_DETECTED = "not_detected"
SPEECH_UNCERTAIN = "uncertain"


def classify_transcription_speech_evidence(raw: dict[str, Any]) -> str:
    """Classify ASR evidence without claiming that speech objectively is absent."""

    segments = list(raw.get("segments") or [])
    discarded_segments = list(raw.get("discarded_segments") or [])
    if segments:
        return SPEECH_DETECTED
    if discarded_segments:
        return SPEECH_UNCERTAIN
    return SPEECH_NOT_DETECTED


def require_audio_speech_evidence(audio: dict[str, Any]) -> str:
    """Validate the canonical audio evidence/status relationship.

    Historical speechful artifacts are compatible because their non-empty
    segments are unambiguous. Empty evidence must carry the new explicit
    ``not_detected`` status; it is never inferred from absence alone.
    """

    segments = list(audio.get("segments") or [])
    words = list(audio.get("words") or [])
    transcript = audio.get("transcript_raw")
    explicit_status = audio.get("speech_evidence_status")

    if explicit_status is None and segments:
        status = SPEECH_DETECTED
    elif explicit_status in {
        SPEECH_DETECTED,
        SPEECH_NOT_DETECTED,
        SPEECH_UNCERTAIN,
    }:
        status = str(explicit_status)
    else:
        raise RuntimeError(
            "audio_v1 has no valid explicit speech_evidence_status."
        )

    if status == SPEECH_UNCERTAIN:
        raise RuntimeError(
            "audio_v1 speech evidence is uncertain; manual handling is required."
        )

    if status == SPEECH_DETECTED:
        if not segments:
            raise RuntimeError(
                "audio_v1 marks speech detected but contains no segments."
            )
        if not words:
            raise RuntimeError(
                "audio_v1 marks speech detected but contains no word-level evidence."
            )
        return status

    if segments or words:
        raise RuntimeError(
            "audio_v1 marks speech not_detected but contains speech evidence."
        )
    if transcript not in ("", None):
        raise RuntimeError(
            "audio_v1 marks speech not_detected but transcript_raw is not empty."
        )
    return status
