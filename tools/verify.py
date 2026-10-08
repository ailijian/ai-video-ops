"""Repository-native verification: conservative selection, isolated parallel jobs.

Only timing hints are reused. Test results are always executed afresh.
"""
from __future__ import annotations

import argparse
import ast
import configparser
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
import tomllib
import uuid
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
TARGETS = ("pipeline", "console", "authority-release", "frp-guard", "verification")
PYTEST_ROOTS = {
    "pipeline": "ops-pipeline",
    "console": "internal-console",
    "authority-release": "deploy/creative-authority",
}


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE)


def changed_paths(root: Path, base: str) -> tuple[str, list[str]]:
    commit = git(root, "rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}").decode().strip()
    # Disabling rename detection includes both deleted and added paths.
    paths = git(root, "diff", "--no-ext-diff", "--no-textconv", "--name-only", "-z", "--no-renames", commit, "--")
    paths += git(root, "diff", "--cached", "--no-ext-diff", "--no-textconv", "--name-only", "-z", "--no-renames", commit, "--")
    paths += git(root, "ls-files", "--others", "--exclude-standard", "-z")
    return commit, sorted(set(p.decode("utf-8") for p in paths.split(b"\0") if p))


def snapshot(root: Path) -> dict:
    head = git(root, "rev-parse", "HEAD").decode().strip()
    status = git(root, "status", "--porcelain=v1", "-z")
    digest = hashlib.sha256(head.encode() + status + git(root, "diff", "--no-ext-diff", "--no-textconv", "--binary", "HEAD", "--")
                            + git(root, "diff", "--cached", "--no-ext-diff", "--no-textconv", "--binary", "HEAD", "--"))
    untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z")
    for name in sorted(filter(None, untracked.split(b"\0"))):
        path = root / name.decode("utf-8")
        digest.update(name)
        if path.is_file():
            digest.update(path.read_bytes())
    return {"head": head, "status": status.decode("utf-8"), "fingerprint": digest.hexdigest()}


def full_selection() -> dict[str, list[str] | None]:
    return dict.fromkeys(TARGETS)


def select(paths: list[str]) -> tuple[dict[str, list[str] | None], str | None]:
    """Explicit consumer map; unknown inputs conservatively select all targets.

    Test-only edits select their module. Production/shared inputs select complete
    consumer suites, including consumers outside the changed directory.
    """
    selected: dict[str, list[str] | None] = {}

    def add(target: str, module: str | None = None) -> None:
        if module is None:
            selected[target] = None
        elif target not in selected:
            selected[target] = [module]
        elif selected[target] is not None:
            selected[target] = sorted(set(selected[target] + [module]))

    for path in paths:
        if path.startswith("ops-pipeline/tests/") and Path(path).name.startswith("test_") and path.endswith(".py"):
            add("pipeline", path.removeprefix("ops-pipeline/"))
        elif path.startswith("internal-console/tests/js/") and path.endswith(".test.mjs"):
            add("console", "tests/test_javascript.py")
        elif path.startswith("internal-console/tests/") and Path(path).name.startswith("test_") and path.endswith(".py"):
            add("console", path.removeprefix("internal-console/"))
        elif path.startswith("internal-console/tests/"):
            add("console")
        elif path.startswith("deploy/creative-authority/tests/") and Path(path).name.startswith("test_") and path.endswith(".py"):
            add("authority-release", path.removeprefix("deploy/creative-authority/"))
        elif path.startswith(("ops-pipeline/tests/", "ops-pipeline/scripts/")) or path in {
            "ops-pipeline/pytest.ini", "ops-pipeline/requirements.txt", "ops-pipeline/requirements-dev.txt",
        }:
            for target in ("pipeline", "console", "authority-release"):
                add(target)
        elif path.startswith(("internal-console/app/", "internal-console/static/", "internal-console/migrations/", "internal-console/scripts/")) or path == "internal-console/pyproject.toml":
            add("console")
        elif path.startswith("deploy/creative-authority/"):
            add("authority-release")
            add("console")  # Runtime preflight and deployment-contract checks.
        elif path.startswith("deploy/local-node/"):
            add("console")  # Includes Windows PowerShell 5.1 smoke.
            add("authority-release")
        elif path.startswith("deploy/frp-ip-guard/"):
            add("frp-guard")
        elif path.startswith("tools/tests/"):
            add("verification")
        elif path.startswith("tools/") or path in {".gitignore", "AGENTS.md"}:
            return full_selection(), f"verification/global input: {path}"
        else:
            return full_selection(), f"unclassified input: {path}"
    return selected, None


def test_modules(root: Path, target: str) -> list[str]:
    package = (root / PYTEST_ROOTS[target]).resolve()
    options = {}
    if (package / "pytest.ini").is_file():
        config = configparser.ConfigParser()
        config.read(package / "pytest.ini", encoding="utf-8")
        options = dict(config["pytest"])
    elif (package / "pyproject.toml").is_file():
        options = tomllib.loads((package / "pyproject.toml").read_text(encoding="utf-8"))\
            .get("tool", {}).get("pytest", {}).get("ini_options", {})
    def values(key, default):
        value = options.get(key, default)
        values = value.split() if isinstance(value, str) else value
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise ValueError(f"Invalid pytest {key} for {target}")
        return values
    directories = values("testpaths", ["tests"])
    patterns = values("python_files", ["test_*.py", "*_test.py"])
    found = set()
    for directory in directories:
        path = (package / directory).resolve()
        if not path.is_relative_to(package.resolve()):
            raise ValueError(f"Test path escapes {target}: {directory}")
        for pattern in patterns:
            candidates = [path] if path.is_file() and path.match(pattern) else path.rglob(pattern)
            found.update(p.relative_to(package).as_posix() for p in candidates if p.is_file())
    return sorted(found)


def estimate(root: Path, target: str, module: str, timings: dict) -> float:
    recorded = timings.get(f"{target}:{module}")
    if isinstance(recorded, (float, int)) and 0 < recorded < 3600:
        return float(recorded)
    tree = ast.parse((root / PYTEST_ROOTS[target] / module).read_text(encoding="utf-8-sig"))
    return max(1, sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and
                      n.name.startswith("test_") for n in ast.walk(tree))) * 0.3


def balanced_shards(modules: list[str], count: int, weights: dict[str, float]) -> list[list[str]]:
    bins: list[list[str]] = [[] for _ in range(min(count, len(modules)))]
    loads = [0.0] * len(bins)
    for module in sorted(modules, key=lambda m: (-weights[m], m)):
        index = min(range(len(bins)), key=lambda i: (loads[i], i))
        bins[index].append(module)
        loads[index] += weights[module]
    return [sorted(b) for b in bins]


@dataclass
class Job:
    target: str
    modules: list[str]
    index: int


def make_jobs(root: Path, selection: dict, jobs: int, timings: dict) -> list[Job]:
    result = []
    for target in TARGETS:
        if target not in selection:
            continue
        if target not in PYTEST_ROOTS:
            result.append(Job(target, [], len(result)))
            continue
        modules = selection[target]
        if modules is not None and any(not (root / PYTEST_ROOTS[target] / m).is_file() for m in modules):
            modules = None  # Deleted tests require remaining consumer regression.
        modules = test_modules(root, target) if modules is None else modules
        if not modules:
            raise ValueError(f"No tests discovered for required target {target}")
        # The measured slow suite is Console. Keep the fast Pipeline together to
        # avoid repeating its expensive imports and collection in many processes.
        count = max(1, jobs - int(len(selection) > 1)) if target == "console" else 1
        weights = {m: estimate(root, target, m, timings) for m in modules}
        for shard in balanced_shards(modules, count, weights):
            result.append(Job(target, shard, len(result)))
    return result


def child_environment(work: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("AIVO_") and
           k.upper() not in {"PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTHONPATH", "PSMODULEPATH"}}
    env.update({
        "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "AIVO_CONSOLE_DB": str(work / "import.sqlite3"),
        "AIVO_CASE_ANALYSIS_WORKER": "0", "AIVO_CUSTOMER_ANALYSIS_WORKER": "0",
        "AIVO_SPEAKER_ANALYSIS_WORKER": "0", "AIVO_BACKGROUND_WORKER": "0",
        "AIVO_VERIFICATION_ARTIFACTS": str(work),
    })
    return env


def terminate_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait()


def junit_result(path: Path, target: str, modules: list[str]) -> tuple[dict, dict]:
    xml = ET.parse(path)
    cases = list(xml.iter("testcase"))
    counts = {"tests": len(cases), "failures": 0, "errors": 0, "skipped": 0, "skip_reasons": []}
    durations = {f"{target}:{m}": 0.0 for m in modules}
    for case in cases:
        for tag, key in (("failure", "failures"), ("error", "errors"), ("skipped", "skipped")):
            counts[key] += int(case.find(tag) is not None)
        skipped = case.find("skipped")
        if skipped is not None:
            counts["skip_reasons"].append({"test": case.get("name"), "reason": skipped.get("message")})
        classname = case.get("classname", "")
        for module in modules:
            prefix = module.removesuffix(".py").replace("/", ".")
            if classname == prefix or classname.startswith(prefix + "."):
                durations[f"{target}:{module}"] += float(case.get("time", "0"))
                break
    counts["passed"] = counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"]
    return counts, durations


def python_toolchain(python: Path, env: dict) -> dict:
    code = ("import importlib.metadata as m,json,platform; "
            "print(json.dumps({'python':platform.python_version(),"
            "'packages':{d.metadata['Name']:d.version for d in m.distributions()}}))")
    return json.loads(subprocess.check_output([str(python), "-c", code], env=env, text=True, encoding="utf-8", timeout=20))


def execute(root: Path, run: Path, job: Job, timeout: int) -> dict:
    work = run / str(job.index)
    work.mkdir()
    log = run / f"{job.index}-{job.target}.log"
    junit = run / f"{job.index}-{job.target}.xml"
    cwd = root
    counts, durations = {}, {}
    toolchain = {}
    if job.target in PYTEST_ROOTS:
        owner = "internal-console" if job.target == "console" else "ops-pipeline"
        python = root / owner / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not python.is_file():
            return {"target": job.target, "status": "failed", "error": f"Missing {python}; install declared test dependencies."}
        cwd = root / PYTEST_ROOTS[job.target]
        toolchain = python_toolchain(python, child_environment(work))
        command = [str(python), "-m", "pytest", *job.modules, "--basetemp", str(work / "t"),
                   "--junitxml", str(junit), "-o", f"cache_dir={work / 'cache'}", "--durations=10", "-ra"]
    elif job.target == "frp-guard":
        powershell = shutil.which("powershell.exe")
        if not powershell:
            return {"target": job.target, "status": "failed", "error": "Windows PowerShell 5.1 is required for full FRP verification."}
        version = subprocess.check_output(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", "$PSVersionTable.PSVersion.ToString()"],
            env=child_environment(work), text=True, encoding="utf-8", timeout=20,
        ).strip()
        toolchain = {"powershell": powershell, "version": version}
        command = [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                   "-File", str(root / "deploy/frp-ip-guard/tests.ps1")]
    else:
        command = [sys.executable, "-m", "unittest", "discover", "-s", "tools/tests", "-v"]
    started = time.perf_counter()
    error = None
    with log.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(command, cwd=cwd, env=child_environment(work), stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=os.name != "nt",
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            terminate_tree(process)
            code, error = 124, f"Exceeded {timeout}s timeout"
        except BaseException:
            terminate_tree(process)
            raise
    output = log.read_text(encoding="utf-8", errors="replace")
    if job.target in PYTEST_ROOTS:
        try:
            counts, durations = junit_result(junit, job.target, job.modules)
            if not counts["tests"] or counts["errors"] or counts["failures"]:
                code = code or 1
        except (OSError, ET.ParseError) as exc:
            code, error = code or 1, f"Missing/invalid JUnit evidence: {exc}"
    elif job.target == "frp-guard":
        match = re.search(r"FRP_GUARD_TESTS_PASS: (\d+);", output)
        if not match or not int(match[1]):
            code, error = code or 1, "Missing FRP completion evidence"
        else:
            counts = {"tests": int(match[1]), "passed": int(match[1]), "skipped": 0}
    else:
        match = re.search(r"Ran (\d+) tests?", output)
        if not match or not int(match[1]):
            code, error = code or 1, "Missing verifier test completion evidence"
        else:
            skipped = re.search(r"skipped=(\d+)", output)
            skip_count = int(skipped[1]) if skipped else 0
            counts = {"tests": int(match[1]), "passed": int(match[1]) - skip_count if code == 0 else None,
                      "skipped": skip_count}
    return {"target": job.target, "modules": job.modules, "command": command, "cwd": str(cwd), "toolchain": toolchain,
            "status": "passed" if code == 0 else "failed", "exit_code": code, "counts": counts,
            "seconds": round(time.perf_counter() - started, 3), "log": str(log),
            "junit": str(junit) if junit.is_file() else None, "error": error, "timings": durations,
            "nested_artifacts": {name: str(work / name) for name in ("javascript.json", "javascript.log")
                                 if job.target == "console" and (work / name).is_file()}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("full", "affected"), default="full")
    parser.add_argument("--base", help="Explicit Git base for affected mode; includes index, working tree and untracked files")
    parser.add_argument("--jobs", type=int, default=min(6, max(1, (os.cpu_count() or 2) // 2)))
    parser.add_argument("--target", action="append", choices=TARGETS, help="Explicit target execution; reported as targeted, not full")
    parser.add_argument("--list", action="store_true", help="Print resolved scope without executing or writing artifacts")
    parser.add_argument("--timeout", type=int, default=600, help="Per-process timeout in seconds")
    args = parser.parse_args(argv)
    if args.jobs < 1 or args.timeout < 1:
        parser.error("--jobs and --timeout must be positive")
    state = snapshot(ROOT)
    base, paths, fallback = None, [], None
    mode = "targeted" if args.target else args.mode
    if args.target:
        selection = dict.fromkeys(args.target)
    elif args.mode == "affected":
        try:
            if not args.base:
                raise ValueError("affected mode requires an explicit --base")
            base, paths = changed_paths(ROOT, args.base)
            selection, fallback = select(paths)
        except (ValueError, subprocess.CalledProcessError, UnicodeError) as exc:
            selection, fallback = full_selection(), str(exc)
        if fallback:
            mode = "full-fallback"
    else:
        selection = full_selection()
    plan = {"requested_mode": args.mode, "mode": mode, "base": base, "changed_paths": paths,
            "selection": selection, "fallback_reason": fallback, "repository": str(ROOT), "state": state,
            "jobs": args.jobs, "excluded": {"live-authority": "opt-in read-only smoke; see ops-pipeline/tests/README.md"}}
    if args.list:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    timings_path = ROOT / ".verify/timings.json"
    try:
        timings = json.loads(timings_path.read_text(encoding="utf-8"))
        if not isinstance(timings, dict):
            timings = {}
    except (OSError, ValueError):
        timings = {}
    started = time.perf_counter()
    run = ROOT / ".verify" / uuid.uuid4().hex[:8]
    run.mkdir(parents=True)
    print(f"{mode}: {', '.join(selection) or 'no affected targets'}; jobs={args.jobs}", flush=True)
    results = []
    try:
        work = make_jobs(ROOT, selection, args.jobs, timings)
    except (OSError, ValueError, SyntaxError, configparser.Error) as exc:
        work = []
        results.append({"target": "planning", "status": "failed", "error": str(exc)})
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(execute, ROOT, run, job, args.timeout): job for job in work}
        for future in as_completed(futures):
            job = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {"target": job.target, "status": "failed", "error": str(exc)}
            results.append(result)
            print(f"{result['status']}: {job.target} ({result.get('seconds', 0):.2f}s) {result.get('error') or ''}", flush=True)
    final = snapshot(ROOT)
    passed = all(r["status"] == "passed" for r in results) and final == state
    report = {**plan, "status": "passed" if passed else "failed", "results": results,
              "state_unchanged": final == state, "final_state": final, "seconds": round(time.perf_counter() - started, 3),
              "environment": {"platform": platform.platform(), "coordinator_python": sys.version,
                              "plugin_autoload": False, "production_environment_inherited": False},
              "result_cache": "disabled; every selected check executes"}
    report_path = run / "summary.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Scheduling hints cannot skip work; only publish after a successful, stable run.
    if passed:
        for result in results:
            timings.update({key: max(0.01, value) for key, value in result.get("timings", {}).items()})
        temporary = run / "timings.json"
        temporary.write_text(json.dumps(timings, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, timings_path)
    print(f"{report['status']}: {report['seconds']:.2f}s; evidence={report_path}", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
