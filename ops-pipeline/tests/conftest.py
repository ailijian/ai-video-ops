from __future__ import annotations

import os
from pathlib import Path

import pytest


LIVE_AUTHORITY_ENV = "AIVO_LIVE_AUTHORITY_ROOT"


def _tree_state(root: Path) -> dict[str, tuple[int, int]]:
    return {
        path.relative_to(root).as_posix(): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Fail closed when explicitly selected live Authority tests lack a root.

    The default marker expression deselects these tests.  When an operator asks
    for ``-m live_authority``, an absent or invalid root produces one clear skip
    reason without falling back to repository ``data``.
    """

    raw_root = os.environ.get(LIVE_AUTHORITY_ENV, "").strip()
    reason: str | None = None
    if not raw_root:
        reason = f"{LIVE_AUTHORITY_ENV} is required for live Authority smoke tests"
    else:
        root = Path(raw_root).expanduser()
        if not root.is_absolute() or not root.is_dir():
            reason = (
                f"{LIVE_AUTHORITY_ENV} must name an existing absolute pipeline root"
            )

    if reason is None:
        return

    marker = pytest.mark.skip(reason=reason)
    for item in items:
        if item.get_closest_marker("live_authority") is not None:
            item.add_marker(marker)


@pytest.fixture(scope="session", autouse=True)
def enforce_live_authority_read_only(
    request: pytest.FixtureRequest,
) -> None:
    selected_live = any(
        item.get_closest_marker("live_authority") is not None
        and not any(mark.name == "skip" for mark in item.iter_markers())
        for item in request.session.items
    )
    raw_root = os.environ.get(LIVE_AUTHORITY_ENV, "").strip()
    if not selected_live or not raw_root:
        yield
        return

    root = Path(raw_root).expanduser().resolve()
    before = _tree_state(root)
    yield
    after = _tree_state(root)
    if after != before:
        pytest.fail(
            "live_authority tests changed the configured Authority root; "
            "this layer must remain read-only"
        )
