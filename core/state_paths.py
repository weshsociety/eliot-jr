from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)

    if raw is None or not raw.strip():
        return default.resolve()

    return Path(raw).expanduser().resolve()


def memory_root() -> Path:
    return _env_path(
        "ELIOT_MEMORY_ROOT",
        PROJECT_ROOT / ".memory",
    )


def external_root() -> Path:
    return _env_path(
        "ELIOT_EXTERNAL_ROOT",
        PROJECT_ROOT / ".external",
    )


def external_encounters_root() -> Path:
    return external_root() / "encounters"


def external_snapshots_root() -> Path:
    return external_root() / "snapshots"
