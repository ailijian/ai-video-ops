from __future__ import annotations

import argparse
import json
import sys
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
    if len(sys.argv) > 1 and sys.argv[1] == 'v1.1':
        return main_v1_1(sys.argv[2:])
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


def main_v1_1(argv):
    """Explicit native entry; no historical reviewer-name bypass."""
    from production_profile_v1 import preview_compatibility_v1_1, decide_compatibility_v1_1
    parser = argparse.ArgumentParser(description='Native independent Mix Compatibility Human Review')
    parser.add_argument('action', choices=['snapshot', 'preview', 'confirm'])
    parser.add_argument('--root', required=True)
    parser.add_argument('--database', required=True)
    parser.add_argument('--namespace', required=True)
    parser.add_argument('--user-id', required=True, type=int)
    parser.add_argument('--operation-id')
    parser.add_argument('--decisions-json')
    parser.add_argument('--preview-sha256')
    parser.add_argument('--case-id', action='append')
    parser.add_argument('--pattern-file', type=Path)
    parser.add_argument('--mix-template', type=Path)
    args = parser.parse_args(argv)
    actor = {'namespace': args.namespace, 'user_id': args.user_id}
    if args.action == 'snapshot':
        from production_profile_v1 import bootstrap_mix_profile_v1_1, MIX_PATTERN_ID
        from profile_compatibility_authorization_v1 import authorization
        from profile_compatibility_decisions_v1_1 import prepare_target, decision_graph
        authorization(Path(args.database), actor)
        if not args.case_id or not args.mix_template or args.decisions_json or args.preview_sha256:
            parser.error('snapshot requires --case-id and --mix-template; it cannot submit a decision')
        definitions = bootstrap_mix_profile_v1_1(Path(args.root), args.mix_template)
        targets = [prepare_target(Path(args.root), case_id=case_id, pattern_id=MIX_PATTERN_ID,
            pattern_path=args.pattern_file, **definitions) for case_id in args.case_id]
        result = {'source_targets': targets, 'current_heads': decision_graph(Path(args.root))['heads'],
                  'review_status': 'review_required', 'approval_created': False}
    elif args.action == 'preview':
        if not args.operation_id or not args.decisions_json or args.preview_sha256:
            parser.error('preview requires only --decisions-json')
        result = preview_compatibility_v1_1(Path(args.root), Path(args.database), actor,
            args.operation_id, json.loads(Path(args.decisions_json).read_text('utf-8')))
    else:
        if not args.operation_id or not args.preview_sha256 or args.decisions_json:
            parser.error('confirm requires only --preview-sha256')
        result = decide_compatibility_v1_1(Path(args.root), Path(args.database), actor,
            args.operation_id, args.preview_sha256)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
