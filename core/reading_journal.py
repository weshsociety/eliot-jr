from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


JOURNAL_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,100}$")


class ReadingJournalError(ValueError):
    """Erreur contrôlée du moteur de lecture."""


def _utc_now(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)

    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)

    return current.astimezone(timezone.utc).isoformat()


def _journal_path(
    journals_root: Path,
    journal_id: str,
) -> Path:
    journal_id = str(journal_id).strip()

    if not JOURNAL_ID_PATTERN.fullmatch(journal_id):
        raise ReadingJournalError(
            "Identifiant de journal invalide."
        )

    root = journals_root.resolve()
    path = (root / f"{journal_id}.json").resolve()

    if path.parent != root:
        raise ReadingJournalError(
            "Le journal demandé sort du dossier autorisé."
        )

    return path


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ReadingJournalError(
            f"Journal introuvable : {path.name}"
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReadingJournalError(
            f"Journal illisible : {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ReadingJournalError(
            "Le journal n’est pas un objet JSON."
        )

    return data


def _write_atomic(
    path: Path,
    data: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=path.parent,
    )

    try:
        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
        ) as temporary:
            json.dump(
                data,
                temporary,
                ensure_ascii=False,
                indent=2,
            )
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())

        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)

    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as source:
        for block in iter(
            lambda: source.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def _resolve_source(
    project_root: Path,
    source_file: str,
) -> Path:
    root = project_root.resolve()
    candidate = Path(source_file)

    if not candidate.is_absolute():
        candidate = root / candidate

    candidate = candidate.resolve()

    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ReadingJournalError(
            "La source doit appartenir à la maison d’Eliot."
        ) from exc

    if not candidate.is_file():
        raise ReadingJournalError(
            f"Source introuvable : {source_file}"
        )

    return candidate


def get_reading_status(
    journals_root: Path,
    journal_id: str,
) -> dict[str, Any]:
    path = _journal_path(journals_root, journal_id)
    journal = _read_json(path)

    work = journal.get("work", {})
    encounters = journal.get("encounters", [])
    before = journal.get("before_reading", {})
    after = journal.get("after_reading", {})

    if not isinstance(work, dict):
        work = {}

    if not isinstance(encounters, list):
        encounters = []

    if not isinstance(before, dict):
        before = {}

    if not isinstance(after, dict):
        after = {}

    return {
        "journal_id": journal.get("journal_id"),
        "status": journal.get("status"),
        "work": {
            "work_id": work.get("work_id"),
            "author": work.get("author"),
            "title": work.get("title"),
            "edition": work.get("edition"),
            "translator": work.get("translator"),
            "source_file": work.get("source_file"),
            "source_status": work.get("source_status"),
            "source_sha256": work.get("source_sha256"),
        },
        "before_reading_status": before.get("status"),
        "encounter_count": len(encounters),
        "after_reading_status": after.get("status"),
        "created_at_utc": journal.get("created_at_utc"),
        "opened_at_utc": journal.get("opened_at_utc"),
        "closed_at_utc": journal.get("closed_at_utc"),
    }


def register_reading_source(
    project_root: Path,
    journals_root: Path,
    journal_id: str,
    source_file: str,
    edition: str | None = None,
    translator: str | None = None,
    registered_by: str = "trinity",
    now: datetime | None = None,
    commit: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Enregistre un fichier réel comme source d’une lecture.

    Cette opération ne signifie pas qu’Eliot a commencé ou terminé
    le livre. Elle établit seulement quelle édition est disponible.
    """
    path = _journal_path(journals_root, journal_id)
    source_path = _resolve_source(
        project_root,
        source_file,
    )

    timestamp = _utc_now(now)
    source_hash = _sha256_file(source_path)
    relative_source = str(
        source_path.relative_to(project_root.resolve())
    )

    lock_path = path.with_suffix(path.suffix + ".lock")

    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)

        journal = _read_json(path)
        work = journal.get("work")

        if not isinstance(work, dict):
            raise ReadingJournalError(
                "La section work du journal est invalide."
            )

        previous_source = {
            "source_file": work.get("source_file"),
            "source_sha256": work.get("source_sha256"),
            "edition": work.get("edition"),
            "translator": work.get("translator"),
        }

        same_source = (
            previous_source["source_sha256"] == source_hash
            and previous_source["source_file"] == relative_source
        )

        updated_work = dict(work)
        updated_work.update({
            "source_file": relative_source,
            "source_status": "available",
            "source_sha256": source_hash,
            "source_size_bytes": source_path.stat().st_size,
            "source_registered_at_utc": timestamp,
            "source_registered_by": registered_by,
        })

        if edition is not None:
            updated_work["edition"] = edition

        if translator is not None:
            updated_work["translator"] = translator

        updated = dict(journal)
        updated["work"] = updated_work

        if journal.get("status") == "waiting_for_source":
            updated["status"] = "source_ready"

        history = journal.get("change_history", [])

        if not isinstance(history, list):
            history = []

        event = {
            "event": (
                "source_confirmed"
                if same_source
                else "source_registered"
            ),
            "at_utc": timestamp,
            "by": registered_by,
            "source_file": relative_source,
            "source_sha256": source_hash,
        }

        if (
            previous_source["source_sha256"]
            and previous_source["source_sha256"] != source_hash
        ):
            event["replaces"] = previous_source

        updated["change_history"] = [*history, event]

        if commit:
            _write_atomic(path, updated)

        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    report = {
        "journal_id": journal_id,
        "source_file": relative_source,
        "source_sha256": source_hash,
        "source_size_bytes": source_path.stat().st_size,
        "same_source_as_before": same_source,
        "status_after": updated.get("status"),
        "committed": commit,
    }

    return updated, report


def open_reading_with_baseline(
    journals_root: Path,
    journal_id: str,
    baseline: dict[str, Any],
    opened_by: str = "eliot_jr",
    now: datetime | None = None,
    commit: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Ouvre une lecture en conservant l'état d'Eliot avant exposition
    au texte.

    Le baseline doit provenir d'une interaction réelle avec Eliot.
    Il n'est ni corrigé ni réécrit par ce moteur.
    """
    path = _journal_path(journals_root, journal_id)
    timestamp = _utc_now(now)

    prompt = str(baseline.get("input", "")).strip()
    response = str(baseline.get("response", "")).strip()

    if not prompt or not response:
        raise ReadingJournalError(
            "Le baseline doit contenir une question et la réponse réelle d’Eliot."
        )

    lock_path = path.with_suffix(path.suffix + ".lock")

    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)

        journal = _read_json(path)
        work = journal.get("work", {})
        before = journal.get("before_reading", {})

        if not isinstance(work, dict):
            raise ReadingJournalError(
                "La section work du journal est invalide."
            )

        if work.get("source_status") != "available":
            raise ReadingJournalError(
                "La source doit être disponible avant l’ouverture."
            )

        if not isinstance(before, dict):
            raise ReadingJournalError(
                "La section before_reading est invalide."
            )

        if before.get("status") == "recorded":
            raise ReadingJournalError(
                "L’état avant lecture a déjà été enregistré."
            )

        temporal = baseline.get("temporal_context", {})
        sources = baseline.get("sources", [])

        if not isinstance(temporal, dict):
            temporal = {}

        if not isinstance(sources, list):
            sources = []

        baseline_timestamp = str(
            baseline.get("timestamp") or timestamp
        )

        updated_before = dict(before)
        updated_before.update({
            "recorded_at_utc": baseline_timestamp,
            "authorship": "eliot_jr",
            "method": "pre_reading_dialogue_snapshot",
            "source_exposure": "not_yet_exposed",
            "prompt": prompt,
            "response_verbatim": response,
            "memory_sources": sources,
            "interaction_number": temporal.get(
                "interaction_number"
            ),
            "current_understanding": [],
            "initial_questions": [],
            "assumptions_to_examine": [],
            "uncertainties": [],
            "status": "recorded",
        })

        history = journal.get("change_history", [])

        if not isinstance(history, list):
            history = []

        updated = dict(journal)
        updated["status"] = "reading"
        updated["opened_at_utc"] = baseline_timestamp
        updated["before_reading"] = updated_before
        updated["change_history"] = [
            *history,
            {
                "event": "reading_opened",
                "at_utc": baseline_timestamp,
                "by": opened_by,
                "source_exposure": "not_yet_exposed",
                "interaction_number": temporal.get(
                    "interaction_number"
                ),
            },
        ]

        if commit:
            _write_atomic(path, updated)

        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    report = {
        "journal_id": journal_id,
        "status_before": journal.get("status"),
        "status_after": updated.get("status"),
        "baseline_recorded": True,
        "source_exposure": "not_yet_exposed",
        "interaction_number": temporal.get(
            "interaction_number"
        ),
        "committed": commit,
    }

    return updated, report
