"""The explicit final human action for NEW Case approvals; never a quality score.

Read paths accept historical approvals. All new approval writers require this
versioned decision, including the trusted offline CLI. Only the authenticated
owner supplies actor, time and execution identity, never the request body.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

VERSION = "case-human-quality-decision-v1.0"
APPROVAL_VERSION = "case-human-approval-v2.0"


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def quality_context(candidate: Path):
    case = json.loads(candidate.read_text(encoding="utf-8"))
    attempt = (case.get("analysis_lineage") or {}).get("attempt_id")
    if not case.get("case_id") or not attempt:
        raise ValueError("Case / Attempt identity is required for final human review")
    evidence = {key: file_sha(Path(raw)) for key, raw in (case.get("source_artifacts") or {}).items()
                if isinstance(raw, str) and raw.lower().endswith(".json")}
    if not {"storyboard_v1", "privacy_projection_v1"} <= evidence.keys():
        raise ValueError("Final human review requires source evidence")
    return {"schema_version": VERSION, "case_id": case["case_id"], "attempt_id": attempt,
            "candidate_sha256": file_sha(candidate), "evidence_sha256": evidence}


def validate_quality_decision(candidate: Path, decision):
    expected = {**quality_context(candidate), "decision": "suitable", "origin": "human_final_confirmation"}
    if decision != expected:
        raise ValueError("Explicit positive human quality decision must match the exact candidate and evidence")
    return expected


def validate_quality_record(case, receipt):
    """Additive version detection; historical approvals retain their old semantics."""
    approval = case.get("approval") or {}
    if not any((approval.get("contract_version"), receipt.get("contract_version"),
                approval.get("human_quality_decision"), receipt.get("human_quality_decision"))):
        return
    record = approval.get("human_quality_decision") or {}
    if (approval.get("contract_version") != APPROVAL_VERSION or receipt.get("contract_version") != APPROVAL_VERSION
            or receipt.get("human_quality_decision") != record or record.get("schema_version") != VERSION
            or record.get("decision") != "suitable" or record.get("origin") != "human_final_confirmation"
            or record.get("case_id") != case.get("case_id")
            or record.get("attempt_id") != (case.get("analysis_lineage") or {}).get("attempt_id")
            or record.get("candidate_sha256") != receipt.get("case_sha256_before_approval")
            or record.get("reviewer") != receipt.get("reviewer")
            or record.get("decided_at") != receipt.get("approved_at")
            or not record.get("actor") or not record.get("operation_id") or not record.get("evidence_sha256")):
        raise ValueError("Case human quality record is inconsistent with the Approval Receipt")
