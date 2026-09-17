from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    repo_root: Path
    console_root: Path
    pipeline_root: Path
    database_path: Path
    python_executable: str
    pipeline_python_executable: str | None = None
    session_cookie_name: str = "aivo_session"
    session_hours: int = 12
    secure_cookies: bool = False
    status_timeout_seconds: int = 30
    case_analysis_worker_enabled: bool = True
    customer_analysis_worker_enabled: bool = True
    default_business_id: str = "shufang_zhiyuan_community_canteen"

    @classmethod
    def from_environment(cls) -> "Settings":
        console_root = Path(__file__).resolve().parents[1]
        repo_root = console_root.parent
        database_path = Path(
            os.environ.get("AIVO_CONSOLE_DB", console_root / "var" / "console.sqlite3")
        ).resolve()
        return cls(
            repo_root=repo_root,
            console_root=console_root,
            pipeline_root=repo_root / "ops-pipeline",
            database_path=database_path,
            python_executable=sys.executable,
            pipeline_python_executable=os.environ.get(
                "AIVO_PIPELINE_PYTHON",
                str(repo_root / "ops-pipeline" / ".venv" / "Scripts" / "python.exe"),
            ),
            session_cookie_name=os.environ.get("AIVO_SESSION_COOKIE", "aivo_session"),
            session_hours=int(os.environ.get("AIVO_SESSION_HOURS", "12")),
            secure_cookies=os.environ.get("AIVO_SECURE_COOKIES", "0") == "1",
            status_timeout_seconds=int(
                os.environ.get("AIVO_STATUS_TIMEOUT_SECONDS", "30")
            ),
            case_analysis_worker_enabled=(
                os.environ.get("AIVO_CASE_ANALYSIS_WORKER", "1") == "1"
            ),
            customer_analysis_worker_enabled=(
                os.environ.get(
                    "AIVO_CUSTOMER_ANALYSIS_WORKER",
                    "1",
                )
                == "1"
            ),
            default_business_id=os.environ.get(
                "AIVO_DEFAULT_BUSINESS_ID", "shufang_zhiyuan_community_canteen"
            ),
        )
