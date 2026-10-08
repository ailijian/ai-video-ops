"""One native Node target covers every frontend behavior test, once."""
from pathlib import Path
import json
import os
import shutil
import subprocess


def test_all_javascript_regressions():
    node = shutil.which("node")
    assert node, "Node.js is required for Console verification."
    scripts = sorted((Path(__file__).parent / "js").glob("*.test.mjs"))
    assert scripts, "No JavaScript regression tests were discovered."
    result = subprocess.run(
        [node, "--test", "--test-concurrency=2", *(str(path) for path in scripts)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    artifact_root = os.environ.get("AIVO_VERIFICATION_ARTIFACTS")
    if artifact_root:
        artifact = Path(artifact_root)
        (artifact / "javascript.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        (artifact / "javascript.json").write_text(
            json.dumps({"files": [str(path) for path in scripts], "exit_code": result.returncode,
                        "node": node, "version": subprocess.check_output([node, "--version"], text=True).strip(),
                        "concurrency": 2}, indent=2) + "\n", encoding="utf-8",
        )
    assert result.returncode == 0, result.stdout + result.stderr
