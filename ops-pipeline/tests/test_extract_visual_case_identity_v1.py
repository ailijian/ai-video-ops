from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "extract_visual_evidence.py"
SPEC = importlib.util.spec_from_file_location("extract_visual_evidence", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_explicit_case_id_overrides_generic_provider_filename(tmp_path: Path):
    source = tmp_path / "source.mp4"
    case_id = "7682442957798161531"
    assert module.extract_case_id(source) != case_id
    assert module.resolve_case_id(source, case_id) == case_id


def test_legacy_filename_fallback_remains_available(tmp_path: Path):
    source = tmp_path / "clip_7682442957798161531.mp4"
    assert module.resolve_case_id(source, None) == "7682442957798161531"


def test_provider_named_video_writes_manifest_under_explicit_case_id(tmp_path: Path):
    source = tmp_path / "source.mp4"
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"mp4v"), 5, (96, 64))
    assert writer.isOpened()
    try:
        for index in range(10):
            writer.write(np.full((64, 96, 3), index * 20, dtype=np.uint8))
    finally:
        writer.release()

    case_id = "7682442957798161531"
    output = tmp_path / "visual"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(source), "--case-id", case_id,
         "--output-root", str(output)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0, result.stderr[-1000:]
    manifest = json.loads((output / case_id / "visual_evidence_manifest.json").read_text(encoding="utf-8"))
    assert manifest["case_id"] == case_id
    assert manifest["frames"]
    assert not (output / module.extract_case_id(source) / "visual_evidence_manifest.json").exists()


@pytest.mark.parametrize("value", ["../other", "short", "7682442957798161531/other"])
def test_explicit_case_id_rejects_unsafe_values(tmp_path: Path, value: str):
    with pytest.raises(ValueError):
        module.resolve_case_id(tmp_path / "source.mp4", value)
