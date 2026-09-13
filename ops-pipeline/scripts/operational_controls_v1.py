from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "operational-controls-v1"
DEFAULT_RELEASE_REQUIREMENT = "explicit_operator_release"
BUSINESS_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_business_id(business_id: str) -> str:
    value = business_id.strip()
    if not BUSINESS_ID_PATTERN.fullmatch(value):
        raise ValueError(
            "business_id must contain only letters, numbers, underscores, or hyphens."
        )
    return value


def require_text(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} must be explicit and non-empty.")
    return normalized


def default_operations_root() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "operations"


def controls_path(operations_root: Path, business_id: str) -> Path:
    return operations_root / validate_business_id(business_id) / "operational_controls_v1.json"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Operational Controls must be a JSON object: {path}")
    return value


def validate_controls(value: dict[str, Any], business_id: str) -> None:
    errors: list[str] = []
    if value.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if value.get("business_id") != business_id:
        errors.append("business_id does not match the requested business")
    hold = value.get("operational_hold")
    if not isinstance(hold, dict):
        errors.append("operational_hold must be an object")
    else:
        if not isinstance(hold.get("active"), bool):
            errors.append("operational_hold.active must be boolean")
        for field in ("reason", "set_by", "set_at", "release_requires"):
            if not isinstance(hold.get(field), str) or not hold[field].strip():
                errors.append(f"operational_hold.{field} must be non-empty")
        if hold.get("release_requires") != DEFAULT_RELEASE_REQUIREMENT:
            errors.append(
                "operational_hold.release_requires must remain explicit_operator_release"
            )
    for field in ("updated_at", "last_action", "last_actor"):
        if not isinstance(value.get(field), str) or not value[field].strip():
            errors.append(f"{field} must be non-empty")
    history = value.get("history", [])
    if not isinstance(history, list):
        errors.append("history must be an array when present")
    if errors:
        raise ValueError("Invalid Operational Controls: " + "; ".join(errors))


def load_controls(
    operations_root: Path,
    business_id: str,
    *,
    required: bool = False,
) -> tuple[dict[str, Any] | None, Path]:
    business_id = validate_business_id(business_id)
    path = controls_path(operations_root, business_id)
    if not path.is_file():
        if required:
            raise FileNotFoundError(path)
        return None, path
    value = read_json(path)
    validate_controls(value, business_id)
    return value, path


def write_controls(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


def set_hold(
    operations_root: Path,
    business_id: str,
    actor: str,
    reason: str,
    *,
    at: str | None = None,
) -> tuple[dict[str, Any], Path]:
    business_id = validate_business_id(business_id)
    actor = require_text(actor, "actor")
    reason = require_text(reason, "reason")
    timestamp = at or now_iso()
    current, path = load_controls(operations_root, business_id)
    history = list((current or {}).get("history") or [])
    history.append(
        {
            "action": "set_hold",
            "actor": actor,
            "at": timestamp,
            "reason": reason,
        }
    )
    value = {
        "schema_version": SCHEMA_VERSION,
        "business_id": business_id,
        "operational_hold": {
            "active": True,
            "reason": reason,
            "set_by": actor,
            "set_at": timestamp,
            "release_requires": DEFAULT_RELEASE_REQUIREMENT,
        },
        "updated_at": timestamp,
        "last_action": "set_hold",
        "last_actor": actor,
        "history": history,
    }
    validate_controls(value, business_id)
    write_controls(path, value)
    return value, path


def release_hold(
    operations_root: Path,
    business_id: str,
    actor: str,
    *,
    at: str | None = None,
) -> tuple[dict[str, Any], Path]:
    business_id = validate_business_id(business_id)
    actor = require_text(actor, "actor")
    current, path = load_controls(operations_root, business_id, required=True)
    assert current is not None
    hold = dict(current["operational_hold"])
    if hold.get("active") is not True:
        raise RuntimeError("Operational Hold is already inactive; no release was applied.")
    if hold.get("release_requires") != DEFAULT_RELEASE_REQUIREMENT:
        raise RuntimeError("Operational Hold cannot be released by this V1 operation.")
    timestamp = at or now_iso()
    history = list(current.get("history") or [])
    history.append({"action": "release_hold", "actor": actor, "at": timestamp})
    hold["active"] = False
    value = {
        **current,
        "operational_hold": hold,
        "updated_at": timestamp,
        "last_action": "release_hold",
        "last_actor": actor,
        "history": history,
    }
    validate_controls(value, business_id)
    write_controls(path, value)
    return value, path


def render_text(value: dict[str, Any] | None, business_id: str, path: Path) -> str:
    if value is None:
        return "\n".join(
            (
                "AI VIDEO OPS — OPERATIONAL CONTROLS",
                f"Business: {business_id}",
                "Operational Hold: NOT_CONFIGURED",
                f"Path: {path}",
            )
        )
    hold = value["operational_hold"]
    return "\n".join(
        (
            "AI VIDEO OPS — OPERATIONAL CONTROLS",
            f"Business: {business_id}",
            f"Operational Hold: {'ACTIVE' if hold['active'] else 'INACTIVE'}",
            f"Reason: {hold['reason']}",
            f"Set by: {hold['set_by']}",
            f"Release requires: {hold['release_requires']}",
            f"Last action: {value['last_action']}",
            f"Last actor: {value['last_actor']}",
            f"Path: {path}",
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Show or explicitly update Operator Action Control metadata."
    )
    parser.add_argument(
        "--operations-root",
        default=str(default_operations_root()),
        help="Default: <pipeline>/data/operations",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    show_parser = subparsers.add_parser("show", help="Read controls without writing.")
    show_parser.add_argument("--business-id", required=True)
    show_parser.add_argument("--format", choices=("text", "json"), default="text")

    set_parser = subparsers.add_parser("set-hold", help="Set an explicit Human hold.")
    set_parser.add_argument("--business-id", required=True)
    set_parser.add_argument("--actor", required=True)
    set_parser.add_argument("--reason", required=True)

    release_parser = subparsers.add_parser(
        "release-hold", help="Release a hold through explicit Human action."
    )
    release_parser.add_argument("--business-id", required=True)
    release_parser.add_argument("--actor", required=True)

    args = parser.parse_args()
    root = Path(args.operations_root).expanduser().resolve()
    if args.command == "show":
        value, path = load_controls(root, args.business_id)
        if args.format == "json":
            output = value or {
                "schema_version": SCHEMA_VERSION,
                "business_id": validate_business_id(args.business_id),
                "operational_hold": None,
                "configured": False,
            }
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            print(render_text(value, args.business_id, path))
        return
    if args.command == "set-hold":
        value, path = set_hold(root, args.business_id, args.actor, args.reason)
    else:
        value, path = release_hold(root, args.business_id, args.actor)
    print(render_text(value, args.business_id, path))


if __name__ == "__main__":
    main()
