from __future__ import annotations

import os


EDGE_SECRET_PREFIXES = (
    "FRP_",
    "FRPC_",
    "FRPS_",
    "AIVO_FRP_",
    "AIVO_FRPC_",
    "AIVO_FRPS_",
)


def pipeline_subprocess_env(*, needs_deepseek: bool = False, needs_qiyun: bool = False) -> dict[str, str]:
    """Build the least-privilege environment for an ops-pipeline child."""

    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(EDGE_SECRET_PREFIXES)
    }
    if not needs_deepseek:
        environment.pop("DEEPSEEK_API_KEY", None)
    if not needs_qiyun:
        environment.pop("QYAPI_APP_ID", None)
        environment.pop("QYAPI_APP_KEY", None)
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    return environment
