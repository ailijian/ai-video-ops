"""Marker initialization must obey the same OS lock as operation metadata."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import operation_lock_v1 as locks


@pytest.mark.parametrize("shared", [False, True])
def test_first_use_never_writes_before_os_lock(tmp_path, monkeypatch, shared):
    owned = {}
    if os.name == "nt":
        original_lock = locks.msvcrt.locking
        def tracked(fd, mode, size):
            result = original_lock(fd, mode, size)
            owned[fd] = mode != locks.msvcrt.LK_UNLCK
            return result
        monkeypatch.setattr(locks.msvcrt, "locking", tracked)
    else:
        original_lock = locks.fcntl.flock
        def tracked(fd, mode):
            result = original_lock(fd, mode)
            owned[fd] = mode != locks.fcntl.LOCK_UN
            return result
        monkeypatch.setattr(locks.fcntl, "flock", tracked)
    original_open = Path.open
    class GuardedHandle:
        def __init__(self, handle):
            self.handle = handle
        def __getattr__(self, name):
            return getattr(self.handle, name)
        def write(self, value):
            assert owned.get(self.handle.fileno()), "marker write before OS ownership can race another lock holder"
            return self.handle.write(value)
    def guarded_open(path, *args, **kwargs):
        handle = original_open(path, *args, **kwargs)
        return GuardedHandle(handle) if path.suffix == ".lock" else handle
    monkeypatch.setattr(Path, "open", guarded_open)
    with locks.operation_lock(tmp_path, "case:first-use", shared=shared, timeout_seconds=0):
        assert any(owned.values())
    with locks.operation_lock(tmp_path, "case:first-use", timeout_seconds=0):
        assert any(owned.values())
