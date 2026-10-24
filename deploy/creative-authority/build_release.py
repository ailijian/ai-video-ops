from __future__ import annotations

import argparse
import json
from pathlib import Path

from authority_release import build_release


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a shared Creative Authority release from canonical development data")
    parser.add_argument("--pipeline-root", type=Path, required=True)
    parser.add_argument("--release-parent", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument('--contract-version', choices=['1.0', '1.1'], default='1.0')
    parser.add_argument('--purpose', choices=['isolated-validation', 'production'])
    parser.add_argument('--parent-release-ref', type=Path)
    args = parser.parse_args()
    parent = json.loads(args.parent_release_ref.read_text('utf-8')) if args.parent_release_ref else None
    if args.contract_version == '1.1' and not args.purpose:
        parser.error('Version 1.1 requires an explicit purpose')
    release = build_release(args.pipeline_root, args.release_parent, args.repo_root,
        contract_version=args.contract_version, purpose=args.purpose, parent_release=parent)
    print(json.dumps({"release": str(release)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
