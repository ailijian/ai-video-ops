from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from transcribe_case import implausible_speech_rate  # noqa: E402


def test_timing_guard_flags_timestamp_impossible_asr_segment():
    flagged, observed = implausible_speech_rate(start=20.78, end=20.98, word_count=15)

    assert flagged is True
    assert round(observed, 1) == 75.0


def test_timing_guard_keeps_normal_speech_and_short_fragments():
    normal, normal_rate = implausible_speech_rate(start=0.0, end=20.78, word_count=97)
    fragment, _ = implausible_speech_rate(start=0.0, end=0.2, word_count=5)

    assert normal is False
    assert round(normal_rate, 1) == 4.7
    assert fragment is False
