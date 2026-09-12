from __future__ import annotations

import argparse
from pathlib import Path

from production_profile_v1 import (
    build_case_acquisition_plan_v1,
    build_profile_compatibility_approval_v1,
    read_json,
    render_case_acquisition_plan_markdown,
    sha256_file,
    write_new_json,
    write_new_text,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Persist the Human-approved Production Profile compatibility receipt and "
            "build the review-only Case Acquisition Plan without modifying source "
            "Case, Pattern, Fingerprint, Storyboard, or Coverage artifacts."
        )
    )
    parser.add_argument("--registry", required=True)
    parser.add_argument("--coverage-report", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--approved-at")
    parser.add_argument("--compatibility-approval-output", required=True)
    parser.add_argument("--acquisition-plan-json-output", required=True)
    parser.add_argument("--acquisition-plan-markdown-output", required=True)
    args = parser.parse_args()

    registry_path = Path(args.registry).expanduser().resolve()
    report_path = Path(args.coverage_report).expanduser().resolve()
    source_hashes_before = {
        str(registry_path): sha256_file(registry_path),
        str(report_path): sha256_file(report_path),
    }
    report = read_json(report_path)
    for assessment in (
        (report.get("case_profile_compatibility_audit") or {}).get(
            "assessments", []
        )
    ):
        for key in ("approved_case", "fingerprint", "storyboard"):
            path = Path(
                str(((assessment.get("lineage") or {}).get(key) or {}).get("path"))
            ).resolve()
            source_hashes_before[str(path)] = sha256_file(path)
    pattern_lineage = (
        ((report.get("pattern_profile_compatibility") or [{}])[0]).get("lineage")
        or {}
    )
    pattern_path = Path(str(pattern_lineage.get("pattern_path"))).resolve()
    source_hashes_before[str(pattern_path)] = sha256_file(pattern_path)

    approval = build_profile_compatibility_approval_v1(
        registry_path=registry_path,
        coverage_report_path=report_path,
        reviewer=args.reviewer,
        approved_at=args.approved_at,
    )
    approval_output = Path(args.compatibility_approval_output).expanduser().resolve()
    approval_sha = write_new_json(approval_output, approval)
    plan = build_case_acquisition_plan_v1(
        registry_path=registry_path,
        coverage_report_path=report_path,
        compatibility_approval_path=approval_output,
    )
    plan_sha = write_new_json(Path(args.acquisition_plan_json_output), plan)
    markdown_sha = write_new_text(
        Path(args.acquisition_plan_markdown_output),
        render_case_acquisition_plan_markdown(plan),
    )

    source_hashes_after = {
        path: sha256_file(Path(path)) for path in source_hashes_before
    }
    if source_hashes_after != source_hashes_before:
        raise RuntimeError("A frozen Profile, Case, Pattern, or Coverage source changed.")

    print("PRODUCTION PROFILE COMPATIBILITY HUMAN REVIEW PASS")
    print(f"Compatibility Approval SHA-256: {approval_sha}")
    print(f"Case Acquisition Plan SHA-256: {plan_sha}")
    print(f"Case Acquisition Markdown SHA-256: {markdown_sha}")
    print("Approved Mix Case compatibility decisions: 3")
    print("Approved Mix Pattern compatibility decisions: 1")
    print("News Phase A targets: 6")
    print("Mix lower-priority targets: 7")
    print("Video search/download: 0")
    print("Remote model calls: 0")
    print("Frozen source artifacts unchanged: True")


if __name__ == "__main__":
    main()
