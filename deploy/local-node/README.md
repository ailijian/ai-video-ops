# Local Production Node V1

This package contains templates only. It does not install WinSW, FRPC, change
the Windows power plan, open a firewall port, or connect to a cloud server.

## Frozen runtime

- Internal Console: `127.0.0.1:8000`
- Uvicorn workers: exactly `1`
- Reload: disabled
- Proxy trust: `127.0.0.1,::1` only; never `*`
- GPU-heavy concurrency: exactly `1`, enforced by `operation_lock_v1`
- Ollama: one process with `OLLAMA_NUM_PARALLEL=1` and
  `OLLAMA_MAX_LOADED_MODELS=1`

The current task runners and startup recovery depend on this single-process
service architecture. Starting a second Console service is unsupported.

## Runtime-only host contract

The old Windows host remains the development host and current Production
Authority until an explicit cutover. The RTX 4090 host is runtime-only staging:
do not edit business code, commit, or push there. Every code change follows
`old host -> commit -> push -> new host git pull`.

A clean Windows runtime node requires Python 3.12, Git, Node/npm, one running
Ollama instance, the preloaded `qwen3-vl:4b-instruct` model, and a preloaded
faster-whisper model directory. Host prerequisites and model downloads remain
manual; the bootstrap never installs CUDA/cuDNN/Ollama or downloads a model.
All deployment PowerShell entry points support the built-in Windows PowerShell
5.1 runtime; PowerShell 7 is not required.

After cloning and creating a protected production env file from
`env.production.example`, run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\deploy\local-node\powershell\bootstrap-runtime.ps1 `
  -RepoRoot E:\AI-Video-Ops `
  -EnvironmentFile E:\AI-Video-Ops-Config\local-node.production.env `
  -IncludeTestDependencies

powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\deploy\local-node\powershell\runtime-preflight.ps1 `
  -RepoRoot E:\AI-Video-Ops `
  -EnvironmentFile E:\AI-Video-Ops-Config\local-node.production.env
```

The bootstrap is repeatable. It creates or reuses the two repository venvs,
installs only repository-declared dependencies, and runs `pip check`. Omit
`-IncludeTestDependencies` after staging acceptance when only runtime
dependencies are wanted. It does not migrate Production data or change the
host configuration.

The ops-pipeline runtime contract is `ops-pipeline/requirements.txt`; its
separate test contract is `ops-pipeline/requirements-dev.txt`. Internal Console
continues to use `pip install -e ".[dev]"` from its existing `pyproject.toml`.

## Template use after Human Review approval

1. Copy `env.production.example` to an out-of-repository path.
2. Replace paths, add the real DeepSeek key, and restrict NTFS ACLs.
3. Edit the WinSW XML paths. Keep `--workers 1` and the loopback bind.
4. Run `powershell/preflight.ps1` without elevation.
5. Run `powershell/runtime-preflight.ps1` before service installation or
   restart on a rebuilt host.
6. Install services only in the separately approved deployment stage.

`frpc.xml.example` is a future service wrapper only. It intentionally contains
no server address or authentication token.

## Process boundaries

- WinSW is recommended for Internal Console and future FRPC restart policy.
- Ollama must have exactly one owner: GUI auto-start, Task Scheduler, or a
  tested service. Never enable GUI auto-start and a Windows service together.
- Historical GPU scripts that do not use `operation_lock_v1` must not run while
  the production node is active.

## Manual Windows checklist

- AC sleep: Never
- AC hibernate: Never
- Screen: may turn off
- Active network adapter power saving: off
- Prefer wired networking
- Prevent automatic Windows Update reboot during production hours
- Use a maintenance window only after the task queue is idle

## Backup

Run `internal-console/scripts/backup_local_node_v1.py` with an explicitly
configured destination on another disk, NAS, or external path. The tool uses
SQLite online backup, copies `ops-pipeline/data` and approved outputs/receipts,
creates checksums, performs a temporary restore smoke, and applies configurable
7-daily/4-weekly retention. It fails with
`BACKUP_REQUIRES_IDLE_WINDOW` while any task or formal Console Authority
mutation is running.

Case source video/music/cover, extracted original frames, and Qwen proxy
frames are transient computation assets and are excluded from Authority
backup. Source acquisition/metadata lineage, recorded source SHA-256,
structured evidence, and cleanup receipts remain in backup scope.
