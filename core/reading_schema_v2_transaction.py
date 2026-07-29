from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
import fcntl
import hashlib
import json
import os
import tempfile

from core.reading_candidate_registry import (
    verify_candidate,
)
from core.reading_schema_v2 import (
    TARGET_PASSAGES,
    migrate_candidate_document,
    migrate_journal_document,
)
from core.reading_status import (
    build_reading_status,
)
from gardien.backup_reading_state import (
    create_backup,
)


DEFAULT_ROOT = Path("/home/eliot-jr")

DEFAULT_JOURNAL_ID = (
    "lecture_thoreau_desobeissance_civile"
)


class ReadingSchemaV2TransactionError(
    RuntimeError
):
    pass


def _utc_now(
    now: datetime | None = None,
) -> datetime:
    value = now or datetime.now(
        timezone.utc
    )

    if value.tzinfo is None:
        value = value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(timezone.utc)


def _read_json(
    path: Path,
) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise ReadingSchemaV2TransactionError(
            f"Document JSON illisible : {path}"
        ) from exc

    if not isinstance(value, dict):
        raise ReadingSchemaV2TransactionError(
            f"Objet JSON attendu : {path}"
        )

    return value


def _json_bytes(
    value: dict[str, Any],
) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(
    payload: bytes,
) -> str:
    return hashlib.sha256(
        payload
    ).hexdigest()


def _file_sha256(
    path: Path,
) -> str:
    return _sha256_bytes(
        path.read_bytes()
    )


def _atomic_write_bytes(
    path: Path,
    payload: bytes,
    *,
    mode: int = 0o600,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )

    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)

        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())

    temporary.chmod(mode)
    temporary.replace(path)
    path.chmod(mode)

    directory_fd = os.open(
        path.parent,
        os.O_DIRECTORY,
    )

    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


@contextmanager
def _exclusive_locks(
    paths: list[Path],
) -> Iterator[None]:
    handles = []

    unique_paths = sorted(
        {
            path.resolve()
            for path in paths
        },
        key=str,
    )

    try:
        for path in unique_paths:
            path.parent.mkdir(
                parents=True,
                exist_ok=True,
                mode=0o700,
            )

            handle = path.open(
                "a+",
                encoding="utf-8",
            )

            path.chmod(0o600)

            fcntl.flock(
                handle.fileno(),
                fcntl.LOCK_EX,
            )

            handles.append(handle)

        yield

    finally:
        for handle in reversed(handles):
            try:
                fcntl.flock(
                    handle.fileno(),
                    fcntl.LOCK_UN,
                )
            finally:
                handle.close()


def _discover_candidates(
    candidates_root: Path,
) -> list[Path]:
    paths = sorted(
        candidates_root.glob("*.json")
    )

    if not paths:
        raise ReadingSchemaV2TransactionError(
            "Aucune candidate de lecture trouvée."
        )

    return paths


def _validate_target_candidates(
    candidates: list[dict[str, Any]],
) -> None:
    found = [
        str(
            candidate.get(
                "passage_id",
                "",
            )
        )
        for candidate in candidates
        if candidate.get("passage_id")
        in TARGET_PASSAGES
    ]

    if len(found) != len(set(found)):
        raise ReadingSchemaV2TransactionError(
            "Plusieurs candidates correspondent "
            "au même passage cible."
        )

    missing = sorted(
        set(TARGET_PASSAGES)
        - set(found)
    )

    if missing:
        raise ReadingSchemaV2TransactionError(
            "Candidates historiques absentes : "
            + ", ".join(missing)
        )


def _validate_passage_0005(
    journal: dict[str, Any],
) -> None:
    queue = journal.get(
        "reading_queue",
        [],
    )

    if not isinstance(queue, list):
        raise ReadingSchemaV2TransactionError(
            "File de lecture invalide."
        )

    passage = next(
        (
            item
            for item in queue
            if (
                isinstance(item, dict)
                and item.get("passage_id")
                == "passage_0005"
            )
        ),
        None,
    )

    if passage is None:
        raise ReadingSchemaV2TransactionError(
            "passage_0005 est absent."
        )

    if passage.get("status") != "queued":
        raise ReadingSchemaV2TransactionError(
            "passage_0005 ne doit pas être "
            "modifié par cette migration."
        )


def _validate_migrated_status(
    *,
    journal_path: Path,
    candidates_root: Path,
) -> dict[str, Any]:
    status = build_reading_status(
        journal_path,
        engine_available=False,
        candidates_root=candidates_root,
    )

    expected = {
        "journal_schema_version": 2,
        "external_reading_note_count": 4,
        "collective_review_count": 4,
        "logical_learning_count": 0,
        "logical_learning_pending_count": 4,
        "legacy_external_note_"
        "classification_count": 0,
    }

    for key, expected_value in expected.items():
        actual = status.get(key)

        if actual != expected_value:
            raise ReadingSchemaV2TransactionError(
                "Statut migré incohérent : "
                f"{key}={actual!r}, "
                f"attendu={expected_value!r}."
            )

    return status


def _prevalidate_documents(
    *,
    journal: dict[str, Any],
    candidates_by_name: dict[
        str,
        dict[str, Any],
    ],
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(
        prefix="eliot-reading-schema-v2-"
    ) as temporary:
        root = Path(temporary)

        journal_path = (
            root
            / "curriculum"
            / "journaux"
            / (
                DEFAULT_JOURNAL_ID
                + ".json"
            )
        )

        candidates_root = (
            root
            / ".memory"
            / "reading_candidates"
        )

        journal_path.parent.mkdir(
            parents=True,
            mode=0o700,
        )

        candidates_root.mkdir(
            parents=True,
            mode=0o700,
        )

        _atomic_write_bytes(
            journal_path,
            _json_bytes(journal),
        )

        for name, candidate in sorted(
            candidates_by_name.items()
        ):
            candidate_path = (
                candidates_root / name
            )

            _atomic_write_bytes(
                candidate_path,
                _json_bytes(candidate),
            )

            verify_candidate(
                candidate_path
            )

        _validate_passage_0005(
            journal
        )

        return _validate_migrated_status(
            journal_path=journal_path,
            candidates_root=(
                candidates_root
            ),
        )


def apply_reading_schema_v2(
    *,
    project_root: Path = DEFAULT_ROOT,
    journal_id: str = DEFAULT_JOURNAL_ID,
    now: datetime | None = None,
    fault_after_write_count: int | None = None,
) -> dict[str, Any]:
    """
    Applique la migration v2 aux quatre rencontres historiques.

    Ordre d'écriture :
    1. candidates ;
    2. journal en dernier.

    Une exception Python après le début des écritures déclenche
    une restauration byte-for-byte sous les mêmes verrous.

    La sauvegarde préalable constitue le point de récupération
    durable en cas d'interruption brutale du processus ou du VPS.
    """
    project_root = project_root.resolve()
    timestamp = _utc_now(now)
    migrated_at_utc = timestamp.isoformat()

    journal_path = (
        project_root
        / "curriculum"
        / "journaux"
        / f"{journal_id}.json"
    )

    candidates_root = (
        project_root
        / ".memory"
        / "reading_candidates"
    )

    backup_root = (
        project_root
        / ".backups"
        / "reading"
    )

    if not journal_path.is_file():
        raise ReadingSchemaV2TransactionError(
            "Journal de lecture introuvable."
        )

    candidate_paths = _discover_candidates(
        candidates_root
    )

    paths_to_preserve = [
        journal_path,
        *candidate_paths,
    ]

    initial_file_set = {
        path.name
        for path in candidate_paths
    }

    initial_hashes = {
        str(path): _file_sha256(path)
        for path in paths_to_preserve
    }

    pre_backup = create_backup(
        project_root=project_root,
        backup_root=backup_root,
    )

    if pre_backup.get("verified") is not True:
        raise ReadingSchemaV2TransactionError(
            "La sauvegarde préalable "
            "n'est pas vérifiée."
        )

    lock_paths = [
        (
            project_root
            / ".memory"
            / "reading_schema_v2.lock"
        ),
        backup_root / ".backup.lock",
        journal_path.with_suffix(
            journal_path.suffix + ".lock"
        ),
        *[
            path.with_suffix(
                path.suffix + ".lock"
            )
            for path in candidate_paths
        ],
    ]

    changed_candidate_paths: list[Path] = []
    journal_changed = False
    writes_completed = 0
    write_started = False
    migrated_status: dict[str, Any] | None = None

    with _exclusive_locks(lock_paths):
        current_paths = _discover_candidates(
            candidates_root
        )

        current_file_set = {
            path.name
            for path in current_paths
        }

        if current_file_set != initial_file_set:
            raise ReadingSchemaV2TransactionError(
                "Le jeu de candidates a changé "
                "pendant la préparation."
            )

        current_hashes = {
            str(path): _file_sha256(path)
            for path in paths_to_preserve
        }

        if current_hashes != initial_hashes:
            raise ReadingSchemaV2TransactionError(
                "Un état vivant a changé avant "
                "l'acquisition des verrous."
            )

        originals = {
            path: path.read_bytes()
            for path in paths_to_preserve
        }

        original_modes = {
            path: (
                path.stat().st_mode
                & 0o777
            )
            for path in paths_to_preserve
        }

        journal = _read_json(
            journal_path
        )

        _validate_passage_0005(
            journal
        )

        original_candidates = {
            path.name: _read_json(path)
            for path in candidate_paths
        }

        _validate_target_candidates(
            list(
                original_candidates.values()
            )
        )

        migrated_candidates: dict[
            str,
            dict[str, Any],
        ] = {}

        candidate_change_flags = {}

        for name, candidate in sorted(
            original_candidates.items()
        ):
            migrated, changed = (
                migrate_candidate_document(
                    candidate,
                    migrated_at_utc=(
                        migrated_at_utc
                    ),
                )
            )

            migrated_candidates[name] = (
                migrated
            )
            candidate_change_flags[name] = (
                changed
            )

        migrated_journal, journal_changed = (
            migrate_journal_document(
                journal,
                candidates=list(
                    migrated_candidates.values()
                ),
                migrated_at_utc=(
                    migrated_at_utc
                ),
            )
        )

        _validate_passage_0005(
            migrated_journal
        )

        migrated_status = (
            _prevalidate_documents(
                journal=migrated_journal,
                candidates_by_name=(
                    migrated_candidates
                ),
            )
        )

        changed_candidate_paths = [
            candidates_root / name
            for name, changed in (
                candidate_change_flags.items()
            )
            if changed
        ]

        if (
            not changed_candidate_paths
            and not journal_changed
        ):
            return {
                "schema_version": 2,
                "migrated": False,
                "already_applied": True,
                "documents_written": 0,
                "rollback_performed": False,
                "pre_backup": pre_backup,
                "post_backup": None,
                "status": migrated_status,
                "passage_0005_processed": False,
                "external_model_called": False,
            }

        try:
            write_started = True

            for path in changed_candidate_paths:
                _atomic_write_bytes(
                    path,
                    _json_bytes(
                        migrated_candidates[
                            path.name
                        ]
                    ),
                    mode=original_modes[path],
                )

                writes_completed += 1

                if (
                    fault_after_write_count
                    is not None
                    and writes_completed
                    >= fault_after_write_count
                ):
                    raise RuntimeError(
                        "Panne artificielle après "
                        f"{writes_completed} écriture(s)."
                    )

            if journal_changed:
                _atomic_write_bytes(
                    journal_path,
                    _json_bytes(
                        migrated_journal
                    ),
                    mode=original_modes[
                        journal_path
                    ],
                )

                writes_completed += 1

                if (
                    fault_after_write_count
                    is not None
                    and writes_completed
                    >= fault_after_write_count
                ):
                    raise RuntimeError(
                        "Panne artificielle après "
                        f"{writes_completed} écriture(s)."
                    )

            for path in candidate_paths:
                verify_candidate(path)

            live_journal = _read_json(
                journal_path
            )

            _validate_passage_0005(
                live_journal
            )

            migrated_status = (
                _validate_migrated_status(
                    journal_path=journal_path,
                    candidates_root=(
                        candidates_root
                    ),
                )
            )

        except Exception as exc:
            restoration_errors = []

            if write_started:
                for path in paths_to_preserve:
                    try:
                        _atomic_write_bytes(
                            path,
                            originals[path],
                            mode=original_modes[
                                path
                            ],
                        )
                    except Exception as restore_exc:
                        restoration_errors.append(
                            f"{path}: {restore_exc}"
                        )

                for path in paths_to_preserve:
                    expected = _sha256_bytes(
                        originals[path]
                    )

                    try:
                        actual = _file_sha256(
                            path
                        )
                    except OSError as verify_exc:
                        restoration_errors.append(
                            f"{path}: {verify_exc}"
                        )
                        continue

                    if actual != expected:
                        restoration_errors.append(
                            f"{path}: empreinte "
                            "restaurée non conforme"
                        )

            if restoration_errors:
                raise (
                    ReadingSchemaV2TransactionError(
                        "Échec de migration et "
                        "restauration incomplète : "
                        + " | ".join(
                            restoration_errors
                        )
                    )
                ) from exc

            raise ReadingSchemaV2TransactionError(
                "Migration annulée ; les "
                "documents originaux ont été "
                "restaurés exactement. Cause : "
                f"{exc}"
            ) from exc

    post_backup = create_backup(
        project_root=project_root,
        backup_root=backup_root,
    )

    if post_backup.get("verified") is not True:
        raise ReadingSchemaV2TransactionError(
            "La migration est appliquée, mais "
            "la sauvegarde postérieure n'est "
            "pas vérifiée."
        )

    return {
        "schema_version": 2,
        "migrated": True,
        "already_applied": False,
        "documents_written": (
            len(changed_candidate_paths)
            + int(journal_changed)
        ),
        "candidate_documents_written": len(
            changed_candidate_paths
        ),
        "journal_written": journal_changed,
        "rollback_performed": False,
        "pre_backup": pre_backup,
        "post_backup": post_backup,
        "status": migrated_status,
        "passage_0005_processed": False,
        "external_model_called": False,
    }
