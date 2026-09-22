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
        else:
            result = install_release(args.release, args.pipeline_root, args.repo_root, args.expected_commit, args.backup_parent, args.receipt)
    except AuthorityReleaseError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "message": str(exc), "audit": exc.details}, ensure_ascii=False))
        raise SystemExit(2) from exc
    print(json.dumps({"ok": True, **result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
