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
    args = parser.parse_args()
    release = build_release(args.pipeline_root, args.release_parent, args.repo_root)
    print(json.dumps({"release": str(release)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
