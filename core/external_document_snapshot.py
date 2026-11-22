from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath


_INVESTIGATION_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
)

_SHA256_PATTERN = re.compile(
    r"^[0-9a-fA-F]{64}$"
)


def validate_investigation_id(
    value: str,
) -> str:
    if (
        not isinstance(value, str)
        or not _INVESTIGATION_ID_PATTERN.fullmatch(
            value
        )
    ):
        raise ValueError(
            "investigation_id invalide"
        )

    return value


def snapshot_id_for(
    *,
    source_system: str,
    source_path: str,
    source_sha256: str,
) -> str:
    if (
        not isinstance(source_system, str)
        or not source_system.strip()
    ):
        raise ValueError(
            "source_system invalide"
        )

    if (
        not isinstance(source_path, str)
        or not source_path.strip()
    ):
        raise ValueError(
            "source_path invalide"
        )

    if (
        not isinstance(source_sha256, str)
        or not _SHA256_PATTERN.fullmatch(
            source_sha256
        )
    ):
        raise ValueError(
            "source_sha256 invalide"
        )

    identity = {
        "source_system": source_system.strip(),
        "source_path": source_path,
        "source_sha256": (
            source_sha256.lower()
        ),
    }

    canonical = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    identity_hash = hashlib.sha256(
        canonical
    ).hexdigest()

    filename = PurePosixPath(
        source_path
    ).name

    stem = filename.rsplit(
        ".",
        1,
    )[0]

    safe_stem = "".join(
        character
        if (
            character.isalnum()
            or character in {"_", "-"}
        )
        else "_"
        for character in stem
    ).strip("_")

    if not safe_stem:
        safe_stem = "document"

    return (
        f"{safe_stem[:80]}__"
        f"{identity_hash[:16]}"
    )
