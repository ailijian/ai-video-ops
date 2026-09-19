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

## Template use after Human Review approval

1. Copy `env.production.example` to an out-of-repository path.
2. Replace paths, add the real DeepSeek key, and restrict NTFS ACLs.
3. Edit the WinSW XML paths. Keep `--workers 1` and the loopback bind.
4. Run `powershell/preflight.ps1` without elevation.
5. Install services only in the separately approved deployment stage.

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
