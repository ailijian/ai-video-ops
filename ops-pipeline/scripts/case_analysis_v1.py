from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit
from case_duplicate_guard_v1 import find_media_identity_duplicate
from storage_retention_v1 import (
    FAILED_RETENTION,
    cleanup_successful_attempt,
    mark_cleanup_retry_required,
    parse_utc,
)
from operation_lock_v1 import OperationLockTimeout, operation_lock
from speech_evidence_v1 import (
    SPEECH_NOT_DETECTED,
    SPEECH_UNCERTAIN,
    classify_transcription_speech_evidence,
    require_audio_speech_evidence,
)
from qiyun_acquisition_v1 import QiyunAcquisitionError, acquire_qiyun_media


OPERATION_VERSION = "case_analysis_v1.py@1.0"
SCHEMA_VERSION = "case-analysis-attempt-v1.0"
DEFAULT_WHISPER_MODEL = "large-v3"
CASE_ID_RE = re.compile(r"(?:/video/|video_id=)(\d{10,24})")
ATTEMPT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{7,127}$")
ALLOWED_HOSTS = {
    "douyin.com",
    "www.douyin.com",
    "iesdouyin.com",
    "www.iesdouyin.com",
}

STAGES = (
    ("acquire", "获取视频", 12),
    ("transcribe", "提取语音", 32),
    ("visual", "分析画面", 58),
    ("structure", "理解内容结构", 84),
    ("review", "生成审核结果", 100),
)


class CaseAnalysisError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def resolve_whisper_model() -> str:
    configured = os.environ.get("AIVO_WHISPER_MODEL", "").strip()
    if not configured:
        return DEFAULT_WHISPER_MODEL

    candidate = Path(configured).expanduser()
    if candidate.is_absolute() and not candidate.is_dir():
        raise CaseAnalysisError(
            "WHISPER_MODEL_PATH_INVALID",
            "AIVO_WHISPER_MODEL absolute path must be an existing local directory.",
        )
    return configured


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CaseAnalysisError("INVALID_ARTIFACT", f"Expected a JSON object: {path}")
    return value


def write_atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def stable_source_identity(source_url: str) -> tuple[str, str]:
    raw = source_url.strip()
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    if parts.scheme not in {"http", "https"} or host not in ALLOWED_HOSTS:
        raise CaseAnalysisError(
            "UNSUPPORTED_SOURCE",
            "case_analysis_v1 currently accepts full Douyin video URLs only.",
        )
    match = CASE_ID_RE.search(raw)
    if match is None:
        raise CaseAnalysisError(
            "SOURCE_IDENTITY_UNRESOLVED",
            "Use the full Douyin video URL so a stable source identity can be verified.",
        )
    case_id = match.group(1)
    return case_id, f"https://www.douyin.com/video/{case_id}"


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def find_local_source(downloader_root: Path, case_id: str) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []
    for metadata_path in downloader_root.glob(f"Downloaded/**/*{case_id}*_data.json"):
        try:
            metadata = read_json(metadata_path)
        except (OSError, json.JSONDecodeError, CaseAnalysisError):
            continue
        if str(metadata.get("aweme_id") or "") != case_id:
            continue
        videos = sorted(metadata_path.parent.glob(f"*{case_id}*.mp4"))
        if len(videos) != 1:
            continue
        video = videos[0].resolve()
        matches.append(
            {
                "video": str(video),
                "metadata": str(metadata_path.resolve()),
                "cover": next(
                    (str(path.resolve()) for path in metadata_path.parent.glob(f"*{case_id}*_cover.*")),
                    None,
                ),
                "music": next(
                    (str(path.resolve()) for path in metadata_path.parent.glob(f"*{case_id}*_music.*")),
                    None,
                ),
                "source_description": str(metadata.get("desc") or ""),
                "source_author": str((metadata.get("author") or {}).get("nickname") or ""),
            }
        )
    unique = {item["video"]: item for item in matches}
    if len(unique) > 1:
        raise CaseAnalysisError(
            "SOURCE_ACQUISITION_AMBIGUOUS",
            f"Multiple local source videos match stable case identity {case_id}.",
        )
    return next(iter(unique.values()), None)


def validate_json(
    path: Path,
    validator: Callable[[dict[str, Any]], bool],
) -> bool:
    try:
        return path.is_file() and validator(read_json(path))
    except (OSError, json.JSONDecodeError, CaseAnalysisError, TypeError, ValueError):
        return False


class Orchestrator:
    def __init__(
        self,
        *,
        pipeline_root: Path,
        repo_root: Path,
        downloader_root: Path,
        source_url: str,
        attempt_id: str,
        profile: str | None,
        industry: str,
        reanalyze: bool,
        operator_profile_hint: str | None = None,
        source_upload_id: str | None = None,
        source_upload_receipt_sha256: str | None = None,
        acquisition_provider: str = "legacy_downloader",
        provider_source_url: str | None = None,
    ) -> None:
        if not ATTEMPT_ID_RE.fullmatch(attempt_id):
            raise CaseAnalysisError("INVALID_ATTEMPT_ID", "Attempt ID is invalid.")
        self.pipeline_root = pipeline_root.resolve()
        self.repo_root = repo_root.resolve()
        self.downloader_root = downloader_root.resolve()
        self.case_id, self.source_url = stable_source_identity(source_url)
        self.attempt_id = attempt_id
        self.profile = profile
        self.operator_profile_hint = operator_profile_hint
        self.source_upload_id = source_upload_id
        self.source_upload_receipt_sha256 = source_upload_receipt_sha256
        if acquisition_provider not in {"legacy_downloader", "qiyun", "upload_only"}:
            raise CaseAnalysisError("SOURCE_PROVIDER_INVALID", "Unsupported acquisition provider.")
        self.acquisition_provider = acquisition_provider
        self.provider_source_url = provider_source_url
        if bool(source_upload_id) != bool(source_upload_receipt_sha256):
            raise CaseAnalysisError("SOURCE_UPLOAD_INVALID", "Upload receipt checksum is required.")
        if bool(profile) == bool(operator_profile_hint):
            raise CaseAnalysisError(
                "CASE_PROFILE_INPUT_INVALID",
                "Provide exactly one legacy profile or operator profile hint.",
            )
        if operator_profile_hint and operator_profile_hint not in {"mix", "news", "hybrid", "uncertain"}:
            raise CaseAnalysisError("CASE_OPERATOR_PROFILE_HINT_INVALID", "Operator profile hint is invalid.")
        self.industry = industry
        self.reanalyze = reanalyze
        self.whisper_model = resolve_whisper_model()
        self.attempt_root = (
            self.pipeline_root
            / "data"
            / "case_analysis_attempts"
            / self.case_id
            / self.attempt_id
        )
        self.state_path = self.attempt_root / "case_analysis_attempt_v1.json"
        self.logs_root = self.attempt_root / "logs"
        self.python = Path(sys.executable).resolve()
        edge_secret_prefixes = (
            "FRP_",
            "FRPC_",
            "FRPS_",
            "AIVO_FRP_",
            "AIVO_FRPC_",
            "AIVO_FRPS_",
        )
        self.child_env = {
            key: value
            for key, value in os.environ.items()
            if not key.upper().startswith(edge_secret_prefixes)
        }
        self.child_env.pop("DEEPSEEK_API_KEY", None)
        self.child_env.pop("QYAPI_APP_ID", None)
        self.child_env.pop("QYAPI_APP_KEY", None)
        self.child_env["PYTHONIOENCODING"] = "utf-8"
        self.child_env["PYTHONUTF8"] = "1"
        self.deepseek_env = self.child_env.copy()
        for key, value in load_dotenv(self.pipeline_root / ".env").items():
            if key.upper().startswith(edge_secret_prefixes):
                continue
            if key in {"QYAPI_APP_ID", "QYAPI_APP_KEY"}:
                continue
            if key.startswith("DEEPSEEK_"):
                self.deepseek_env.setdefault(key, value)
            else:
                self.child_env.setdefault(key, value)
                self.deepseek_env.setdefault(key, value)
        self.state = self._load_or_initialize()

    def _load_or_initialize(self) -> dict[str, Any]:
        if self.state_path.is_file():
            state = read_json(self.state_path)
            if (
                state.get("schema_version") != SCHEMA_VERSION
                or state.get("attempt_id") != self.attempt_id
                or state.get("case_id") != self.case_id
                or state.get("source", {}).get("canonical_url") != self.source_url
                or state.get("request", {}).get("operator_profile_hint") != self.operator_profile_hint
                or state.get("request", {}).get("source_upload_id") != self.source_upload_id
                or state.get("request", {}).get("source_upload_receipt_sha256") != self.source_upload_receipt_sha256
                or state.get("request", {}).get("acquisition_provider", "legacy_downloader") != self.acquisition_provider
                or state.get("request", {}).get("provider_source_url") != self.provider_source_url
            ):
                raise CaseAnalysisError(
                    "ATTEMPT_IDENTITY_MISMATCH",
                    "Existing attempt lineage does not match this source request.",
                )
            return state

        canonical_case = self.pipeline_root / "data" / "cases" / self.case_id / "case_v1.json"
        if canonical_case.exists() and not self.reanalyze:
            raise CaseAnalysisError(
                "DUPLICATE_CASE",
                f"Case {self.case_id} already has a canonical Case artifact.",
            )
        case_attempts_root = (
            self.pipeline_root / "data" / "case_analysis_attempts" / self.case_id
        )
        if not self.reanalyze:
            for other_path in case_attempts_root.glob("*/case_analysis_attempt_v1.json"):
                if other_path.parent.name == self.attempt_id:
                    continue
                try:
                    other = read_json(other_path)
                except (OSError, json.JSONDecodeError, CaseAnalysisError):
                    continue
                if other.get("status") in {"queued", "running", "awaiting_review"}:
                    raise CaseAnalysisError(
                        "DUPLICATE_CASE_ATTEMPT",
                        f"Case {self.case_id} already has an active or review-ready analysis attempt.",
                    )
        previous_attempts: list[tuple[str, str]] = []
        for previous_path in case_attempts_root.glob("*/case_analysis_attempt_v1.json"):
            if previous_path.parent.name == self.attempt_id:
                continue
            try:
                previous_state = read_json(previous_path)
            except (OSError, json.JSONDecodeError, CaseAnalysisError):
                continue
            previous_attempts.append(
                (
                    str(previous_state.get("created_at") or ""),
                    str(previous_state.get("attempt_id") or previous_path.parent.name),
                )
            )
        previous_attempts.sort()
        state: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "operation_version": OPERATION_VERSION,
            "attempt_id": self.attempt_id,
            "case_id": self.case_id,
            "source": {
                "input_url": self.source_url,
                "canonical_url": self.source_url,
                "platform": "douyin",
            },
            "request": {
                "industry": self.industry,
                "reanalyze": self.reanalyze,
                "acquisition_provider": self.acquisition_provider,
            },
            "lineage": {
                "previous_attempt_id": previous_attempts[-1][1] if previous_attempts else None,
                "canonical_case_existed_at_start": canonical_case.exists(),
                "canonical_case_sha256_at_start": (
                    sha256_file(canonical_case) if canonical_case.is_file() else None
                ),
            },
            "status": "queued",
            "progress": 0,
            "current_stage": "queued",
            "stages": [
                {"id": stage_id, "label": label, "status": "pending", "progress": progress}
                for stage_id, label, progress in STAGES
            ],
            "artifacts": {},
            "model_calls": [],
            "error": None,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        if self.profile:
            state["request"]["profile"] = self.profile
        if self.operator_profile_hint:
            state["request"]["operator_profile_hint"] = self.operator_profile_hint
        if self.source_upload_id:
            state["request"]["source_upload_id"] = self.source_upload_id
            state["request"]["source_upload_receipt_sha256"] = self.source_upload_receipt_sha256
        if self.provider_source_url:
            state["request"]["provider_source_url"] = self.provider_source_url
        write_atomic_json(self.state_path, state)
        return state

    def save(self) -> None:
        self.state["updated_at"] = now_iso()
        write_atomic_json(self.state_path, self.state)

    def stage_record(self, stage_id: str) -> dict[str, Any]:
        return next(item for item in self.state["stages"] if item["id"] == stage_id)

    def start_stage(self, stage_id: str) -> None:
        stage = self.stage_record(stage_id)
        stage["status"] = "running"
        stage["started_at"] = stage.get("started_at") or now_iso()
        self.state["status"] = "running"
        self.state["current_stage"] = stage_id
        self.state["progress"] = max(int(self.state.get("progress") or 0), 0, int(stage["progress"]) - 10)
        self.state["error"] = None
        self.save()

    def complete_stage(self, stage_id: str, *, recovered: bool = False) -> None:
        stage = self.stage_record(stage_id)
        stage["status"] = "completed"
        stage["completed_at"] = now_iso()
        stage["recovered_from_checkpoint"] = recovered
        self.state["progress"] = max(int(self.state.get("progress") or 0), int(stage["progress"]))
        self.save()

    def run_command(
        self,
        label: str,
        command: list[str],
        stage_id: str,
        timeout: int,
        *,
        needs_deepseek: bool = False,
    ) -> None:
        self.logs_root.mkdir(parents=True, exist_ok=True)
        log_path = self.logs_root / f"{stage_id}-{label}.log"
        result = subprocess.run(
            command,
            cwd=self.repo_root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=self.deepseek_env if needs_deepseek else self.child_env,
            timeout=timeout,
            check=False,
        )
        log_path.write_text(
            f"COMMAND: {json.dumps(command, ensure_ascii=False)}\n"
            f"RETURN_CODE: {result.returncode}\n\nSTDOUT\n{result.stdout}\n\nSTDERR\n{result.stderr}",
            encoding="utf-8",
        )
        if result.returncode != 0:
            tail = (result.stderr or result.stdout).strip().splitlines()[-1:]
            reason = tail[0] if tail else f"exit code {result.returncode}"
            raise CaseAnalysisError(
                "PIPELINE_STAGE_FAILED",
                f"{label} failed: {reason}",
            )

    def reuse_failed_qiyun_media(self) -> dict[str, Any] | None:
        """Copy verified media from a failed attempt before making another paid call."""

        candidates: list[tuple[datetime, Path]] = []
        now = datetime.now(timezone.utc)
        for state_path in self.attempt_root.parent.glob("*/case_analysis_attempt_v1.json"):
            previous_root = state_path.parent
            if previous_root == self.attempt_root or previous_root.is_symlink():
                continue
            try:
                state = read_json(state_path)
                terminal_at = parse_utc(str(state.get("updated_at") or ""))
            except (OSError, ValueError, TypeError, json.JSONDecodeError, CaseAnalysisError):
                continue
            if (
                state.get("status") != "failed"
                or state.get("case_id") != self.case_id
                or state.get("attempt_id") != previous_root.name
                or (state.get("source") or {}).get("canonical_url") != self.source_url
                or (state.get("request") or {}).get("acquisition_provider") != "qiyun"
                or state.get("cleanup_status") == "completed"
                or terminal_at is None
                or not timedelta(0) <= now - terminal_at < FAILED_RETENTION
            ):
                continue
            candidates.append((terminal_at, previous_root))

        for _, previous_root in sorted(candidates, key=lambda item: (item[0], item[1].name), reverse=True):
            lock_key = f"storage_cleanup:{self.case_id}:{previous_root.name}"
            try:
                with operation_lock(self.pipeline_root, lock_key, timeout_seconds=30):
                    video = previous_root / "source_media" / "source.mp4"
                    metadata_path = previous_root / "source_metadata_v1.json"
                    if video.is_symlink() or metadata_path.is_symlink():
                        continue
                    try:
                        state = read_json(previous_root / "case_analysis_attempt_v1.json")
                        acquisition = read_json(previous_root / "source_acquisition_v1.json")
                        metadata = read_json(metadata_path)
                        terminal_at = parse_utc(str(state.get("updated_at") or ""))
                    except (OSError, ValueError, TypeError, json.JSONDecodeError, CaseAnalysisError):
                        continue
                    if (
                        state.get("status") != "failed"
                        or state.get("case_id") != self.case_id
                        or state.get("attempt_id") != previous_root.name
                        or (state.get("source") or {}).get("canonical_url") != self.source_url
                        or (state.get("request") or {}).get("acquisition_provider") != "qiyun"
                        or state.get("cleanup_status") == "completed"
                        or terminal_at is None
                        or not timedelta(0) <= datetime.now(timezone.utc) - terminal_at < FAILED_RETENTION
                    ):
                        continue
                    recorded_sha = str(acquisition.get("source_video_sha256") or "").lower()
                    if (
                        acquisition.get("mode") != "qiyun_resolved_media"
                        or acquisition.get("case_id") != self.case_id
                        or acquisition.get("stable_video_id") != self.case_id
                        or acquisition.get("source_url") != self.source_url
                        or acquisition.get("platform") != "douyin"
                        or Path(str(acquisition.get("video") or "")).resolve() != video.resolve()
                        or Path(str(acquisition.get("metadata") or "")).resolve()
                        != metadata_path.resolve()
                        or metadata.get("provider") != "qiyun"
                        or metadata.get("stable_video_id") != self.case_id
                        or metadata.get("canonical_source_url") != self.source_url
                        or re.fullmatch(r"[0-9a-f]{64}", recorded_sha) is None
                        or not video.is_file()
                    ):
                        continue
                    try:
                        if sha256_file(video) != recorded_sha:
                            continue
                    except OSError:
                        continue
                    destination = self.attempt_root / "source_media" / "source.mp4"
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    partial = destination.with_suffix(".mp4.part")
                    try:
                        shutil.copyfile(video, partial)
                        if sha256_file(partial) != recorded_sha:
                            raise CaseAnalysisError("SOURCE_MEDIA_REUSE_INVALID", "Previously acquired video failed verification.")
                        os.replace(partial, destination)
                    except OSError as exc:
                        raise CaseAnalysisError("SOURCE_MEDIA_REUSE_FAILED", "Previously acquired video could not be copied.") from exc
                    finally:
                        partial.unlink(missing_ok=True)
                    return {
                        "video": str(destination),
                        "source_video_sha256": recorded_sha,
                        "source_description": str(acquisition.get("source_description") or ""),
                        "source_author": str(acquisition.get("source_author") or ""),
                        "metadata": metadata,
                        "reused_from_attempt_id": previous_root.name,
                    }
            except OperationLockTimeout as exc:
                raise CaseAnalysisError(
                    "SOURCE_MEDIA_REUSE_BUSY", "Previously acquired video is being maintained; retry shortly."
                ) from exc
        return None

    def acquire(self) -> dict[str, Any]:
        acquisition_path = self.attempt_root / "source_acquisition_v1.json"
        if self.source_upload_id:
            # An explicit upload never falls back to downloading a different file.
            from case_source_upload_v1 import read_upload
            try:
                receipt, video = read_upload(
                    self.pipeline_root, self.source_upload_id, source_url=self.source_url,
                    receipt_sha256=self.source_upload_receipt_sha256,
                )
            except (OSError, ValueError, TypeError) as exc:
                raise CaseAnalysisError("SOURCE_UPLOAD_INVALID", "上传文件已失效，请重新上传后分析。") from exc
            metadata = self.attempt_root / "source_metadata_v1.json"
            write_atomic_json(metadata, receipt)
            acquisition = {
                "schema_version": "case-source-acquisition-v1.0", "case_id": self.case_id,
                "stable_video_id": self.case_id, "source_url": self.source_url, "platform": "douyin",
                "mode": "operator_uploaded_file", "upload_id": self.source_upload_id,
                "upload_receipt_sha256": self.source_upload_receipt_sha256,
                "video": str(video), "metadata": str(metadata), "cover": None, "music": None,
                "source_description": "", "source_author": "",
                "source_video_sha256": receipt["source_video_sha256"],
                "binding_method": "operator_attestation", "platform_original_verified": False,
                "media_rights_granted": False, "production_footage_pool_eligible": False,
                "created_at": now_iso(),
            }
            write_atomic_json(acquisition_path, acquisition)
            return acquisition
        if self.acquisition_provider == "upload_only":
            raise CaseAnalysisError("SOURCE_UPLOAD_REQUIRED", "请上传与来源链接对应的视频文件。")
        if validate_json(
            acquisition_path,
            lambda value: (
                value.get("case_id") == self.case_id
                and Path(str(value.get("video") or "")).is_file()
                and value.get("source_video_sha256")
                == sha256_file(Path(str(value["video"])))
            ),
        ):
            return read_json(acquisition_path)

        if self.acquisition_provider == "qiyun":
            acquired = self.reuse_failed_qiyun_media()
            if acquired is None:
                try:
                    acquired = acquire_qiyun_media(
                        pipeline_root=self.pipeline_root, source_url=self.source_url,
                        case_id=self.case_id, attempt_root=self.attempt_root,
                        provider_source_url=self.provider_source_url,
                    )
                except QiyunAcquisitionError as exc:
                    raise CaseAnalysisError(exc.code, str(exc)) from None
            metadata_path = self.attempt_root / "source_metadata_v1.json"
            write_atomic_json(metadata_path, acquired["metadata"])
            acquisition = {
                "schema_version": "case-source-acquisition-v1.0", "case_id": self.case_id,
                "stable_video_id": self.case_id, "source_url": self.source_url,
                "platform": "douyin", "mode": "qiyun_resolved_media",
                "video": acquired["video"], "metadata": str(metadata_path),
                "cover": None, "music": None,
                "source_description": acquired["source_description"],
                "source_author": acquired["source_author"],
                "source_video_sha256": acquired["source_video_sha256"],
                "provider_api_called_this_attempt": "reused_from_attempt_id" not in acquired,
                "reused_from_attempt_id": acquired.get("reused_from_attempt_id"),
                "binding_method": "canonical_douyin_url_and_recorded_media_sha256",
                "platform_original_verified": False,
                "media_rights_granted": False, "production_footage_pool_eligible": False,
                "created_at": now_iso(),
            }
            write_atomic_json(acquisition_path, acquisition)
            return acquisition

        source = find_local_source(self.downloader_root, self.case_id)
        acquisition_mode = "reused_verified_local_source"
        if source is None:
            downloader_python = self.downloader_root / ".venv" / "Scripts" / "python.exe"
            if not downloader_python.is_file():
                raise CaseAnalysisError(
                    "SOURCE_ACQUISITION_UNAVAILABLE",
                    "The approved downloader runtime is unavailable.",
                )
            self.run_command(
                "download-source",
                [str(downloader_python), str(self.downloader_root / "run.py"), "-u", self.source_url],
                "acquire",
                600,
            )
            source = find_local_source(self.downloader_root, self.case_id)
            acquisition_mode = "downloaded_from_canonical_source_url"
        if source is None:
            raise CaseAnalysisError(
                "SOURCE_ACQUISITION_FAILED",
                "The downloader completed without a uniquely traceable source video.",
            )
        video = Path(source["video"])
        source_metadata = Path(str(source["metadata"]))
        metadata_snapshot = self.attempt_root / "source_metadata_v1.json"
        write_atomic_json(metadata_snapshot, read_json(source_metadata))
        source = {
            **source,
            "metadata": str(metadata_snapshot),
            "downloader_metadata": str(source_metadata),
        }
        acquisition = {
            "schema_version": "case-source-acquisition-v1.0",
            "case_id": self.case_id,
            "stable_video_id": self.case_id,
            "source_url": self.source_url,
            "platform": "douyin",
            "mode": acquisition_mode,
            **source,
            "source_video_sha256": sha256_file(video),
            "media_rights_granted": False,
            "production_footage_pool_eligible": False,
            "created_at": now_iso(),
        }
        write_atomic_json(acquisition_path, acquisition)
        return acquisition

    def run(self) -> dict[str, Any]:
        try:
            acquisition_path = self.attempt_root / "source_acquisition_v1.json"
            self.start_stage("acquire")
            recovered = validate_json(
                acquisition_path,
                lambda value: value.get("case_id") == self.case_id
                and Path(str(value.get("video") or "")).is_file(),
            )
            source = self.acquire()
            self.state["artifacts"]["source_acquisition_v1"] = str(acquisition_path)
            recovered = recovered or bool(source.get("reused_from_attempt_id"))

            media_duplicate = find_media_identity_duplicate(
                self.pipeline_root,
                current_case_id=self.case_id,
                current_attempt_id=self.attempt_id,
                media_sha256=str(source.get("source_video_sha256") or ""),
            )

            if media_duplicate is not None:
                self.state["duplicate"] = media_duplicate
                self.save()

                raise CaseAnalysisError(
                    "MEDIA_DUPLICATE_CASE",
                    (
                        "The acquired video is byte-identical to an existing Case source: "
                        f"{media_duplicate['existing_case_id']}."
                    ),
                )

            self.complete_stage("acquire", recovered=recovered)

            video = Path(source["video"])
            transcription_root = self.attempt_root / "evidence" / "transcription"
            transcript_dir = transcription_root / video.stem
            transcript_segments = transcript_dir / "transcript_segments.json"
            audio_root = self.attempt_root / "evidence" / "audio_v1"
            audio_v1 = audio_root / "audio_word_timeline_v1.json"
            self.start_stage("transcribe")
            transcribe_valid = validate_json(
                transcript_segments,
                lambda value: (
                    value.get("source_file") == str(video)
                    and classify_transcription_speech_evidence(value)
                    != SPEECH_UNCERTAIN
                ),
            )
            source_caption = str(source.get("source_description") or "").strip()
            if not transcribe_valid:
                transcribe_command = [
                    str(self.python),
                    str(self.pipeline_root / "scripts" / "transcribe_case.py"),
                    "--input",
                    str(video),
                    "--model",
                    self.whisper_model,
                    "--language",
                    "zh",
                    "--device",
                    "cpu",
                    "--output-root",
                    str(transcription_root),
                    "--filter-implausible-segments",
                ]
                if source_caption:
                    transcribe_command.extend(["--initial-prompt", source_caption[:1000]])
                self.run_command(
                    "transcribe",
                    transcribe_command,
                    "transcribe",
                    1800,
                )
            audio_valid = validate_json(
                audio_v1,
                lambda value: value.get("case_id") == self.case_id
                and value.get("validation", {}).get("passed") is True,
            )
            if not audio_valid:
                self.run_command(
                    "audio-timeline",
                    [
                        str(self.python),
                        str(self.pipeline_root / "scripts" / "build_audio_word_timeline_v1.py"),
                        "--case-id",
                        self.case_id,
                        "--audio",
                        str(transcript_segments),
                        "--output-root",
                        str(audio_root),
                    ],
                    "transcribe",
                    300,
                )
            audio_data = read_json(audio_v1)
            speech_evidence_status = require_audio_speech_evidence(audio_data)
            self.state["speech_evidence_status"] = speech_evidence_status
            if speech_evidence_status == SPEECH_NOT_DETECTED:
                self.state.setdefault("model_call_accounting", {})[
                    "narration_remote_calls"
                ] = 0
            self.state["model_calls"].append(
                {
                    "stage": "transcribe",
                    "model": f"faster-whisper/{self.whisper_model}",
                    "boundary": "local_transcription",
                    "source_caption_hint": bool(source_caption),
                    "deterministic_timing_guard": True,
                    "cache_reused": transcribe_valid,
                    "speech_evidence_status": speech_evidence_status,
                }
            )
            self.state["artifacts"]["transcript_segments"] = str(
                transcript_segments
            )
            self.state["artifacts"]["audio_v1"] = str(audio_v1)
            self.complete_stage("transcribe", recovered=transcribe_valid and audio_valid)

            visual_root = self.attempt_root / "evidence" / "visual"
            manifest = visual_root / self.case_id / "visual_evidence_manifest.json"
            visual_v1 = visual_root / self.case_id / "visual_v1" / "visual_timeline_v1.json"
            privacy_root = self.attempt_root / "evidence" / "privacy"
            privacy = privacy_root / "privacy_projection_v1.json"
            self.start_stage("visual")
            extract_valid = validate_json(
                manifest,
                lambda value: value.get("case_id") == self.case_id
                and bool(value.get("frames")),
            )
            if not extract_valid:
                self.run_command(
                    "extract-visual",
                    [
                        str(self.python),
                        str(self.pipeline_root / "scripts" / "extract_visual_evidence.py"),
                        "--input",
                        str(video),
                        "--case-id",
                        self.case_id,
                        "--output-root",
                        str(visual_root),
                    ],
                    "visual",
                    600,
                )
            visual_valid = validate_json(
                visual_v1,
                lambda value: value.get("case_id") == self.case_id
                and value.get("coverage", {}).get("coverage_label") == "candidate_complete",
            )
            if not visual_valid:
                self.run_command(
                    "analyze-visual",
                    [
                        str(self.python),
                        str(self.pipeline_root / "scripts" / "analyze_visual_timeline_v1.py"),
                        "--manifest",
                        str(manifest),
                        "--model",
                        "qwen3-vl:4b-instruct",
                        "--chunk-size",
                        "6",
                        "--num-ctx",
                        "16384",
                        "--max-image-edge",
                        "960",
                    ],
                    "visual",
                    3600,
                )
            privacy_valid = validate_json(
                privacy,
                lambda value: value.get("case_id") == self.case_id
                and value.get("privacy_policy_version") == "privacy-policy-v1.0",
            )
            if not privacy_valid:
                self.run_command(
                    "privacy-projection",
                    [
                        str(self.python),
                        str(self.pipeline_root / "scripts" / "build_privacy_projection_v1.py"),
                        "--case-id",
                        self.case_id,
                        "--visual-v1",
                        str(visual_v1),
                        "--audio-v1",
                        str(audio_v1),
                        "--output-root",
                        str(privacy_root),
                    ],
                    "visual",
                    300,
                )
            self.state["model_calls"].append(
                {
                    "stage": "visual",
                    "model": "qwen3-vl:4b-instruct",
                    "boundary": "local_visual_evidence_interpretation",
                    "cache_reused": visual_valid,
                }
            )
            self.state["artifacts"].update(
                {
                    "visual_manifest": str(manifest),
                    "visual_v1": str(visual_v1),
                    "privacy_projection_v1": str(privacy),
                }
            )
            self.complete_stage(
                "visual",
                recovered=extract_valid and visual_valid and privacy_valid,
            )

            narration_root = self.attempt_root / "evidence" / "narration"
            narration = narration_root / "narration_review_v1.json"
            shots_root = self.attempt_root / "evidence" / "shots"
            shots = shots_root / "shot_boundaries_v1_1.json"
            boundary_reviews = sorted(shots_root.glob("boundary_review_???.json"))
            boundary_review = boundary_reviews[-1] if boundary_reviews else None
            storyboard_root = self.attempt_root / "evidence" / "storyboard"
            storyboard = storyboard_root / "reverse_storyboard_v1.json"
            self.start_stage("structure")
            narration_valid = validate_json(
                narration,
                lambda value: value.get("case_id") == self.case_id
                and value.get("manual_review", {}).get("required") is False,
            )
            if not narration_valid:
                self.run_command(
                    "narration-review",
                    [
                        str(self.python),
                        str(self.pipeline_root / "scripts" / "build_narration_review_v1.py"),
                        "--case-id",
                        self.case_id,
                        "--audio-v1",
                        str(audio_v1),
                        "--visual-v1",
                        str(visual_v1),
                        "--privacy-projection",
                        str(privacy),
                        "--output-root",
                        str(narration_root),
                    ],
                    "structure",
                    1800,
                    needs_deepseek=(
                        speech_evidence_status != SPEECH_NOT_DETECTED
                    ),
                )
            shot_valid = validate_json(
                shots,
                lambda value: value.get("case_id") == self.case_id
                and value.get("validation", {}).get("passed") is True
                and value.get("manual_review", {}).get("required") is False,
            )
            if not shot_valid:
                shot_command = [
                    str(self.python),
                    str(self.pipeline_root / "scripts" / "build_shot_boundaries_v1.py"),
                    "--case-id",
                    self.case_id,
                    "--visual-v1",
                    str(visual_v1),
                    "--visual-manifest",
                    str(manifest),
                    "--audio-v1",
                    str(audio_v1),
                    "--privacy-projection",
                    str(privacy),
                    "--output-root",
                    str(shots_root),
                ]
                if boundary_review is not None and boundary_review.is_file():
                    shot_command.extend(["--review-file", str(boundary_review)])
                self.run_command(
                    "shot-boundaries",
                    shot_command,
                    "structure",
                    1800,
                    needs_deepseek=True,
                )
            if read_json(shots).get("manual_review", {}).get("required") is True:
                raise CaseAnalysisError(
                    "SHOT_BOUNDARY_REVIEW_REQUIRED",
                    "Two or more adjacent shots need a human boundary decision before the Case can be built.",
                )
            storyboard_valid = validate_json(
                storyboard,
                lambda value: value.get("case_id") == self.case_id
                and value.get("validation", {}).get("passed") is True,
            )
            # A revised boundary projection invalidates the prior storyboard,
            # even when its own validation had passed against the old shots.
            if not storyboard_valid or not shot_valid:
                self.run_command(
                    "reverse-storyboard",
                    [
                        str(self.python),
                        str(self.pipeline_root / "scripts" / "generate_reverse_storyboard.py"),
                        "--shot-boundaries",
                        str(shots),
                        "--audio-v1",
                        str(audio_v1),
                        "--narration-review",
                        str(narration),
                        "--privacy-projection",
                        str(privacy),
                        "--output-root",
                        str(storyboard_root),
                    ],
                    "structure",
                    2400,
                    needs_deepseek=True,
                )
            model_boundaries = [
                ("privacy_safe_shot_boundary_selection", shot_valid),
                ("privacy_safe_reverse_storyboard", storyboard_valid),
            ]
            if speech_evidence_status != SPEECH_NOT_DETECTED:
                model_boundaries.insert(
                    0,
                    ("privacy_safe_narration_review", narration_valid),
                )
            for boundary, cache_reused in model_boundaries:
                self.state["model_calls"].append(
                    {
                        "stage": "structure",
                        "model": "deepseek-v4-flash",
                        "boundary": boundary,
                        "cache_reused": cache_reused,
                    }
                )
            self.state["artifacts"].update(
                {
                    "narration_review_v1": str(narration),
                    "shot_boundaries_v1": str(shots),
                    "reverse_storyboard_v1": str(storyboard),
                }
            )
            self.complete_stage(
                "structure",
                recovered=narration_valid and shot_valid and storyboard_valid,
            )

            candidate_root = self.attempt_root / "candidate_cases"
            candidate = candidate_root / self.case_id / "case_v1.json"
            self.start_stage("review")
            candidate_valid = validate_json(
                candidate,
                lambda value: value.get("case_id") == self.case_id
                and value.get("lifecycle", {}).get("status") == "review_required"
                and value.get("lifecycle", {}).get("approved") is False
                and value.get("validation", {}).get("auto_approved") is False,
            )
            if not candidate_valid:
                command = [
                    str(self.python),
                    str(self.pipeline_root / "scripts" / "build_case_v1.py"),
                    "--case-id",
                    self.case_id,
                    "--industry",
                    self.industry,
                    "--video",
                    str(video),
                    "--audio-v1",
                    str(audio_v1),
                    "--narration-review",
                    str(narration),
                    "--visual-manifest",
                    str(manifest),
                    "--visual-v1",
                    str(visual_v1),
                    "--shot-boundaries",
                    str(shots),
                    "--storyboard-v1",
                    str(storyboard),
                    "--privacy-projection",
                    str(privacy),
                    "--source-url",
                    self.source_url,
                    "--output-root",
                    str(candidate_root),
                ]
                if self.operator_profile_hint:
                    command.extend(["--operator-profile-hint", self.operator_profile_hint])
                else:
                    command.extend(["--profile", str(self.profile)])
                for option, key in (
                    ("--metadata", "metadata"),
                    ("--cover", "cover"),
                    ("--music", "music"),
                ):
                    if source.get(key):
                        command.extend([option, str(source[key])])
                self.run_command("build-case", command, "review", 600)
            case = read_json(candidate)
            case["analysis_lineage"] = {
                "operation": "case_analysis_v1",
                "attempt_id": self.attempt_id,
                "attempt_artifact": str(self.state_path),
                "previous_attempt_id": self.state["lineage"].get("previous_attempt_id"),
                "reanalysis": self.reanalyze,
            }
            case["source_governance"] = {
                "research_use_requires_explicit_human_approval": True,
                "media_reuse_rights": "not_established",
                "production_footage_pool_eligible": False,
            }
            case.setdefault("source_evidence", {}).setdefault("video", {})[
                "sha256"
            ] = str(source["source_video_sha256"])
            case["source_evidence"]["video"]["retention"] = (
                "transient_until_analysis_awaiting_review"
            )
            case["source_provenance"] = {
                "platform": "douyin",
                "acquisition_mode": source.get("mode"),
                "source_binding_method": source.get("binding_method", "recorded_acquisition_lineage"),
                "canonical_source_url": self.source_url,
                "stable_video_id": self.case_id,
                "recorded_source_media_sha256": str(
                    source["source_video_sha256"]
                ),
                "source_acquisition_ref": {
                    "path": str(acquisition_path),
                    "sha256": sha256_file(acquisition_path),
                },
                "source_metadata_ref": {
                    "path": str(source["metadata"]),
                    "sha256": sha256_file(Path(str(source["metadata"]))),
                },
                "semantics": "identity_and_acquisition_lineage_not_media_reuse_permission",
            }
            case.setdefault("source_artifacts", {})[
                "source_acquisition_v1"
            ] = str(acquisition_path)
            case["source_artifacts"]["source_metadata_v1"] = str(
                source["metadata"]
            )
            write_atomic_json(candidate, case)
            self.state["artifacts"]["case_candidate_v1"] = str(candidate)
            self.state["status"] = "awaiting_review"
            self.state["current_stage"] = "awaiting_review"
            self.complete_stage("review", recovered=candidate_valid)
            self.state["status"] = "awaiting_review"
            self.state["current_stage"] = "awaiting_review"
            self.state["progress"] = 100
            self.save()
            try:
                cleanup_successful_attempt(
                    self.attempt_root,
                    self.downloader_root,
                    trigger="analysis_awaiting_review",
                )
            except Exception as cleanup_error:
                try:
                    mark_cleanup_retry_required(
                        self.attempt_root,
                        trigger="analysis_awaiting_review",
                        error=str(cleanup_error),
                    )
                except Exception:
                    pass
            self.state = read_json(self.state_path)
            return self.state
        except Exception as exc:
            self.state["status"] = "failed"
            self.state["error"] = {
                "code": getattr(exc, "code", "CASE_ANALYSIS_FAILED"),
                "message": str(exc),
            }
            self.save()
            raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Recoverable canonical URL-to-Case analysis orchestration. "
            "It always stops at the explicit Human Case Review gate."
        )
    )
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--profile", choices=["mix", "news"])
    parser.add_argument("--operator-profile-hint", choices=["mix", "news", "hybrid", "uncertain"])
    parser.add_argument("--industry", default="待分类")
    parser.add_argument("--reanalyze", action="store_true")
    parser.add_argument("--pipeline-root", default=None)
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--downloader-root", default=None)
    parser.add_argument("--source-upload-id", default=None)
    parser.add_argument("--source-upload-receipt-sha256", default=None)
    parser.add_argument("--acquisition-provider", choices=["legacy_downloader", "qiyun", "upload_only"], default="legacy_downloader")
    parser.add_argument("--provider-source-url", default=None)
    args = parser.parse_args()
    if bool(args.profile) == bool(args.operator_profile_hint):
        parser.error("Provide exactly one of --profile or --operator-profile-hint")

    pipeline_root = (
        Path(args.pipeline_root).expanduser().resolve()
        if args.pipeline_root
        else Path(__file__).resolve().parents[1]
    )
    repo_root = (
        Path(args.repo_root).expanduser().resolve()
        if args.repo_root
        else pipeline_root.parent
    )
    downloader_root = (
        Path(args.downloader_root).expanduser().resolve()
        if args.downloader_root
        else repo_root / "douyin-downloader"
    )
    try:
        state = Orchestrator(
            pipeline_root=pipeline_root,
            repo_root=repo_root,
            downloader_root=downloader_root,
            source_url=args.source_url,
            attempt_id=args.attempt_id,
            profile=args.profile,
            industry=args.industry,
            reanalyze=args.reanalyze,
            operator_profile_hint=args.operator_profile_hint,
            source_upload_id=args.source_upload_id,
            source_upload_receipt_sha256=args.source_upload_receipt_sha256,
            acquisition_provider=args.acquisition_provider,
            provider_source_url=args.provider_source_url,
        ).run()
    except CaseAnalysisError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "message": str(exc)}, ensure_ascii=False))
        raise SystemExit(2) from exc
    print(
        json.dumps(
            {
                "ok": True,
                "case_id": state["case_id"],
                "attempt_id": state["attempt_id"],
                "status": state["status"],
                "progress": state["progress"],
                "case_candidate": state["artifacts"]["case_candidate_v1"],
                "auto_approved": False,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
