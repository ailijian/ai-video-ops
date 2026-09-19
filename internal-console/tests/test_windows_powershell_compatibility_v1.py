from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_runtime_scripts_support_windows_powershell_5_1():
    powershell = shutil.which("powershell.exe")
    if powershell is None:
        pytest.skip("Windows PowerShell is unavailable on this host.")

    repo_root = Path(__file__).resolve().parents[2]
    smoke = (
        repo_root
        / "deploy"
        / "local-node"
        / "tests"
        / "windows-powershell-5.1-smoke.ps1"
    )
    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(smoke),
            "-RepoRoot",
            str(repo_root),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "PASS: bootstrap/runtime-preflight path compatibility" in result.stdout
