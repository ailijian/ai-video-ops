from __future__ import annotations

import os
from pathlib import Path


FIXTURE_ROOT = (
    Path(__file__).resolve().parent / "fixtures" / "authority_baseline_v1"
)


def live_authority_root() -> Path:
    """Return only the explicitly configured live root; never fall back to data."""

    raw_root = os.environ.get("AIVO_LIVE_AUTHORITY_ROOT", "").strip()
    if not raw_root:
        return Path("__live_authority_root_not_configured__")
    return Path(raw_root).expanduser().resolve()
