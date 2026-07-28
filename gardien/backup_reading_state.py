#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
import fcntl
import hashlib
import json
import os
import tarfile
import tempfile


class ReadingBackupError(RuntimeError):
    pass


DEFAULT_ROOT = Path("/home/eliot-jr")
DEFAULT_RETENTION = 30


def _canonical_bytes(
    value: Any,
) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(
    value: bytes,
) -> str:
    return hashlib.sha256(value).hexdigest()


def _utc_now(
    now: datetime | None = None,
) -> datetime:
    value = now or datetime.now(timezone.utc)

    if value.tzinfo is None:
        value = value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(timezone.utc)


def _write_json_atomic(
    path: Path,
    value: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )
    path.parent.chmod(0o700)

    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        payload = (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        ).encode("utf-8")

        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())

    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def _collect_files(
    project_root: Path,
) -> dict[str, bytes]:
    paths = [
        *sorted(
            (
                project_root
                / "curriculum"
                / "journaux"
            ).glob("*.json")
        ),
        *sorted(
            (
                project_root
                / ".memory"
                / "reading_candidates"
            ).glob("*.json")
        ),
    ]

    contents: dict[str, bytes] = {}

    for path in paths:
        if not path.is_file():
            continue

        relative = path.relative_to(
            project_root
        ).as_posix()

        contents[relative] = path.read_bytes()

    if not contents:
        raise ReadingBackupError(
            "Aucun état de lecture à sauvegarder."
        )

    return contents


def _build_manifest(
    *,
    project_root: Path,
    contents: dict[str, bytes],
    created_at: datetime,
) -> dict[str, Any]:
    files = []

    for relative, payload in sorted(
        contents.items()
    ):
        source = project_root / relative

        files.append({
            "path": relative,
            "size": len(payload),
            "mode": oct(
                source.stat().st_mode
                & 0o777
            ),
            "sha256": _sha256(payload),
        })

    state_payload = {
        "schema_version": 1,
        "files": files,
    }

    return {
        "schema_version": 1,
        "created_at_utc": (
            created_at.isoformat()
        ),
        "project_root": str(project_root),
        "state_sha256": _sha256(
            _canonical_bytes(state_payload)
        ),
        "file_count": len(files),
        "files": files,
        "claims": {
            "lock_files_included": False,
            "secrets_included": False,
            "external_transfer_performed": False,
            "source_files_modified": False,
        },
    }


def verify_backup(
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
        raise ReadingBackupError(
            "Manifeste de sauvegarde illisible."
        ) from exc

    if not isinstance(sidecar, dict):
        raise ReadingBackupError(
            "Le manifeste doit être un objet."
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
                raise ReadingBackupError(
                    "Manifeste absent de l’archive."
                )

            embedded = json.loads(
                manifest_handle.read().decode(
                    "utf-8"
                )
            )

            if embedded != sidecar:
                raise ReadingBackupError(
                    "Le manifeste embarqué diffère "
                    "du manifeste latéral."
                )

            for entry in sidecar.get(
                "files",
                [],
            ):
                if not isinstance(entry, dict):
                    raise ReadingBackupError(
                        "Entrée de manifeste invalide."
                    )

                relative = str(
                    entry.get("path", "")
                )

                member = archive.getmember(
                    relative
                )
                handle = archive.extractfile(
                    member
                )

                if handle is None:
                    raise ReadingBackupError(
                        f"Fichier absent : {relative}"
                    )

                payload = handle.read()

                if len(payload) != entry.get(
                    "size"
                ):
                    raise ReadingBackupError(
                        f"Taille invalide : {relative}"
                    )

                if _sha256(payload) != entry.get(
                    "sha256"
                ):
                    raise ReadingBackupError(
                        f"Empreinte invalide : "
                        f"{relative}"
                    )

    except (
        OSError,
        tarfile.TarError,
        KeyError,
        json.JSONDecodeError,
    ) as exc:
        if isinstance(
            exc,
            ReadingBackupError,
        ):
            raise

        raise ReadingBackupError(
            "Archive de sauvegarde invalide."
        ) from exc

    return {
        "verified": True,
        "archive_path": str(archive_path),
        "manifest_path": str(manifest_path),
        "state_sha256": sidecar.get(
            "state_sha256"
        ),
        "file_count": sidecar.get(
            "file_count"
        ),
    }


def _latest_manifest(
    backup_root: Path,
) -> Path | None:
    manifests = sorted(
        backup_root.glob(
            "reading-state-*.manifest.json"
        )
    )

    return manifests[-1] if manifests else None


def _apply_retention(
    *,
    backup_root: Path,
    retention: int,
) -> int:
    manifests = sorted(
        backup_root.glob(
            "reading-state-*.manifest.json"
        )
    )

    removed = 0

    for manifest_path in manifests[
        :-retention
    ]:
        archive_name = manifest_path.name.replace(
            ".manifest.json",
            ".tar.gz",
        )
        archive_path = (
            backup_root / archive_name
        )

        if archive_path.exists():
            archive_path.unlink()

        manifest_path.unlink()
        removed += 1

    return removed


def create_backup(
    *,
    project_root: Path = DEFAULT_ROOT,
    backup_root: Path | None = None,
    retention: int = DEFAULT_RETENTION,
    now: datetime | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()

    backup_root = (
        backup_root
        or project_root
        / ".backups"
        / "reading"
    ).resolve()

    if retention < 1:
        raise ReadingBackupError(
            "La rétention doit être positive."
        )

    backup_root.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )
    backup_root.chmod(0o700)

    lock_path = (
        backup_root / ".backup.lock"
    )

    with lock_path.open(
        "a+",
        encoding="utf-8",
    ) as lock:
        lock_path.chmod(0o600)
        fcntl.flock(
            lock.fileno(),
            fcntl.LOCK_EX,
        )

        created_at = _utc_now(now)
        contents = _collect_files(
            project_root
        )
        manifest = _build_manifest(
            project_root=project_root,
            contents=contents,
            created_at=created_at,
        )

        latest_path = _latest_manifest(
            backup_root
        )

        if latest_path is not None:
            try:
                latest = json.loads(
                    latest_path.read_text(
                        encoding="utf-8"
                    )
                )
            except (
                OSError,
                json.JSONDecodeError,
            ):
                latest = {}

            latest_archive = backup_root / (
                latest_path.name.replace(
                    ".manifest.json",
                    ".tar.gz",
                )
            )

            if (
                latest.get("state_sha256")
                == manifest["state_sha256"]
                and latest_archive.is_file()
            ):
                verification = verify_backup(
                    archive_path=latest_archive,
                    manifest_path=latest_path,
                )

                return {
                    **verification,
                    "created": False,
                    "already_current": True,
                    "removed_by_retention": 0,
                }

        timestamp = created_at.strftime(
            "%Y%m%dT%H%M%S%fZ"
        )
        digest = manifest[
            "state_sha256"
        ][:16]

        stem = (
            f"reading-state-{timestamp}-{digest}"
        )

        archive_path = (
            backup_root / f"{stem}.tar.gz"
        )
        manifest_path = (
            backup_root
            / f"{stem}.manifest.json"
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
                manifest_info = tarfile.TarInfo(
                    "MANIFEST.json"
                )
                manifest_info.size = len(
                    manifest_bytes
                )
                manifest_info.mode = 0o600
                manifest_info.mtime = int(
                    created_at.timestamp()
                )

                archive.addfile(
                    manifest_info,
                    BytesIO(manifest_bytes),
                )

                for relative, payload in sorted(
                    contents.items()
                ):
                    info = tarfile.TarInfo(
                        relative
                    )
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

        verification = verify_backup(
            archive_path=archive_path,
            manifest_path=manifest_path,
        )

        removed = _apply_retention(
            backup_root=backup_root,
            retention=retention,
        )

        return {
            **verification,
            "created": True,
            "already_current": False,
            "archive_size": (
                archive_path.stat().st_size
            ),
            "removed_by_retention": removed,
        }


def main() -> None:
    report = create_backup()

    print("===== SAUVEGARDE LECTURE =====")
    print(
        "Créée :",
        report["created"],
    )
    print(
        "Déjà actuelle :",
        report["already_current"],
    )
    print(
        "Vérifiée :",
        report["verified"],
    )
    print(
        "Fichiers :",
        report["file_count"],
    )
    print(
        "État SHA-256 :",
        report["state_sha256"],
    )
    print(
        "Archive :",
        report["archive_path"],
    )
    print(
        "Rétention appliquée :",
        report[
            "removed_by_retention"
        ],
    )


if __name__ == "__main__":
    main()
