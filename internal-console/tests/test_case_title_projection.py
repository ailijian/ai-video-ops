import hashlib
import json
from pathlib import Path

from app.canonical_gateway import _case_title, _project_case, _source_caption


CASE_ID = "7687296010611280827"


def approved_case(tmp_path: Path, metadata: dict) -> tuple[Path, Path, Path]:
    root = tmp_path / CASE_ID
    root.mkdir()
    metadata_path = root / "source_metadata_v1.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    case_path = root / "case_v1.json"
    case_path.write_text(json.dumps({
        "case_id": CASE_ID,
        "lifecycle": {"status": "approved"},
        "identity": {"platform": "douyin", "source_url": f"https://www.douyin.com/video/{CASE_ID}"},
        "source_evidence": {
            "video": {"path": str(root / "source.mp4")},
            "metadata": {"path": str(metadata_path)},
        },
    }, ensure_ascii=False), encoding="utf-8")
    receipt_path = root / "approval_receipt.json"
    receipt_path.write_text(json.dumps({"decision": "approved", "human_gate": True}), encoding="utf-8")
    return case_path, metadata_path, receipt_path


def test_paid_provider_title_projects_as_approved_case_name_without_modifying_artifacts(tmp_path: Path):
    caption = "我们会用心倾听，每一位顾客的需求 #同城好店推荐"
    case_path, metadata_path, receipt_path = approved_case(tmp_path, {
        "provider": "qiyun", "title": caption,
    })
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest()
              for path in (case_path, metadata_path, receipt_path)}
    assert _project_case(case_path).title == caption
    assert _case_title(json.loads(case_path.read_text(encoding="utf-8")), case_path) == caption
    assert _source_caption({"title": caption}, max_length=360) == caption
    assert {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in before} == before


def test_legacy_desc_keeps_priority_over_paid_title(tmp_path: Path):
    case_path, _, _ = approved_case(tmp_path, {
        "desc": "原来的视频描述，保持旧命名方式", "title": "另一份付费标题",
    })
    assert _project_case(case_path).title == "原来的视频描述，保持旧命名方式"
    assert _case_title(json.loads(case_path.read_text(encoding="utf-8")), case_path) == "原来的视频描述，保持旧命名方式"


def test_missing_provider_caption_does_not_expose_temporary_source_filename(tmp_path: Path):
    case_path, _, _ = approved_case(tmp_path, {"provider": "qiyun", "title": ""})
    expected = f"抖音案例 {CASE_ID[-6:]}"
    assert _project_case(case_path).title == expected
    assert _case_title(json.loads(case_path.read_text(encoding="utf-8")), case_path) == expected
