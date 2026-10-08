from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools import verify


class SelectionTests(unittest.TestCase):
    def test_shared_pipeline_code_includes_downstream_consumers(self):
        selected, fallback = verify.select(["ops-pipeline/scripts/content_quality_v1.py"])
        self.assertEqual(selected, dict.fromkeys(("pipeline", "console", "authority-release")))
        self.assertIsNone(fallback)

    def test_fixture_changes_include_consumers_and_helpers_do_not_narrow_scope(self):
        selected, _ = verify.select(["ops-pipeline/tests/test_a.py", "ops-pipeline/tests/fixtures/new.json"])
        self.assertIsNone(selected["pipeline"])
        self.assertIn("console", selected)
        self.assertIn("authority-release", selected)

    def test_only_test_changes_select_modules(self):
        selected, _ = verify.select(["internal-console/tests/test_security.py"])
        self.assertEqual(selected, {"console": ["tests/test_security.py"]})

    def test_console_fixture_and_verifier_tests_have_bounded_targets(self):
        self.assertEqual(verify.select(["internal-console/tests/conftest.py"])[0], {"console": None})
        self.assertEqual(verify.select(["tools/tests/test_verify.py"])[0], {"verification": None})

    def test_javascript_test_additions_use_discovering_bridge(self):
        selected, _ = verify.select(["internal-console/tests/js/new.test.mjs"])
        self.assertEqual(selected, {"console": ["tests/test_javascript.py"]})

    def test_deployment_and_runtime_consumers_are_included(self):
        self.assertEqual(set(verify.select(["deploy/local-node/powershell/path-compat.ps1"])[0]),
                         {"console", "authority-release"})
        self.assertEqual(verify.select(["deploy/frp-ip-guard/frp-ip-guard.ps1"])[0], {"frp-guard": None})

    def test_unknown_inputs_and_governance_fail_back_to_full(self):
        for path in ("new-package/file.py", "docs/product/contract.md", "AGENTS.md", "tools/verify.py"):
            with self.subTest(path=path):
                selected, reason = verify.select([path])
                self.assertEqual(set(selected), set(verify.TARGETS))
                self.assertTrue(reason)

    def test_empty_change_has_explicit_empty_scope(self):
        self.assertEqual(verify.select([]), ({}, None))

    def test_balanced_shards_cover_every_module_once(self):
        files = ["a", "b", "c", "d"]
        bins = verify.balanced_shards(files, 2, {"a": 10, "b": 8, "c": 2, "d": 1})
        flattened = [m for b in bins for m in b]
        self.assertCountEqual(flattened, files)
        self.assertEqual(len(flattened), len(set(flattened)))
        self.assertLessEqual(max(sum({"a": 10, "b": 8, "c": 2, "d": 1}[m] for m in b) for b in bins), 11)


class RepositoryStateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="aivo-verifier-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.git("init")
        self.write("original.py", "original")
        self.git("add", ".")
        self.git("-c", "user.email=test@example.invalid", "-c", "user.name=Test", "commit", "-m", "fixture")

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], stderr=subprocess.PIPE)

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def test_index_worktree_untracked_and_renames_are_all_selected(self):
        self.git("mv", "original.py", "renamed.py")
        self.write("renamed.py", "dirty")
        self.write("new.py", "untracked")
        _, paths = verify.changed_paths(self.root, "HEAD")
        self.assertEqual(paths, ["new.py", "original.py", "renamed.py"])

    def test_index_only_changes_are_not_lost_when_worktree_matches_base(self):
        self.write("original.py", "index-only")
        self.git("add", ".")
        self.write("original.py", "original")
        _, paths = verify.changed_paths(self.root, "HEAD")
        self.assertEqual(paths, ["original.py"])

    def test_snapshot_detects_untracked_content_changes(self):
        self.write("new.py", "before")
        before = verify.snapshot(self.root)
        self.write("new.py", "after")
        self.assertNotEqual(before["fingerprint"], verify.snapshot(self.root)["fingerprint"])

    def test_snapshot_detects_index_content_changes_with_unchanged_status(self):
        self.write("original.py", "index-one")
        self.git("add", ".")
        self.write("original.py", "working")
        before = verify.snapshot(self.root)
        self.write("original.py", "index-two")
        self.git("add", ".")
        self.write("original.py", "working")
        after = verify.snapshot(self.root)
        self.assertEqual(before["status"], after["status"])
        self.assertNotEqual(before["fingerprint"], after["fingerprint"])

    def test_deleted_test_falls_back_to_complete_remaining_target(self):
        self.write("internal-console/tests/test_remaining.py", "def test_ok(): pass")
        jobs = verify.make_jobs(self.root, {"console": ["tests/test_deleted.py"]}, 4, {})
        self.assertEqual([m for j in jobs for m in j.modules], ["tests/test_remaining.py"])

    def test_inventory_honors_native_testpaths_and_file_patterns(self):
        self.write("internal-console/pyproject.toml", '[tool.pytest.ini_options]\ntestpaths=["checks"]\npython_files=["check_*.py"]\n')
        self.write("internal-console/checks/check_custom.py", "def test_ok(): pass")
        self.write("internal-console/tests/test_old.py", "def test_wrong_scope(): pass")
        self.assertEqual(verify.test_modules(self.root, "console"), ["checks/check_custom.py"])

    def test_invalid_base_fails_closed(self):
        with self.assertRaises(subprocess.CalledProcessError):
            verify.changed_paths(self.root, "nonexistent")

    def test_cli_invalid_base_resolves_full_without_writing_artifacts(self):
        output = io.StringIO()
        with patch.object(verify, "ROOT", self.root), patch("sys.stdout", output):
            code = verify.main(["--mode", "affected", "--base", "nonexistent", "--list"])
        plan = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(plan["mode"], "full-fallback")
        self.assertEqual(set(plan["selection"]), set(verify.TARGETS))
        self.assertFalse((self.root / ".verify").exists())

    def test_repository_change_during_execution_invalidates_successful_tests(self):
        self.write(".gitignore", ".verify/\n")
        self.write("tools/tests/test_mutation.py",
                   "from pathlib import Path\nimport unittest\nclass TestMutation(unittest.TestCase):\n"
                   " def test_mutation(self): Path('original.py').write_text('changed during test')\n")
        with patch.object(verify, "ROOT", self.root), patch("sys.stdout", io.StringIO()):
            code = verify.main(["--target", "verification", "--jobs", "1"])
        reports = list((self.root / ".verify").glob("*/summary.json"))
        report = json.loads(reports[0].read_text(encoding="utf-8"))
        self.assertEqual(code, 1)
        self.assertFalse(report["state_unchanged"])
        self.assertEqual(report["results"][0]["status"], "passed")
        self.assertEqual(report["status"], "failed")


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="aivo-verifier-exec-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "tools/tests").mkdir(parents=True)
        self.run = self.root / "run"
        self.run.mkdir()

    def execute_test(self, source):
        (self.root / "tools/tests/test_child.py").write_text(source, encoding="utf-8")
        return verify.execute(self.root, self.run, verify.Job("verification", [], 0), 20)

    def test_real_child_failure_propagates_with_log(self):
        result = self.execute_test("import unittest\nclass TestFailure(unittest.TestCase):\n def test_failure(self): self.fail('sentinel failure')\n")
        self.assertEqual(result["status"], "failed")
        self.assertNotEqual(result["exit_code"], 0)
        self.assertIn("sentinel failure", Path(result["log"]).read_text(encoding="utf-8"))

    def test_empty_required_verifier_suite_cannot_pass(self):
        result = verify.execute(self.root, self.run, verify.Job("verification", [], 0), 20)
        self.assertEqual(result["status"], "failed")
        self.assertNotEqual(result["exit_code"], 0)

    def test_child_environment_is_isolated_from_production_and_pytest_overrides(self):
        with patch.dict(os.environ, {"AIVO_ENV_FILE": "production.env", "AIVO_LIVE_AUTHORITY_ROOT": "production",
                                     "PYTEST_ADDOPTS": "-k nothing", "PSMODULEPATH": "PowerShell7/modules"}):
            result = self.execute_test(
                "import os,unittest\nclass TestEnvironment(unittest.TestCase):\n"
                " def test_environment(self):\n"
                "  self.assertNotIn('AIVO_ENV_FILE',os.environ)\n"
                "  self.assertNotIn('AIVO_LIVE_AUTHORITY_ROOT',os.environ)\n"
                "  self.assertNotIn('PYTEST_ADDOPTS',os.environ)\n"
                "  self.assertNotIn('PSMODULEPATH',os.environ)\n"
                "  self.assertEqual(os.environ['AIVO_BACKGROUND_WORKER'],'0')\n"
            )
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["counts"]["tests"], 1)

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell environment regression")
    def test_native_powershell_security_module_loads_with_parent_core_path(self):
        powershell = shutil.which("powershell.exe")
        self.assertIsNotNone(powershell)
        with patch.dict(os.environ, {"PSMODULEPATH": "C:/nonexistent/PowerShell7/modules"}):
            result = subprocess.run(
                [powershell, "-NoProfile", "-NonInteractive", "-Command",
                 "Import-Module Microsoft.PowerShell.Security -ErrorAction Stop; Get-Command Set-Acl | Select-Object -ExpandProperty Name"],
                env=verify.child_environment(self.run), capture_output=True, timeout=20,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"Set-Acl", result.stdout)

    def test_junit_records_skips_failures_and_module_timings(self):
        xml = self.run / "results.xml"
        xml.write_text('<testsuites><testsuite><testcase classname="tests.test_a" name="ok" time="2"/>'
                       '<testcase classname="tests.test_a" name="bad" time="1"><failure/></testcase>'
                       '<testcase classname="tests.test_b" name="platform" time="0"><skipped message="Windows unavailable"/>'
                       '</testcase></testsuite></testsuites>', encoding="utf-8")
        counts, timings = verify.junit_result(xml, "console", ["tests/test_a.py", "tests/test_b.py"])
        self.assertEqual((counts["passed"], counts["failures"], counts["skipped"]), (1, 1, 1))
        self.assertEqual(counts["skip_reasons"][0]["reason"], "Windows unavailable")
        self.assertEqual(timings["console:tests/test_a.py"], 3)

    @unittest.skipUnless(shutil.which("node"), "Node is required for the frontend bridge regression")
    def test_bridge_discovers_new_javascript_test_and_propagates_failure(self):
        path = verify.ROOT / "internal-console/tests/test_javascript.py"
        spec = importlib.util.spec_from_file_location("frontend_bridge", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        tests = self.root / "tests"
        (tests / "js").mkdir(parents=True)
        (tests / "js/new.test.mjs").write_text("import assert from 'node:assert/strict'; assert.fail('new file executed');", encoding="utf-8")
        module.__file__ = str(tests / "test_javascript.py")
        with self.assertRaisesRegex(AssertionError, "new file executed"):
            module.test_all_javascript_regressions()


if __name__ == "__main__":
    unittest.main()
