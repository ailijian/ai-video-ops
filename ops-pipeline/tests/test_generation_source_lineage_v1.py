from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from match_generation_sources_v1 import (  # noqa: E402
    case_assessment_matches_source_lineage,
    case_compatibility_approval_matches_source_lineage,
)


def source(case_sha: str = "a" * 64, fingerprint_sha: str = "b" * 64) -> dict:
    return {
        "case": {"sha256": case_sha},
        "fingerprint": {"sha256": fingerprint_sha},
    }


def test_coverage_assessment_for_another_case_fork_is_stale_non_authoritative() -> None:
    assessment = {
        "case_id": "case-a",
        "lineage": {
            "approved_case": {"sha256": "c" * 64},
            "fingerprint": {"sha256": "d" * 64},
        },
        "legacy_current_truth": {"compatible_profiles": ["mix"]},
    }
    assert case_assessment_matches_source_lineage(assessment, source()) is False
    assessment["lineage"]["approved_case"]["sha256"] = "a" * 64
    assessment["lineage"]["fingerprint"]["sha256"] = "b" * 64
    assert case_assessment_matches_source_lineage(assessment, source()) is True


def test_human_compatibility_approval_cannot_transfer_between_case_forks() -> None:
    approval = {
        "case_id": "case-a",
        "approved_compatible_generation_profiles": ["mix"],
        "source_approved_case_ref": {"sha256": "c" * 64},
        "fingerprint_ref": {"sha256": "d" * 64},
    }
    assert case_compatibility_approval_matches_source_lineage(approval, source()) is False
    approval["source_approved_case_ref"]["sha256"] = "a" * 64
    approval["fingerprint_ref"]["sha256"] = "b" * 64
    assert case_compatibility_approval_matches_source_lineage(approval, source()) is True
