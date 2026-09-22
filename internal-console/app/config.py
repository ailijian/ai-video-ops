from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def _load_environment_file() -> None:
    path_value = os.environ.get("AIVO_ENV_FILE")
    if not path_value:
        return
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise RuntimeError(f"AIVO_ENV_FILE does not exist: {path}")
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "a").isalnum():
            raise RuntimeError(f"Invalid environment key in AIVO_ENV_FILE: {key!r}")
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


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
    speaker_analysis_worker_enabled: bool = True
    background_worker_enabled: bool = False
    task_queue_max: int = 20
    gpu_pending_per_user_max: int = 3
    task_lease_seconds: int = 120
    task_heartbeat_seconds: int = 10
    storage_maintenance_interval_seconds: int = 3600
    session_last_seen_interval_seconds: int = 300
    default_business_id: str | None = None
    case_acquisition_provider: str = "legacy_downloader"
    novel_news_rollout: str = "off"
    novel_news_validation_phones: tuple[str, ...] = ()

    @classmethod
    def from_environment(cls) -> "Settings":
        _load_environment_file()
        acquisition_provider = os.environ.get(
            "AIVO_CASE_ACQUISITION_PROVIDER", "legacy_downloader"
        ).strip()
        if acquisition_provider not in {"legacy_downloader", "qiyun", "upload_only"}:
            raise ValueError("AIVO_CASE_ACQUISITION_PROVIDER must be legacy_downloader, qiyun or upload_only")
        novel_news_rollout = os.environ.get("AIVO_NOVEL_NEWS_ROLLOUT", "off").strip().lower()
        if novel_news_rollout not in {"off", "validation", "on"}:
            raise ValueError("AIVO_NOVEL_NEWS_ROLLOUT must be off, validation or on")
        validation_phones = tuple(
            sorted({phone.strip() for phone in os.environ.get("AIVO_NOVEL_NEWS_VALIDATION_PHONES", "").split(",") if phone.strip()})
        )
        if novel_news_rollout == "validation" and not validation_phones:
            raise ValueError("AIVO_NOVEL_NEWS_VALIDATION_PHONES is required for validation mode")
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
            speaker_analysis_worker_enabled=(
                os.environ.get(
                    "AIVO_SPEAKER_ANALYSIS_WORKER",
                    "1",
                )
                == "1"
            ),
            background_worker_enabled=(
                os.environ.get("AIVO_BACKGROUND_WORKER", "1") == "1"
            ),
            task_queue_max=max(1, int(os.environ.get("AIVO_TASK_QUEUE_MAX", "20"))),
            gpu_pending_per_user_max=max(
                1,
                int(os.environ.get("AIVO_GPU_PENDING_PER_USER_MAX", "3")),
            ),
            task_lease_seconds=max(
                30, int(os.environ.get("AIVO_TASK_LEASE_SECONDS", "120"))
            ),
            task_heartbeat_seconds=max(
                5, int(os.environ.get("AIVO_TASK_HEARTBEAT_SECONDS", "10"))
            ),
            storage_maintenance_interval_seconds=max(
                60,
                int(
                    os.environ.get(
                        "AIVO_STORAGE_MAINTENANCE_INTERVAL_SECONDS",
                        "3600",
                    )
                ),
            ),
            session_last_seen_interval_seconds=max(
                60,
                int(os.environ.get("AIVO_SESSION_LAST_SEEN_INTERVAL_SECONDS", "300")),
            ),
            default_business_id=(
                os.environ.get("AIVO_DEFAULT_BUSINESS_ID", "").strip() or None
            ),
            case_acquisition_provider=acquisition_provider,
            novel_news_rollout=novel_news_rollout,
            novel_news_validation_phones=validation_phones,
        )
