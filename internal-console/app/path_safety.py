from __future__ import annotations

import re
from pathlib import Path


IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{3,127}$")


def validate_identifier(value: str, *, field: str = "identifier") -> str:
    normalized = str(value or "").strip()
    if not IDENTIFIER_RE.fullmatch(normalized):
        raise ValueError(f"invalid {field}")
    return normalized


def resolve_within(root: Path, *parts: str) -> Path:
    resolved_root = Path(root).expanduser().resolve()
    candidate = resolved_root.joinpath(*parts).expanduser().resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("path escapes approved root") from exc
    return candidate
