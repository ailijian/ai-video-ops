from __future__ import annotations

import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from production_profile_v1 import (  # noqa: E402
    validate_case_source_governance_companion_v1,
)


def fresh_companion() -> dict:
    return {
        "schema_version": "case-source-governance-companion-v1.0",
        "canonical_case_status": "approved",
        "case_ref": {"sha256": "a" * 64},
        "source_provenance": {"status": "traceable"},
        "research_ingestion_eligibility": "eligible_for_internal_research",
        "media_reuse_rights": "not_established",
        "case_approval_changed_media_reuse_rights": False,
        "legacy_source_rights_field_observation": {"present": False},
        "governance_policy_version": None,
        "governance_policy_ref": {
            "applicable": False,
            "path": None,
            "sha256": None,
        },
    }


def test_current_schema_companion_accepts_explicit_non_applicable_policy():
    validate_case_source_governance_companion_v1(
        fresh_companion(), expected_case_sha256="a" * 64
    )


def test_legacy_policy_cannot_be_marked_non_applicable():
    companion = fresh_companion()
    companion["legacy_source_rights_field_observation"]["present"] = True
    with pytest.raises(ValueError, match="cannot waive"):
        validate_case_source_governance_companion_v1(companion)


def test_historical_policy_companion_remains_compatible():
    companion = fresh_companion()
    companion["governance_policy_version"] = "V1.0"
    companion["governance_policy_ref"] = {
        "path": "historical-policy.json",
        "sha256": "b" * 64,
    }
    validate_case_source_governance_companion_v1(companion)
