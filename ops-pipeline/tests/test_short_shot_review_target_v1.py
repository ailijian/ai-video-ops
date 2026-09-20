import importlib.util
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("shot_boundary_target", SCRIPTS / "build_shot_boundaries_v1.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_first_short_shot_reviews_next_boundary_not_mandatory_video_start():
    shots = [
        {"shot_id": "S001", "start": 0, "end": 0.28, "duration": 0.28,
         "boundary": {"selected_from_frame_ref": "frame_000000000ms.jpg"}},
        {"shot_id": "S002", "start": 0.28, "end": 3, "duration": 2.72,
         "boundary": {"selected_from_frame_ref": "frame_000000280ms.jpg"}},
    ]
    item = module.short_shot_review_item(shots, 0)
    assert item["boundary_frame_id"] == "frame_000000280ms.jpg"
    assert item["merge_allowed"] is True
    shots[1]["boundary"]["review_action"] = "keep"
    assert module.short_shot_review_item(shots, 0) is None


def test_last_short_shot_reviews_own_start_and_single_shot_cannot_merge():
    shots = [
        {"shot_id": "S001", "start": 0, "end": 2, "duration": 2,
         "boundary": {"selected_from_frame_ref": "frame_000000000ms.jpg"}},
        {"shot_id": "S002", "start": 2, "end": 2.25, "duration": 0.25,
         "boundary": {"selected_from_frame_ref": "frame_000002000ms.jpg"}},
    ]
    assert module.short_shot_review_item(shots, 1)["boundary_frame_id"] == "frame_000002000ms.jpg"
    single = [dict(shots[1], start=0, boundary={"selected_from_frame_ref": "frame_000000000ms.jpg"})]
    assert module.short_shot_review_item(single, 0)["merge_allowed"] is False
