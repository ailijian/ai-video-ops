from __future__ import annotations

import argparse
import sys
from pathlib import Path


CONSOLE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CONSOLE_ROOT))

from app.auth_service import provision_user  # noqa: E402
from app.config import Settings  # noqa: E402
from app.database import apply_migrations  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision one internal console account.")
    parser.add_argument("--phone", required=True)
    parser.add_argument("--initial-password", default="123456")
    parser.add_argument(
        "--reset-existing",
        action="store_true",
        help="Reset an existing account to must-change-password state and revoke sessions.",
    )
    args = parser.parse_args()

    settings = Settings.from_environment()
    apply_migrations(settings.database_path, settings.console_root / "migrations")
    try:
        action = provision_user(
            settings.database_path,
            args.phone,
            args.initial_password,
            reset_existing=args.reset_existing,
        )
    except ValueError as exc:
        print(f"Provisioning failed: {exc}", file=sys.stderr)
        return 2
    print(f"Internal user {action}. First-login password change is required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
