"""Run the Console dependency probe shipped by the deployment Owner."""
import json
from pathlib import Path
import subprocess
import sys
import tomllib
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[2]


def probe_source():
    script = (ROOT / "deploy/local-node/powershell/runtime-preflight.ps1").read_text(encoding="utf-8")
    code = script.split("$consoleDependencyProbe = @'\n", 1)[1].split("\n'@", 1)[0]
    assert '@("-c", $consoleDependencyProbe)' in script
    assert script.index("$consoleDependencies = Invoke-CapturedNative") < script.index('$ollamaModels = Invoke-CapturedNative')
    return code


def test_production_probe_checks_current_console_runtime_dependencies():
    manifest = tomllib.loads((ROOT / "internal-console/pyproject.toml").read_text(encoding="utf-8"))
    assert "jsonschema>=4.23,<5" in manifest["project"]["dependencies"]
    result = subprocess.run([sys.executable, "-c", probe_source()], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert set(value["console_runtime_packages"]) == {"fastapi", "uvicorn", "jsonschema"}
    assert value["draft_2020_12"] == "PASS"


def test_production_probe_rejects_missing_jsonschema_even_when_metadata_exists():
    missing = """import sys
import importlib.abc
class MissingSchema(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'jsonschema' or fullname.startswith('jsonschema.'):
            raise ModuleNotFoundError('Isolated missing jsonschema', name='jsonschema')
sys.meta_path.insert(0, MissingSchema())
"""
    result = subprocess.run([sys.executable, "-c", missing + probe_source()], capture_output=True, text=True, timeout=20)
    assert result.returncode != 0
    assert "ModuleNotFoundError" in result.stderr and "jsonschema" in result.stderr
    assert '"draft_2020_12": "PASS"' not in result.stdout


def test_dependency_probe_uses_real_windows_powershell_native_arguments(tmp_path):
    powershell = shutil.which("powershell.exe")
    if powershell is None:
        pytest.skip("Windows PowerShell is unavailable on this host")
    source = (ROOT / "deploy/local-node/powershell/runtime-preflight.ps1").read_text(encoding="utf-8")
    function = source[source.index("function Invoke-CapturedNative {"):source.index("function Get-EnvFileSetting {")]
    probe = source[source.index("$consoleDependencyProbe = @'"):source.index('foreach ($package in @("faster-whisper"')]
    script = tmp_path / "native-dependency-probe.ps1"
    script.write_text(function + "\n$consolePython = '" + sys.executable.replace("'", "''") + "'\n" + probe, encoding="utf-8")
    result = subprocess.run([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"draft_2020_12": "PASS"' in result.stdout
