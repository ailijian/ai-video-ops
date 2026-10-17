"""Immutable Human operation records; execution projections never own decisions."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RuntimeError("Invalid Human operation record")
    return value


def write_once(path, value):
    """Atomic, exclusive publication; an interrupted retry cannot overwrite history."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if read(path) != value:
            raise RuntimeError("Human operation replay differs from its immutable record")
        return
    temporary = path.parent / ("." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if read(path) != value:
                raise RuntimeError("Human operation identity already contains another decision")
    finally:
        temporary.unlink(missing_ok=True)
