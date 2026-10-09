# Case Smart Intake V1.1 Production Deploy Runbook

Status: release preparation; **Production Validation Pending**. This procedure
is for a separately authorized maintenance window on the actual RTX4090 runtime
host. CSI-R1 prepares these commands on LIJIAN; it does not execute them on 4090.
Use Windows PowerShell 5.1, an elevated operator shell for the existing Windows
service, and the current service account/configuration. No FRP, Nginx, domain,
security-group, Novel News rollout, credentials or Authority installation change
is part of this deployment. Do not use fixtures on the runtime node.

## 1. Release identity and actual host discovery (read-only)

Transfer `release-identity.json` from the development release evidence. It pins
the exact Git commit, baseline, migration and static **Git blob** SHA-256 values;
checkout CRLF bytes can differ and are recorded separately. Never deploy a
copied working directory or select the moving tip of `main` as the version.

```powershell
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$Repo = (Resolve-Path (Read-Host 'Actual existing 4090 checkout path')).Path
$Identity = Get-Content -Raw -LiteralPath (Read-Host 'Transferred release-identity.json path') | ConvertFrom-Json
$ReleaseCommit = [string]$Identity.release_commit
if ($ReleaseCommit -notmatch '^[0-9a-f]{40}$') { throw 'Exact release commit required' }
$ServiceName = Read-Host 'Existing Console Windows service name'
$Service = Get-CimInstance Win32_Service -Filter "Name='$ServiceName'"
if (!$Service -or $Service.State -ne 'Running') { throw 'Existing running service required; investigate actual controller' }
$Wrapper = [regex]::Match($Service.PathName, '^"([^"]+)"|^(\S+)').Value.Trim('"')
$ServiceXml = [IO.Path]::ChangeExtension($Wrapper, '.xml')
[xml]$WrapperConfig = Get-Content -Raw -LiteralPath $ServiceXml
$EnvFile = [string](@($WrapperConfig.service.env | Where-Object name -eq 'AIVO_ENV_FILE')[0].value)
if (!(Test-Path -LiteralPath $EnvFile)) { throw 'Actual service environment file missing' }
if ((Resolve-Path $WrapperConfig.service.workingdirectory).Path -ne (Join-Path $Repo 'internal-console')) { throw 'Service checkout mismatch' }
$Python = Join-Path $Repo 'internal-console\.venv\Scripts\python.exe'
$PipelinePython = Join-Path $Repo 'ops-pipeline\.venv\Scripts\python.exe'
if ([string]$WrapperConfig.service.executable -ne $Python) { throw 'Service venv mismatch' }
if ([string]$WrapperConfig.service.arguments -notmatch '--workers\s+1\b' -or
    [string]$WrapperConfig.service.arguments -match '--reload|forwarded-allow-ips\s+["'']?\*') { throw 'Unsafe service arguments' }
# Review only safe selected fields, never dump the protected env or entire XML.
[pscustomobject]@{HostName=$env:COMPUTERNAME;Service=$ServiceName;Account=$Service.StartName;Wrapper=$Wrapper;EnvFile=$EnvFile;Repo=$Repo}
$OldCommit = (git -C $Repo rev-parse HEAD).Trim()
if ($LASTEXITCODE) { throw 'HEAD unavailable' }
git -C $Repo status --short
if (git -C $Repo status --porcelain --untracked-files=no) { throw 'Tracked runtime changes; do not overwrite' }
```

If the host uses Task Scheduler or another formal controller, STOP this Windows
service procedure and record/review its equivalent stop/start and environment
identity first. Do not add a fallback launcher or a second Console.
Confirm the host is the intended 4090, not LIJIAN. A service-account environment
or XML override of `AIVO_*` can supersede the protected file (`setdefault`);
resolve such overrides before proceeding. Do not print their secret values.

```powershell
function Assert-Listener {
    $listeners = @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)
    if ($listeners.Count -ne 1 -or $listeners[0].LocalAddress -ne '127.0.0.1') { throw 'Expected one loopback Console listener' }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listeners[0].OwningProcess)"
    if ($process.CommandLine -notmatch 'uvicorn\s+app.main:app' -or $process.CommandLine -notmatch '--workers\s+1\b' -or $process.CommandLine -match '--reload') { throw 'Listener command mismatch' }
    $controller = Get-CimInstance Win32_Service -Filter "Name='$ServiceName'"
    $ancestor = $process
    $owned = $false
    for ($depth=0; $depth -lt 8 -and $ancestor; $depth++) {
        if ($ancestor.ProcessId -eq $controller.ProcessId) { $owned=$true; break }
        $ancestor = Get-CimInstance Win32_Process -Filter "ProcessId=$($ancestor.ParentProcessId)" -ErrorAction SilentlyContinue
    }
    if (!$owned) { throw '8000 is not owned by the recorded service' }
    $process | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine
}
Assert-Listener
$env:AIVO_ENV_FILE = $EnvFile
Push-Location (Join-Path $Repo 'internal-console')
try {
    $Effective = @'
import json
from app.config import Settings
s=Settings.from_environment()
print(json.dumps(dict(database=str(s.database_path),pipeline=str(s.pipeline_root),case_worker=s.case_analysis_worker_enabled,background_worker=s.background_worker_enabled,customer_worker=s.customer_analysis_worker_enabled,speaker_worker=s.speaker_analysis_worker_enabled,provider=s.case_acquisition_provider,queue_max=s.task_queue_max,gpu_pending_per_user=s.gpu_pending_per_user_max)))
'@ | & $Python - | ConvertFrom-Json
    if ($LASTEXITCODE) { throw 'Settings discovery failed' }
} finally { Pop-Location }
$Database = [string]$Effective.database
if (!(Test-Path -LiteralPath $Database) -or $Effective.pipeline -ne (Join-Path $Repo 'ops-pipeline')) { throw 'Actual paths unconfirmed' }
$Effective # whitelisted non-secret settings only
nvidia-smi --query-gpu=name,driver_version,memory.used,memory.total --format=csv,noheader
if ($LASTEXITCODE) { throw 'GPU unavailable' }
```

The **4090 database path, old commit, schema, service ownership and effective
worker settings are pending live discovery**. The development rehearsal used
`E:\projects\ai-video-ops\internal-console\var\console.sqlite3`; that is not
evidence of the 4090 path. The existing Whisper contract is CPU/int8; observe
actual GPU use rather than assuming Whisper uses CUDA.

## 2. Quiesce submissions, inspect queue, stop through the existing controller

Arrange a Human maintenance window: colleagues stop submissions/confirmations
and synchronous mutations. In `/tasks`, wait for queued/running work to finish
naturally. Pending intake-group items must drain as well. Never kill a model
task, clear a lease, edit task rows, or stop Ollama to force an idle window.
Keep the window closed through the read-only smoke.

Create an external, protected evidence directory. The helper below reports only
counts and row hashes; it does not dump account/session/payload contents.

```powershell
$EvidenceParent = (Resolve-Path (Read-Host 'Existing protected external evidence/backup directory')).Path
if ($EvidenceParent.StartsWith($Repo, [StringComparison]::OrdinalIgnoreCase)) { throw 'Use an external destination' }
$Evidence = Join-Path $EvidenceParent ('csi-' + (Get-Date -Format 'yyyyMMddTHHmmss'))
New-Item -ItemType Directory -Path $Evidence -ErrorAction Stop | Out-Null
$DbAudit = Join-Path $Evidence 'db-audit.py'
@'
import sys,json,sqlite3,hashlib
from pathlib import Path
from contextlib import closing
path=Path(sys.argv[1]).resolve()
with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert not db.execute('PRAGMA foreign_key_check').fetchall()
    names=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    tables={}
    for name in names:
        rows=sorted(db.execute('SELECT * FROM "'+name.replace('"','""')+'"').fetchall(),key=repr)
        tables[name]={'count':len(rows),'rows_sha256':hashlib.sha256(repr(rows).encode()).hexdigest()}
    versions=[r[0] for r in db.execute('SELECT version FROM schema_migrations ORDER BY version')]
    expected={'001_initial','002_speaker_analysis_task','003_local_production_node_hardening'}
    assert expected.issubset(versions) and set(versions).issubset(expected|{'004_case_intake_groups'}),'Unexpected migration versions'
    intake_names={'case_intake_groups','case_intake_items'}
    if '004_case_intake_groups' in versions:
        assert intake_names.issubset(names),'004 tables missing'
        assert db.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_case_intake_pending'").fetchone(),'004 index missing'
        assert len(db.execute('PRAGMA foreign_key_list(case_intake_groups)').fetchall())==1
        assert len(db.execute('PRAGMA foreign_key_list(case_intake_items)').fetchall())==2
    else:
        assert not intake_names.intersection(names),'Unmarked partial 004; do not migrate'
    active=db.execute("SELECT COUNT(*) FROM tasks WHERE status IN ('queued','running')").fetchone()[0]
    pending=db.execute("SELECT COUNT(*) FROM case_intake_items WHERE state='pending'").fetchone()[0] if 'case_intake_items' in names else 0
report=dict(database=str(path),versions=versions,tables=tables,integrity='ok',foreign_key_errors=0,active_tasks=active,pending_intake=pending)
if '--idle' in sys.argv: assert active==pending==0,'WAIT_FOR_IDLE; do not terminate work'
if '--baseline' in sys.argv:
    baseline=json.loads(Path(sys.argv[sys.argv.index('--baseline')+1]).read_text(encoding='utf-8-sig'))
    assert all(tables[name]==value for name,value in baseline['tables'].items() if name!='schema_migrations'),'Historical rows changed'
print(json.dumps(report,indent=2))
'@ | Set-Content -LiteralPath $DbAudit -Encoding UTF8
& $Python $DbAudit $Database --idle | Set-Content (Join-Path $Evidence 'before-stop.json') -Encoding UTF8
if ($LASTEXITCODE) { throw 'Wait for idle; do not stop service' }
Assert-Listener | ConvertTo-Json | Set-Content (Join-Path $Evidence 'old-listener.json') -Encoding UTF8
Stop-Service -Name $ServiceName -ErrorAction Stop
(Get-Service $ServiceName).WaitForStatus('Stopped',[TimeSpan]::FromSeconds(60))
if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { throw 'Listener still active; investigate without killing it' }
& $Python $DbAudit $Database --idle | Set-Content (Join-Path $Evidence 'before.json') -Encoding UTF8
if ($LASTEXITCODE) { throw 'Queue changed; stop deployment and investigate' }
```

## 3. Verified Online Backup and exact code promotion

```powershell
$BackupResult = & $Python (Join-Path $Repo 'internal-console\scripts\backup_local_node_v1.py') --destination $EvidenceParent --database $Database --pipeline-root (Join-Path $Repo 'ops-pipeline') --repo-root $Repo
if ($LASTEXITCODE) { throw 'Online backup failed; do not migrate' }
$Backup = ($BackupResult | ConvertFrom-Json).backup_root
& $Python (Join-Path $Repo 'internal-console\scripts\backup_local_node_v1.py') --validate $Backup
if ($LASTEXITCODE) { throw 'Backup restore/checksum validation failed' }
$BackupDatabase = Join-Path $Backup 'internal-console\console.sqlite3'
& $Python $DbAudit $BackupDatabase --idle --baseline (Join-Path $Evidence 'before.json') | Set-Content (Join-Path $Evidence 'backup.json') -Encoding UTF8
if ($LASTEXITCODE) { throw 'Backup rows/integrity differ' }
Get-FileHash -Algorithm SHA256 $BackupDatabase | ConvertTo-Json | Set-Content (Join-Path $Evidence 'backup-sha.json') -Encoding UTF8

git -C $Repo fetch origin main
if ($LASTEXITCODE) { throw 'Fetch failed; use the reviewed bundle alternative below' }
git -C $Repo cat-file -e "$ReleaseCommit^{commit}"
if ($LASTEXITCODE) { throw 'Release commit missing' }
git -C $Repo merge --ff-only $ReleaseCommit
if ($LASTEXITCODE -or (git -C $Repo rev-parse HEAD).Trim() -ne $ReleaseCommit) { throw 'Exact fast-forward failed; never force/reset' }
```

If GitHub is unreachable, use a previously configured formal Codeup remote,
without creating a new source Authority. CSI-R1 found no Codeup remote on
LIJIAN. Existing exact-commit Git bundle fallback:

```powershell
# Development host ONLY, after committed regression PASS:
git bundle create E:\csi-r1-release\case-smart-intake.bundle main
git bundle verify E:\csi-r1-release\case-smart-intake.bundle
# Transfer bundle + identity through the approved transport; verify SHA-256.
# Runtime substitute for fetch/merge above (do not run both alternatives):
# git -C $Repo bundle verify <transferred-bundle>
# git -C $Repo fetch <transferred-bundle> main
# git -C $Repo merge --ff-only $ReleaseCommit
```

Verify every identity-pinned file from Git, and require each checkout file to
match its Git object after normal Git text filters. Record actual disk hashes
for the local migration/static assets as well.

```powershell
$IdentityPath = Join-Path $Evidence 'release-identity.json'
$Identity | ConvertTo-Json -Depth 12 | Set-Content $IdentityPath -Encoding UTF8
@'
import sys,json,hashlib,subprocess
from pathlib import Path
repo=Path(sys.argv[1]); identity=json.loads(Path(sys.argv[2]).read_text(encoding='utf-8-sig'))
def git(*args): return subprocess.check_output(['git','-C',str(repo),*args])
assert git('rev-parse','HEAD').decode().strip()==identity['release_commit']
disk={}
for name,expected in identity['git_blob_sha256'].items():
    blob=git('show','HEAD:'+name)
    assert hashlib.sha256(blob).hexdigest()==expected,name
    assert git('hash-object','--path='+name,str(repo/name)).strip()==git('rev-parse','HEAD:'+name).strip(),name
    disk[name]=hashlib.sha256((repo/name).read_bytes()).hexdigest()
print(json.dumps(dict(commit=identity['release_commit'],checkout_sha256=disk),indent=2))
'@ | Set-Content (Join-Path $Evidence 'verify-identity.py') -Encoding UTF8
& $Python (Join-Path $Evidence 'verify-identity.py') $Repo $IdentityPath | Set-Content (Join-Path $Evidence 'checkout-identity.json') -Encoding UTF8
if ($LASTEXITCODE) { throw 'Mixed code/static/migration release' }
& $Python -m pip check
if ($LASTEXITCODE) { throw 'Console dependencies invalid' }
& $PipelinePython -m pip check
if ($LASTEXITCODE) { throw 'Pipeline dependencies invalid' }
```

There are no dependency or environment-contract changes in this RC. Reuse the
existing venvs and protected configuration. The existing bootstrap is the
approved repair/install route if a declared dependency is missing; do not
upgrade arbitrary packages during deployment.

## 4. Rehearse the actual backup; migrate only while stopped

Check `before.json`: 001–003 must exist. If 004 is already marked, verify both
tables/index and their foreign keys, preserve their rows, and run the idempotent
checks below. Unknown versions, unmarked partial tables or missing legacy
versions are STOP conditions. Never hand-insert a migration marker or drop a
table. The populated migration-audit CLI also injects a failure **only in a
separate copy**; it requires users/tasks and 004 not yet applied:

```powershell
$Before = Get-Content -Raw (Join-Path $Evidence 'before.json') | ConvertFrom-Json
if ($Before.versions -notcontains '004_case_intake_groups' -and $Before.tables.users.count -gt 0 -and $Before.tables.tasks.count -gt 0) {
    & $Python (Join-Path $Repo 'internal-console\tests\test_case_intake_migration_v1.py') --source $BackupDatabase --output (Join-Path $Evidence 'migration-rehearsal')
    if ($LASTEXITCODE) { throw 'Actual backup rehearsal failed' }
}
Push-Location (Join-Path $Repo 'internal-console')
try {
    # Always rehearse the real backup, including a genesis/empty or already-004 DB.
    $Rehearsal = Join-Path $Evidence 'upgrade-rehearsal.sqlite3'
    @'
import sys,sqlite3
from pathlib import Path
from contextlib import closing
source=Path(sys.argv[1]).resolve(); target=Path(sys.argv[2])
assert not target.exists()
with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as src:
    with closing(sqlite3.connect(target)) as dst: src.backup(dst)
'@ | & $Python - $BackupDatabase $Rehearsal
    if ($LASTEXITCODE) { throw 'Rehearsal copy failed' }
    $MigrationScript = Join-Path $Evidence 'apply-migrations.py'
    @'
import sys
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[2])/'internal-console'))
from app.database import apply_migrations
apply_migrations(Path(sys.argv[1]),Path(sys.argv[2])/'internal-console/migrations')
'@ | Set-Content $MigrationScript -Encoding UTF8
    & $Python $MigrationScript $Rehearsal $Repo
    if ($LASTEXITCODE) { throw 'Rehearsal migration failed' }
    & $Python $DbAudit $Rehearsal --idle --baseline (Join-Path $Evidence 'before.json') | Set-Content (Join-Path $Evidence 'rehearsal.json') -Encoding UTF8
    if ($LASTEXITCODE) { throw 'Rehearsal lost historical rows' }
    & $Python $MigrationScript $Rehearsal $Repo
    if ($LASTEXITCODE) { throw 'Rehearsal repeat migration failed' }
    & $Python $DbAudit $Rehearsal --idle --baseline (Join-Path $Evidence 'rehearsal.json') | Set-Content (Join-Path $Evidence 'rehearsal-repeat.json') -Encoding UTF8
    if ($LASTEXITCODE) { throw 'Rehearsal repeat changed rows' }
    & $Python $MigrationScript $Database $Repo
    if ($LASTEXITCODE) { throw 'Migration failed; no service restart' }
    & $Python $DbAudit $Database --idle --baseline (Join-Path $Evidence 'before.json') | Set-Content (Join-Path $Evidence 'migrated.json') -Encoding UTF8
    if ($LASTEXITCODE) { throw 'Historical data/integrity failure' }
    & $Python $MigrationScript $Database $Repo
    if ($LASTEXITCODE) { throw 'Repeat migration failed' }
    & $Python $DbAudit $Database --idle --baseline (Join-Path $Evidence 'migrated.json') | Set-Content (Join-Path $Evidence 'repeated.json') -Encoding UTF8
    if ($LASTEXITCODE) { throw 'Repeat migration changed rows' }
} finally { Pop-Location }
$Migrated = Get-Content -Raw (Join-Path $Evidence 'migrated.json') | ConvertFrom-Json
if ($Migrated.versions -notcontains '004_case_intake_groups') { throw '004 marker missing' }
```

The transactional runner uses `BEGIN IMMEDIATE`: DDL, historical rows and
markers roll back together. A failure must leave the original row hashes and
schema unchanged; audit before deciding to retry. Earlier non-transactional
partial state requires the verified pre-upgrade backup/recovery review.

## 5. Runtime and Shared Creative Authority preflight; restart and identify

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Repo 'deploy\local-node\powershell\runtime-preflight.ps1') -RepoRoot $Repo -EnvironmentFile $EnvFile
if ($LASTEXITCODE) { throw 'Runtime/Authority preflight failed; keep Console stopped' }
& $PipelinePython (Join-Path $Repo 'deploy\creative-authority\verify_release.py') preflight --pipeline-root (Join-Path $Repo 'ops-pipeline') --repo-root $Repo --receipt E:\AI-Video-Ops-Config\creative-authority-installation.json
if ($LASTEXITCODE) { throw 'Shared Authority graph/installation receipt invalid' }
@'
import sys
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'scripts'))
from operation_lock_v1 import operation_lock
with operation_lock(Path(sys.argv[1]),'global_gpu',timeout_seconds=0):
    print('GPU guard acquired/released; no model invoked')
'@ | & $PipelinePython - (Join-Path $Repo 'ops-pipeline')
if ($LASTEXITCODE) { throw 'GPU guard unavailable; investigate without forcing unlock' }
if (!$Effective.case_worker) { throw 'Case worker disabled; controlled analysis cannot proceed' }
if ($Effective.provider -ne 'qiyun') { throw 'Qiyun production validation configuration not ready; no silent provider fallback' }
Start-Service -Name $ServiceName -ErrorAction Stop
(Get-Service $ServiceName).WaitForStatus('Running',[TimeSpan]::FromSeconds(60))
Start-Sleep -Seconds 3
Assert-Listener | ConvertTo-Json | Set-Content (Join-Path $Evidence 'new-listener.json') -Encoding UTF8
if ((git -C $Repo rev-parse HEAD).Trim() -ne $ReleaseCommit) { throw 'Code changed after restart' }
& $Python $DbAudit $Database --idle --baseline (Join-Path $Evidence 'migrated.json') | Set-Content (Join-Path $Evidence 'after-start.json') -Encoding UTF8
if ($LASTEXITCODE) { throw 'Unexpected startup writes/tasks; investigate' }
$LocalHealth = Invoke-RestMethod 'http://127.0.0.1:8000/api/health'
if ($LocalHealth.status -ne 'ok') { throw 'Local health failed' }
$PublicBase = (Read-Host 'Existing public HTTPS Console origin; no URL/config change').TrimEnd('/')
if ($PublicBase -notmatch '^https://[^/]+$') { throw 'Use the existing HTTPS origin' }
$PublicHealth = Invoke-RestMethod ($PublicBase + '/api/health')
if ($PublicHealth.status -ne 'ok') { throw 'Public health failed; do not alter FRP/Nginx here' }
```

Preflight checks package/model inventory and credential **presence**, not Qiyun
validity or real inference. Verify the unchanged service-account Ollama
environment has one owner, `OLLAMA_NUM_PARALLEL=1`, and
`OLLAMA_MAX_LOADED_MODELS=1`. Inspect GPU compute processes without starting a
model. Shared Authority failure is a separate blocked gate, not permission to
install/reapprove/overwrite Authority. Fresh Runtime needs no Ledger/Request.

## 6. Read-only smoke and controlled real validation (separate Human go-ahead)

Before reopening submissions, log in through the existing public HTTPS flow
with existing authorized accounts. Use browser devtools/network evidence and
real 1440×1000 / 390×844 viewports; hard reload to bypass cached entry modules.
Do not put passwords, cookies, CSRF tokens or signed media URLs in reports.

Read-only smoke: open `/cases/new`, confirm link-only intake and local-upload
fallback; GET `/api/cases`, `/api/tasks`, `/api/case-intake/groups`, an existing
group/detail/classification and operator activity. Compare historical references
and counts with the backup. Unauthenticated routes must reject access; actual
mutation CSRF/locks are covered offline and must not be probed by creating dummy
Production data. Record release/static SHA, service PID/controller/env path,
actual DB versions, preflight results and local/public Health together.

Only after a separate explicit approval to spend on real source/model work:

| Group | Controlled action | Required observed evidence |
|---|---|---|
| A | One lawful, clearly structured Douyin video; paste full share text | Extracted stable identity; exactly one task/attempt; Qiyun receipt; Qwen observable evidence; Whisper speech/times; privacy projection; stage times; calls/cost when available; GPU peak/processes |
| A Human gate | Inspect recommendation, modify classification if needed, confirm, continue Case Review | Original AI suggestion and Human choice/actor/time distinct; no additional expensive call on edit; final evidence/Privacy/Proof/source review still required; no automatic Case/Compatibility approval |
| B | One clear News video, then one mixed/ambiguous video; small batch only | Human comparison against real narration/onscreen evidence; News not passed as short Mix; insufficient evidence remains uncertain; model value alone is not an accuracy verdict |
| C duplicate | Paste a Group A stable identity again | Existing Case/task discoverable; task/attempt/call counts unchanged; no second Qiyun fee/full analysis |
| C recovery | Safely available failure, then one explicit retry or governed upload fallback | Same-task retry reuses validated checkpoints; at most 3 manual retries per task; initial acquisition plus retries may cost up to 4 provider calls if acquisition never completed; actual receipts/cost remain authoritative |
| Recovery/UI | Close/reopen, refresh; second existing account reads shared batch; real mobile scroll/click | Persistent same group/tasks, login required, independent partial completion; confirmed cards read-only; edit only on demand; one primary action; bottom navigation never intercepts button |

Do not intentionally interrupt a real model task. Restart/lease fault injection
and ten-item resource tests remain isolated evidence. A first real batch is one
video, followed by a small batch, not ten simultaneous GPU jobs. An explicit
new upload/reanalysis is a separate paid/rights-reviewed attempt, not a way to
bypass a capped failed-stage retry. Do not retry repeatedly when quota/rate
errors require operator intervention. This RC adds no absolute currency budget;
measure provider/model billing and approve that budget before this gate.

Collect task IDs, attempts, sanitized stage logs/times and receipts, original
AI/Human classification evidence, relevant immutable Case/receipt/fingerprint/
compatibility hashes, source/privacy review, screenshots and model-call counts.
Never edit Authority JSON or the AI original suggestion to obtain PASS.
`PRODUCTION_PASS` / `COLLEAGUE_CONTROLLED_USE_READY` remain forbidden until all
real provider/model, accuracy, recovery, Authority and UI gates are observed.

## 7. Failure and rollback boundaries

Before any new business write: keep maintenance closed, wait for idle and stop
through the recorded controller; take a fresh diagnostic online backup. Verify
that task/payload/group/Authority hashes have no new business changes (login
session timestamps alone need separate accounting). If 004 succeeded, its
additive tables do not require automatic removal. The exact baseline
`1c640ede641fdb10a4b250e4e4189e47a7180765` was tested with the upgraded populated
copy: old startup left rows/004 marker unchanged, old authenticated API read 42
historical tasks, and an isolated approved fixture Case was readable. This is
**read compatibility**, not old-worker compatibility for new hint-free tasks,
and not proof for an unknown actual old 4090 commit.

For a confirmed pre-write rollback, rehearse the **actual** old commit on the
verified upgraded copy with workers disabled. Then use `git switch --detach
$OldCommit` on the clean stopped checkout (never `reset --hard`), repeat runtime
preflight and restart with the existing controller. Keeping the upgraded DB
requires that old-commit read check. If the check fails or migration is partial,
an operator may restore the verified database via SQLite online backup only
after proving no new business facts exist. Preserve the failed DB/WAL and all
diagnostic backups first; never blindly copy an old `.sqlite3` over a live WAL
database. Any Authority restoration is a separate reviewed recovery operation.

After any new Task/Case/classification/review/approval write: **do not restore
the pre-upgrade DB and do not delete new records/artifacts**. Close submissions,
allow active tasks to end safely, stop the controller when idle, and back up the
latest database plus Authority. Retain the new-schema database and attempt /
approval lineage. Prefer a reviewed forward fix. An older application must not
run workers against unsupported hint-free tasks; a compatibility repair or
explicit recovery plan is required before restart. Git rollback alone is not
data rollback. Record the incident and require a Human recovery decision.

If a queue cannot safely drain, do not force termination: pause deployment and
escalate the concrete task/lease/provider problem. Never automatically undo
Case approval, Compatibility, media rights or customer facts.

## 8. CSI-R1 evidence and remaining gates

Development evidence is stored outside Git in `E:\csi-r1-release` and
`E:\csi-r1-migration`. The release identity pins the committed code and migration;
the post-commit root verifier supplies the final regression result. Earlier
V1.1 integrated browser/ten-item/recovery evidence is under
`E:\csi-v1-1-runtime`; it uses the complete new ASGI/auth/static stack and an
isolated database with a serial fixture driver, no Qiyun/models/GPU.

Remaining gates: actual 4090 host/service/DB/schema/backup and old-commit rollback
rehearsal; existing Shared Creative Authority receipt/graph; actual runtime
preflight and public Health; lawful selected videos and paid-validation approval;
real Qiyun/Qwen/Whisper and privacy evidence; real conservative classification
quality and billing; real desktop/mobile end-to-end behavior. CSI-R1 stops before
any of those production mutations or calls.
