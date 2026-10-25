from __future__ import annotations

import argparse
import json
from pathlib import Path

from authority_release import (
    AuthorityReleaseError,
    audit_merge,
    install_release,
    plan_merge,
    preflight,
    verify_release,
    stage_release_v1_1,
    activate_release_v1_1,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only verification or guarded installation of a Creative Authority release")
    sub = parser.add_subparsers(dest="operation", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--release", type=Path, required=True)
    verify.add_argument("--repo-root", type=Path, required=True)
    check = sub.add_parser("preflight")
    check.add_argument("--pipeline-root", type=Path, required=True)
    check.add_argument("--repo-root", type=Path, required=True)
    check.add_argument("--receipt", type=Path)
    plan = sub.add_parser("plan")
    plan.add_argument("--release", type=Path, required=True)
    plan.add_argument("--pipeline-root", type=Path, required=True)
    plan.add_argument("--repo-root", type=Path, required=True)
    audit = sub.add_parser("audit")
    audit.add_argument("--release", type=Path, required=True)
    audit.add_argument("--pipeline-root", type=Path, required=True)
    audit.add_argument("--repo-root", type=Path, required=True)
    install = sub.add_parser("install")
    install.add_argument("--release", type=Path, required=True)
    install.add_argument("--pipeline-root", type=Path, required=True)
    install.add_argument("--repo-root", type=Path, required=True)
    install.add_argument("--expected-commit", required=True)
    install.add_argument("--backup-parent", type=Path, required=True)
    install.add_argument("--receipt", type=Path, required=True)
    stage = sub.add_parser('stage-v1.1')
    stage.add_argument('--release', type=Path, required=True)
    stage.add_argument('--pipeline-root', type=Path, required=True)
    stage.add_argument('--repo-root', type=Path, required=True)
    activate = sub.add_parser('activate-v1.1')
    activate.add_argument('--release-ref', type=Path, required=True)
    activate.add_argument('--pipeline-root', type=Path, required=True)
    activate.add_argument('--repo-root', type=Path, required=True)
    activate.add_argument('--operation-id', required=True)
    configure=sub.add_parser('configure-v1.3')
    configure.add_argument('--pipeline-root',type=Path,required=True)
    configure.add_argument('--control-root',type=Path,required=True)
    configure.add_argument('--repo-root',type=Path,required=True)
    configure.add_argument('--profiles',nargs='+',choices=['mix','news'],required=True)
    args = parser.parse_args()
    try:
        if args.operation == "verify":
            result = verify_release(args.release, args.repo_root)
        elif args.operation == "preflight":
            result = preflight(args.pipeline_root, args.repo_root, args.receipt)
        elif args.operation == "audit":
            result = audit_merge(args.release, args.pipeline_root, args.repo_root)
        elif args.operation == "plan":
            result = plan_merge(args.release, args.pipeline_root, args.repo_root)
        elif args.operation == 'stage-v1.1':
            result = {'release_ref': stage_release_v1_1(args.release, args.pipeline_root, args.repo_root)}
        elif args.operation == 'activate-v1.1':
            result = activate_release_v1_1(args.pipeline_root, args.repo_root,
                json.loads(args.release_ref.read_text('utf-8')), args.operation_id)
        elif args.operation == 'configure-v1.3':
            import sys
            sys.path.insert(0,str(args.repo_root/'ops-pipeline/scripts'))
            from profile_compatibility_release_v1_1 import configure_runtime
            result={'configuration':configure_runtime(args.pipeline_root,args.control_root,
                purpose='production',contract_version='1.3',profiles=args.profiles)}
        else:
            result = install_release(args.release, args.pipeline_root, args.repo_root, args.expected_commit, args.backup_parent, args.receipt)
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "code": getattr(exc, 'code', 'AUTHORITY_RELEASE_BLOCKED'), "message": str(exc), "audit": getattr(exc, 'details', None)}, ensure_ascii=False))
        raise SystemExit(2) from exc
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
