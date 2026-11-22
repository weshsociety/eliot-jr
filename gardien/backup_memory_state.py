#!/usr/bin/env python3

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any


class MemoryBackupError(RuntimeError):
    pass


ROLE_INTERNAL = "internal_memory_state"
ROLE_HISTORICAL = "historical_retained"
ROLE_EXTERNAL_PRIVATE = "external_private_source"

ALLOWED_MEMORY_ROLES = frozenset({
    ROLE_INTERNAL,
    ROLE_HISTORICAL,
    ROLE_EXTERNAL_PRIVATE,
})


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _utc_now(now: datetime | None = None) -> datetime:
    value = now or datetime.now(timezone.utc)

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def _role_for(relative: Path) -> str:
    parts = relative.parts

    if (
        parts
        and parts[0] == "investigation_encounters"
    ):
        return ROLE_EXTERNAL_PRIVATE

    if relative.name.endswith(".before-repair"):
        return ROLE_HISTORICAL

    return ROLE_INTERNAL


def _collect_files(
    memory_root: Path,
) -> dict[str, tuple[Path, bytes, str]]:
    contents: dict[
        str,
        tuple[Path, bytes, str],
    ] = {}

    for path in sorted(memory_root.rglob("*")):
        if not path.is_file():
            continue

        if path.name.endswith(".lock"):
            continue

        relative = path.relative_to(memory_root)

        logical = (
            Path(".memory") / relative
        ).as_posix()

        contents[logical] = (
            path,
            path.read_bytes(),
            _role_for(relative),
        )

    if not contents:
        raise MemoryBackupError(
            "Aucun état mémoire à sauvegarder."
        )

    return contents


def _build_manifest(
    *,
    contents: dict[
        str,
        tuple[Path, bytes, str],
    ],
    created_at: datetime,
) -> dict[str, Any]:
    files: list[dict[str, Any]] = []

    for logical, source_value in sorted(
        contents.items()
    ):
        source, payload, role = source_value

        files.append({
            "path": logical,
            "role": role,
            "size": len(payload),
            "mode": oct(
                source.stat().st_mode & 0o777
            ),
            "sha256": _sha256(payload),
        })

    state_payload = {
        "schema_version": 1,
        "files": files,
    }

    return {
        "schema_version": 1,
        "kind": "eliot_jr_full_memory_backup",
        "created_at_utc": created_at.isoformat(),
        "state_sha256": _sha256(
            _canonical_bytes(state_payload)
        ),
        "file_count": len(files),
        "files": files,
        "claims": {
            "logical_memory_prefix": ".memory",
            "lock_files_included": False,
            "physical_memory_root_recorded": False,
            "source_files_modified": False,
            "external_transfer_performed": False,
            "requires_quiescent_source": True,
        },
    }


def _write_json_atomic(
    path: Path,
    value: dict[str, Any],
) -> None:
    payload = (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )

    with tempfile.NamedTemporaryFile(
        mode="w+b",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())

    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def verify_memory_backup(
    *,
    archive_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    try:
        sidecar = json.loads(
            manifest_path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise MemoryBackupError(
            "Manifeste mémoire illisible."
        ) from exc

    if not isinstance(sidecar, dict):
        raise MemoryBackupError(
            "Le manifeste mémoire doit être un objet."
        )

    files = sidecar.get("files")

    if not isinstance(files, list):
        raise MemoryBackupError(
            "La liste des fichiers du manifeste est invalide."
        )

    if sidecar.get("file_count") != len(files):
        raise MemoryBackupError(
            "Le nombre de fichiers du manifeste est incohérent."
        )

    logical_paths: set[str] = set()

    for entry in files:
        if not isinstance(entry, dict):
            raise MemoryBackupError(
                "Entrée de manifeste invalide."
            )

        logical = str(
            entry.get("path", "")
        )

        if logical in logical_paths:
            raise MemoryBackupError(
                f"Chemin logique dupliqué : {logical}"
            )

        logical_paths.add(logical)

    state_payload = {
        "schema_version": sidecar.get(
            "schema_version"
        ),
        "files": files,
    }

    expected_state_sha256 = _sha256(
        _canonical_bytes(state_payload)
    )

    if sidecar.get("state_sha256") != (
        expected_state_sha256
    ):
        raise MemoryBackupError(
            "SHA-256 global de l'état mémoire invalide."
        )

    try:
        with tarfile.open(
            archive_path,
            mode="r:gz",
        ) as archive:
            manifest_member = archive.getmember(
                "MANIFEST.json"
            )
            manifest_handle = archive.extractfile(
                manifest_member
            )

            if manifest_handle is None:
                raise MemoryBackupError(
                    "MANIFEST.json absent."
                )

            embedded = json.loads(
                manifest_handle.read().decode(
                    "utf-8"
                )
            )

            if embedded != sidecar:
                raise MemoryBackupError(
                    "Le manifeste embarqué diffère "
                    "du manifeste latéral."
                )

            for entry in sidecar.get("files", []):
                relative = str(
                    entry.get("path", "")
                )

                _restore_relative_path(
                    relative
                )

                role = str(
                    entry.get("role", "")
                )

                if role not in ALLOWED_MEMORY_ROLES:
                    raise MemoryBackupError(
                        f"Rôle mémoire inconnu : {role}"
                    )

                member = archive.getmember(relative)
                handle = archive.extractfile(member)

                if handle is None:
                    raise MemoryBackupError(
                        f"Fichier absent : {relative}"
                    )

                payload = handle.read()

                if len(payload) != entry.get("size"):
                    raise MemoryBackupError(
                        f"Taille invalide : {relative}"
                    )

                if _sha256(payload) != entry.get(
                    "sha256"
                ):
                    raise MemoryBackupError(
                        f"SHA-256 invalide : {relative}"
                    )

    except (
        OSError,
        tarfile.TarError,
        KeyError,
        json.JSONDecodeError,
    ) as exc:
        if isinstance(exc, MemoryBackupError):
            raise

        raise MemoryBackupError(
            "Archive mémoire invalide."
        ) from exc

    return {
        "verified": True,
        "archive_path": str(archive_path),
        "manifest_path": str(manifest_path),
        "file_count": sidecar["file_count"],
        "state_sha256": sidecar["state_sha256"],
    }


def create_memory_backup(
    *,
    memory_root: Path,
    backup_root: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    memory_root = memory_root.resolve()
    backup_root = backup_root.resolve()

    if not memory_root.is_dir():
        raise MemoryBackupError(
            "Le memory_root n'existe pas."
        )

    backup_root.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )
    backup_root.chmod(0o700)

    created_at = _utc_now(now)

    contents = _collect_files(memory_root)

    manifest = _build_manifest(
        contents=contents,
        created_at=created_at,
    )

    timestamp = created_at.strftime(
        "%Y%m%dT%H%M%S%fZ"
    )
    digest = manifest["state_sha256"][:16]

    stem = (
        f"memory-state-{timestamp}-{digest}"
    )

    archive_path = (
        backup_root / f"{stem}.tar.gz"
    )
    manifest_path = (
        backup_root / f"{stem}.manifest.json"
    )

    manifest_bytes = (
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")

    with tempfile.NamedTemporaryFile(
        mode="w+b",
        dir=backup_root,
        prefix=f".{stem}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)

        with tarfile.open(
            fileobj=handle,
            mode="w:gz",
            format=tarfile.PAX_FORMAT,
        ) as archive:
            info = tarfile.TarInfo(
                "MANIFEST.json"
            )
            info.size = len(manifest_bytes)
            info.mode = 0o600
            info.mtime = int(
                created_at.timestamp()
            )

            archive.addfile(
                info,
                BytesIO(manifest_bytes),
            )

            for logical, source_value in sorted(
                contents.items()
            ):
                _source, payload, _role = (
                    source_value
                )

                info = tarfile.TarInfo(logical)
                info.size = len(payload)
                info.mode = 0o600
                info.mtime = int(
                    created_at.timestamp()
                )

                archive.addfile(
                    info,
                    BytesIO(payload),
                )

        handle.flush()
        os.fsync(handle.fileno())

    temporary.chmod(0o600)
    temporary.replace(archive_path)
    archive_path.chmod(0o600)

    _write_json_atomic(
        manifest_path,
        manifest,
    )

    return verify_memory_backup(
        archive_path=archive_path,
        manifest_path=manifest_path,
    )


def _restore_relative_path(logical: str) -> Path:
    candidate = Path(logical)

    if candidate.is_absolute():
        raise MemoryBackupError(
            "Chemin absolu interdit dans la sauvegarde."
        )

    if not candidate.parts:
        raise MemoryBackupError(
            "Chemin mémoire vide."
        )

    if candidate.parts[0] != ".memory":
        raise MemoryBackupError(
            "Chemin hors de l'espace logique .memory."
        )

    relative = Path(*candidate.parts[1:])

    if not relative.parts:
        raise MemoryBackupError(
            "Chemin mémoire incomplet."
        )

    if ".." in relative.parts:
        raise MemoryBackupError(
            "Traversée de chemin interdite."
        )

    return relative


def restore_memory_backup(
    *,
    archive_path: Path,
    manifest_path: Path,
    memory_root: Path,
) -> dict[str, Any]:
    verification = verify_memory_backup(
        archive_path=archive_path,
        manifest_path=manifest_path,
    )

    try:
        manifest = json.loads(
            manifest_path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise MemoryBackupError(
            "Manifeste mémoire illisible."
        ) from exc

    memory_root = memory_root.resolve()

    if memory_root.exists():
        raise MemoryBackupError(
            "La cible de restauration existe déjà."
        )

    memory_root.parent.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )

    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{memory_root.name}.restore-",
            dir=memory_root.parent,
        )
    )
    staging.chmod(0o700)

    restored = 0
    historical_restored = 0
    external_private_skipped = 0

    try:
        with tarfile.open(
            archive_path,
            mode="r:gz",
        ) as archive:
            for entry in manifest.get(
                "files",
                [],
            ):
                if not isinstance(entry, dict):
                    raise MemoryBackupError(
                        "Entrée de manifeste invalide."
                    )

                logical = str(
                    entry.get("path", "")
                )
                role = str(
                    entry.get("role", "")
                )

                relative = _restore_relative_path(
                    logical
                )

                if role == ROLE_EXTERNAL_PRIVATE:
                    external_private_skipped += 1
                    continue

                if role not in {
                    "internal_memory_state",
                    "historical_retained",
                }:
                    raise MemoryBackupError(
                        f"Rôle mémoire inconnu : {role}"
                    )

                member = archive.getmember(
                    logical
                )

                if not member.isfile():
                    raise MemoryBackupError(
                        "Membre non régulier interdit : "
                        f"{logical}"
                    )

                handle = archive.extractfile(
                    member
                )

                if handle is None:
                    raise MemoryBackupError(
                        f"Fichier absent : {logical}"
                    )

                payload = handle.read()

                if len(payload) != entry.get(
                    "size"
                ):
                    raise MemoryBackupError(
                        f"Taille invalide : {logical}"
                    )

                if _sha256(payload) != entry.get(
                    "sha256"
                ):
                    raise MemoryBackupError(
                        f"SHA-256 invalide : {logical}"
                    )

                target = staging / relative

                target.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                    mode=0o700,
                )

                with tempfile.NamedTemporaryFile(
                    mode="w+b",
                    dir=target.parent,
                    prefix=f".{target.name}.",
                    suffix=".restore",
                    delete=False,
                ) as out:
                    temporary = Path(out.name)
                    out.write(payload)
                    out.flush()
                    os.fsync(out.fileno())

                temporary.chmod(0o600)
                temporary.replace(target)
                target.chmod(0o600)

                restored += 1

                if role == ROLE_HISTORICAL:
                    historical_restored += 1

        if memory_root.exists():
            raise MemoryBackupError(
                "La cible de restauration est apparue "
                "pendant l'opération."
            )

        staging.replace(memory_root)

    except Exception:
        if staging.exists():
            shutil.rmtree(
                staging,
                ignore_errors=True,
            )
        raise

    return {
        **verification,
        "memory_root": str(memory_root),
        "restored_files": restored,
        "historical_restored": (
            historical_restored
        ),
        "external_private_skipped": (
            external_private_skipped
        ),
    }
