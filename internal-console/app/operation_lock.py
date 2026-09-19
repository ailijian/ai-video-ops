from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .canonical_gateway import CanonicalOperationError
from .config import Settings


_SCRIPTS_ROOT = Path(__file__).resolve().parents[2] / "ops-pipeline" / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from operation_lock_v1 import (  # noqa: E402
    OperationLockTimeout,
    operation_lock,
    scoped_lock_key,
)


AUTHORITY_BACKUP_GATE = "authority_backup_gate"


@contextmanager
def authority_mutation_barrier(
    settings: Settings,
    *,
    timeout_seconds: float = 1.0,
) -> Iterator[None]:
    try:
        with operation_lock(
            settings.pipeline_root,
            AUTHORITY_BACKUP_GATE,
            timeout_seconds=timeout_seconds,
            shared=True,
        ):
            yield
    except OperationLockTimeout as exc:
        raise CanonicalOperationError(
            "OPERATION_IN_PROGRESS",
            "本机正在执行互斥维护或备份，请稍后刷新重试。",
            "等待维护窗口结束后重新提交；不要重复操作。",
        ) from exc


@contextmanager
def authority_operation_lock(
    settings: Settings,
    scope: str,
    identity: str,
    *,
    timeout_seconds: float = 1.0,
) -> Iterator[None]:
    try:
        with authority_mutation_barrier(
            settings,
            timeout_seconds=timeout_seconds,
        ):
            with operation_lock(
                settings.pipeline_root,
                scoped_lock_key(scope, identity),
                timeout_seconds=timeout_seconds,
            ):
                yield
    except OperationLockTimeout as exc:
        raise CanonicalOperationError(
            "OPERATION_IN_PROGRESS",
            "该内容正在被另一位同事处理，请刷新后继续。",
            "等待当前操作完成后刷新页面；不要重复提交。",
        ) from exc


__all__ = [
    "OperationLockTimeout",
    "authority_mutation_barrier",
    "authority_operation_lock",
    "operation_lock",
    "scoped_lock_key",
]
