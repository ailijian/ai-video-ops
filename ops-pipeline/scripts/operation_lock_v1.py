from __future__ import annotations

import hashlib
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

if os.name == "nt":
    import msvcrt
else:
    import fcntl


LOCK_SCHEMA_VERSION = "operation-lock-v1.0"


class OperationLockTimeout(RuntimeError):
    def __init__(self, key: str) -> None:
        super().__init__(f"Timed out waiting for operation lock: {key}")
        self.code = "OPERATION_IN_PROGRESS"
        self.key = key


def _lock_path(pipeline_root: Path, key: str) -> Path:
    normalized = str(key or "").strip()
    if not normalized:
        raise ValueError("operation lock key must not be empty")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return (
        Path(pipeline_root).resolve()
        / "data"
        / ".locks"
        / "operation_lock_v1"
        / f"{digest}.lock"
    )


@contextmanager
def operation_lock(
    pipeline_root: Path,
    key: str,
    *,
    timeout_seconds: float = 15.0,
    poll_seconds: float = 0.05,
    shared: bool = False,
) -> Iterator[None]:
    """Acquire one cross-process, crash-safe advisory operation lock.

    The marker file is not authority state and may remain on disk forever. Lock
    ownership is held by the OS file handle, so process exit releases it without
    stale-file breaking or a cleanup race.
    """

    if timeout_seconds < 0:
        raise ValueError("timeout_seconds must be non-negative")
    if poll_seconds <= 0:
        raise ValueError("poll_seconds must be positive")

    lock_path = _lock_path(pipeline_root, key)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    acquired = False

    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()

        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    mode = msvcrt.LK_NBRLCK if shared else msvcrt.LK_NBLCK
                    msvcrt.locking(handle.fileno(), mode, 1)
                else:
                    mode = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
                    fcntl.flock(handle.fileno(), mode | fcntl.LOCK_NB)
                acquired = True
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise OperationLockTimeout(key) from exc
                time.sleep(poll_seconds)

        if not shared:
            metadata = {
                "schema_version": LOCK_SCHEMA_VERSION,
                "key": key,
                "pid": os.getpid(),
                "acquired_at": datetime.now(timezone.utc).isoformat(),
            }
            encoded = json.dumps(metadata, ensure_ascii=False).encode("utf-8")
            handle.seek(1)
            handle.truncate()
            handle.write(encoded)
            handle.flush()
        yield
    finally:
        if acquired:
            try:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        handle.close()


def scoped_lock_key(scope: str, identity: str) -> str:
    normalized_scope = str(scope or "").strip().lower()
    normalized_identity = str(identity or "").strip()
    if normalized_scope not in {"business", "case", "persona", "request"}:
        raise ValueError("unsupported operation lock scope")
    if not normalized_identity:
        raise ValueError("operation lock identity must not be empty")
    return f"{normalized_scope}:{normalized_identity}"
