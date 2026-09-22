# Shared Creative Authority deployment

This release moves **company-wide structural production authority**, not customer
runtime state. It contains approved Case JSON, Case approval receipts and
Fingerprints; approved Pattern JSON and receipts; Human-approved compatibility;
the Production Profile Registry; Creative Coverage Report; and SHA-pinned
structural companions. It never copies customer intakes, Personas, ledgers,
requests, tasks, exports, media, credentials, or raw downloads. Recorded source
paths in immutable artifacts remain provenance; the installer does not rewrite
them or re-run any Human approval.

The old development node is the only approved source:
`E:\projects\ai-video-ops\ops-pipeline\data`. Do not build from test fixtures.

## Build and validate on the development node

Before the build, record `git rev-parse HEAD`, `git status --short`, and the
actual approved Case/Fingerprint/Pattern counts. Dirty tracked Speaker work is
not included because the release reads only canonical `ops-pipeline/data`.

```powershell
& E:\projects\ai-video-ops\ops-pipeline\.venv\Scripts\python.exe `
  E:\projects\ai-video-ops\deploy\creative-authority\build_release.py `
  --pipeline-root E:\projects\ai-video-ops\ops-pipeline `
  --repo-root E:\projects\ai-video-ops `
  --release-parent E:\AI-Video-Ops-Authority

& E:\projects\ai-video-ops\ops-pipeline\.venv\Scripts\python.exe `
  E:\projects\ai-video-ops\deploy\creative-authority\verify_release.py verify `
  --release <exact-release-directory> `
  --repo-root E:\projects\ai-video-ops
```

Transfer the whole release directory, including `bundle`, `manifest.json`, and
`RELEASE_NOTES.md`. Do not transfer the development working tree or the entire
`ops-pipeline/data` tree. Verify the transferred release on the 4090 host before
installation.

## 4090 maintenance window

1. In the current Console task list, confirm no queued/running mutating tasks.
   If any exist, stop and let them finish; do not kill a task or edit SQLite.
2. Record `git rev-parse HEAD`, `git status --short`, and inspect the actual
   port-8000 process command line with `Get-NetTCPConnection` and
   `Get-CimInstance Win32_Process`. Confirm its executable/command path is from
   `E:\projects\ai-video-ops`. Never start a second listener.
3. Upgrade **code first** on the existing checkout: fetch the approved commit
   from `origin/main` or the approved Codeup mirror, then `git merge --ff-only`.
   If neither is reachable, use an exact-commit Git bundle from the development
   node: `git fetch <code-bundle-path> main`, then `git merge --ff-only FETCH_HEAD`.
   Stop on a dirty tracked tree or non-fast-forward; never copy the development
   working tree. Confirm `git rev-parse HEAD` is the approved deployment commit.
4. Stop the existing Console with its actual service controller. Confirm port
   8000 has no listener. A new checkout cannot pass hardened runtime preflight
   until the missing Authority is installed, so do not start it in between.
5. Verify the transferred release and inspect the read-only merge plan:

```powershell
$repo = 'E:\projects\ai-video-ops'
$release = '<transferred-release-directory>'
$python = Join-Path $repo 'ops-pipeline\.venv\Scripts\python.exe'
$tool = Join-Path $repo 'deploy\creative-authority\verify_release.py'
& $python $tool verify --release $release --repo-root $repo
& $python $tool plan --release $release --pipeline-root (Join-Path $repo 'ops-pipeline') --repo-root $repo
```

6. If the plan reports any collision, stop. Case, Fingerprint, Pattern, and
   singleton SHA differences require Human Authority review. The installer
   never selects the newer file or overwrites a Production Case. Existing new
   Production Cases remain in place; the release does not grant them Mix/News
   compatibility.
7. Install only with an idle queue and stopped service:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File E:\projects\ai-video-ops\deploy\local-node\powershell\install-creative-authority-release.ps1 `
  -ReleasePath $release -RepoRoot $repo -ExpectedCommit '<approved-deployment-commit>'
```

The installer stages and hashes all files, checks every existing target, backs
up affected Shared Authority files under
`E:\AI-Video-Ops-Backup\creative-authority-pre-bootstrap-<timestamp>`, creates
only missing files without replacement, validates the installed graph, and
writes a secret-free receipt at
`E:\AI-Video-Ops-Config\creative-authority-installation.json`. A partially
failed install removes only its own newly added, unchanged files; investigate
the error before retrying. Customer runtime directories are untouched.

8. Run `runtime-preflight.ps1` with the protected production env file. It now
   requires the installed Authority graph and receipt, but does **not** require
   any Customer, Ledger, or Generation Request. Keep
   `AIVO_NOVEL_NEWS_ROLLOUT=off`.
9. Start the Console through its normal service controller. Confirm the actual
   listener command/path, current Git HEAD, `/api/health`, and that
   `/api/create/options` projects `novel_news` (unavailable while rollout is
   off). Do not rely on the browser cache or a second Python process.
10. Read-only Mix smoke A: 鲸汤AI / 宽宽, quantity 4. Accept a structured
    supported, unsupported-coverage, or exhausted result; reject generic 503.
    Do **not** create a Request.
11. Read-only Mix smoke B: an approved customer with real process facts and an
    approved Speaker. Require supported feasibility and at least one eligible
    Pattern/Case. If no such real customer exists, use an isolated synthetic
    Persona outside Production data and report real-customer smoke pending.
12. Only after both smokes and preflight pass may the separate Novel News
    validation gate resume. This release performs no News model call.

The release is portable only when its canonical SHA-pinned references remain
valid for the target code/runtime. Approval receipts and media-rights status
are never changed by copying files.
