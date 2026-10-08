# Repository verification

Run from the repository root with Python 3.12+. Install the two existing test
environments: `ops-pipeline/requirements-dev.txt` in the Pipeline venv and
`internal-console[dev]` in the Console venv. Console verification also requires
Node.js (the current host uses Node 24); complete deployment regression requires
Windows PowerShell 5.1 and Git. The runner never installs dependencies.

```powershell
# Complete isolated regression, with bounded parallel execution.
python tools/verify.py

# Resolve all changes since an explicit base, including staged/unstaged/untracked.
python tools/verify.py --mode affected --base HEAD

# Inspect selection without running tests or writing reports.
python tools/verify.py --mode affected --base HEAD --list

# Explicit package feedback; this is reported as targeted verification.
python tools/verify.py --target console

# Serial reference execution for diagnosis or performance comparison.
python tools/verify.py --jobs 1
```

## Scope and selection

Full regression covers Pipeline's default hermetic suite, Console (including
every `tests/js/*.test.mjs` file and the Windows compatibility smoke), Shared
Creative Authority release tests, FRP Guard offline tests, and verifier tests.
Live Authority smoke remains a separate explicit, read-only operation described
in [Pipeline test layers](../ops-pipeline/tests/README.md); full regression does
not imply live production validation or model/provider execution.

The consumer map is implemented in [verify.py](verify.py), with regression
checks in [test_verify.py](tests/test_verify.py):

| Changed input | Required targets |
|---|---|
| Pipeline scripts, dependencies, shared helpers or fixtures | Pipeline, Console, Authority release |
| Console app, static assets, migrations, scripts, dependencies or shared test helpers | Console |
| Local Node deployment | Console including PowerShell smoke, Authority release |
| Authority release implementation | Authority release, Console deployment checks |
| FRP Guard | FRP Guard |
| One Python test module | That module; deletion runs the remaining complete target |
| JS test file | The discovering Console JS bridge |
| Verifier tests | Verifier |
| Verifier implementation, governance, unknown input, missing/invalid base | Full fallback |

Rename selection includes old and new paths. Unknown untracked inputs also
trigger full fallback, so an unrelated experiment may conservatively widen
verification. The runner does not claim a source import graph or silently omit
downstream consumers. Inspect `--list` when scope is unexpected.

## Efficiency and isolation

The default process limit is half the logical CPUs, capped at six. Console is
split into balanced module shards; fast targets retain one process to avoid
repeating imports. `--jobs` controls the total process budget. Node uses at most
two file workers within the single JS bridge. Increase the budget only after
comparing actual runs on the intended host.

Observed module durations in `.verify/timings.json` improve later balancing.
These hints never select, skip or reuse tests. Every selected check executes;
there is no test-result cache, remote cache or automatic retry. Failed targets
do not suppress other targets or produce a successful full result.

Each process receives a unique, short temporary root, pytest cache and import
database. Production `AIVO_*` settings, `PYTEST_ADDOPTS`, plugin injection and
`PYTHONPATH` are not inherited. PowerShell module paths are rebuilt by the native
host, preventing PowerShell 7 modules from contaminating Windows PowerShell 5.1.
Third-party pytest plugin autoload is disabled;
required plugins must be explicitly declared in package test configuration.
The synthetic fixture and mutable SQLite/Authority copies remain isolated.
Crypto checks, Human Gates and locking assertions are preserved.

## Evidence and checkpoints

Each execution prints its `.verify/<run>/summary.json` path. The report records
Git HEAD and dirty/index/untracked fingerprints, selection and fallback reason,
executed modules and commands, platform, Python/package versions, results,
skips, durations and per-process logs/JUnit files. Console's JS bridge also
records the actual JS file list and native Node output. Source changes during
execution invalidate the overall result.

Missing required runtimes, empty required suites, timeouts, missing result
evidence or failing children produce failure. A missing Windows runtime cannot
produce a complete passing regression. Targeted/affected results retain their
mode and are never labelled full. Full excludes the documented live layer.

Use full regression for changes to this runner/selection map, shared contracts,
broad integration checkpoints and final delivery validation when required by
the task. Use affected verification for ordinary changes with a reliable base;
full fallback is automatic when classification is uncertain. Any future CI
should invoke this same entry point and retain its report and logs.
