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

LEGACY_EXTERNAL_READING_WRITES_ENABLED = False

LEGACY_EXTERNAL_READING_FREEZE_REASON = (
    "Le pipeline historique d’inférence externe est gelé. "
    "Les sorties de moteur existantes restent consultables "
    "comme notes externes, mais ce chemin ne peut plus créer "
    "de rencontre, de réflexion attribuée à Eliot-Jr ou "
    "d’état dépendant d’une validation humaine."
)


def _require_legacy_external_reading_write(
    operation: str,
) -> None:
    if LEGACY_EXTERNAL_READING_WRITES_ENABLED:
        return

    raise ReadingJournalError(
        f"{LEGACY_EXTERNAL_READING_FREEZE_REASON} "
        f"Opération refusée : {operation}."
    )



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


def prepare_reading_queue(
    journals_root: Path,
    journal_id: str,
    manifest: dict[str, Any],
    prepared_by: str = "eliot_jr",
    now: datetime | None = None,
    commit: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Prépare les passages d'une source dans leur ordre de lecture.

    Un passage placé dans cette file n'est pas encore considéré comme lu,
    compris ou interprété. Il est seulement disponible pour une future
    rencontre avec un moteur d'inférence identifié.
    """
    path = _journal_path(journals_root, journal_id)
    timestamp = _utc_now(now)

    if not isinstance(manifest, dict):
        raise ReadingJournalError(
            "Le manifeste de lecture est invalide."
        )

    source_hash = str(
        manifest.get("source_sha256", "")
    ).strip()
    passages = manifest.get("passages", [])

    if not source_hash:
        raise ReadingJournalError(
            "Le manifeste ne contient pas de SHA-256 de source."
        )

    if not isinstance(passages, list) or not passages:
        raise ReadingJournalError(
            "Le manifeste ne contient aucun passage."
        )

    queue: list[dict[str, Any]] = []
    seen_passage_ids: set[str] = set()

    for expected_order, passage in enumerate(passages, 1):
        if not isinstance(passage, dict):
            raise ReadingJournalError(
                f"Le passage {expected_order} est invalide."
            )

        passage_id = str(
            passage.get("passage_id", "")
        ).strip()
        passage_hash = str(
            passage.get("sha256", "")
        ).strip()
        order = passage.get("order")

        if not passage_id or not passage_hash:
            raise ReadingJournalError(
                f"Le passage {expected_order} est incomplet."
            )

        if passage_id in seen_passage_ids:
            raise ReadingJournalError(
                f"Identifiant de passage dupliqué : {passage_id}"
            )

        if order != expected_order:
            raise ReadingJournalError(
                "L'ordre des passages du manifeste est incohérent."
            )

        seen_passage_ids.add(passage_id)

        queue.append({
            "passage_id": passage_id,
            "order": order,
            "passage_sha256": passage_hash,
            "word_count": int(
                passage.get("word_count", 0)
            ),
            "character_count": int(
                passage.get("character_count", 0)
            ),
            "status": "queued",
            "queued_at_utc": timestamp,
            "exposed_at_utc": None,
            "inference_engine": None,
            "reflection_status": "not_produced",
        })

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

        if not isinstance(before, dict):
            raise ReadingJournalError(
                "La section before_reading est invalide."
            )

        if work.get("source_sha256") != source_hash:
            raise ReadingJournalError(
                "Le manifeste ne correspond pas à la source "
                "enregistrée dans le journal."
            )

        if before.get("status") != "recorded":
            raise ReadingJournalError(
                "L'état avant lecture doit être enregistré "
                "avant de préparer la file."
            )

        previous_plan = journal.get("reading_plan")
        previous_queue = journal.get("reading_queue", [])

        same_plan = (
            isinstance(previous_plan, dict)
            and previous_plan.get("source_sha256") == source_hash
            and isinstance(previous_queue, list)
            and [
                item.get("passage_sha256")
                for item in previous_queue
                if isinstance(item, dict)
            ] == [
                item["passage_sha256"]
                for item in queue
            ]
        )

        if same_plan:
            report = {
                "journal_id": journal_id,
                "source_sha256": source_hash,
                "passage_count": len(queue),
                "queued_passages": sum(
                    1
                    for item in previous_queue
                    if (
                        isinstance(item, dict)
                        and item.get("status") == "queued"
                    )
                ),
                "already_prepared": True,
                "committed": False,
            }

            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            return journal, report

        updated = dict(journal)

        if isinstance(previous_plan, dict):
            superseded = journal.get(
                "superseded_reading_plans",
                [],
            )

            if not isinstance(superseded, list):
                superseded = []

            updated["superseded_reading_plans"] = [
                *superseded,
                {
                    "superseded_at_utc": timestamp,
                    "reading_plan": previous_plan,
                    "reading_queue": previous_queue,
                },
            ]

        updated["reading_plan"] = {
            "version": 1,
            "mode": "sequential",
            "source_sha256": source_hash,
            "source_file": manifest.get("source_file"),
            "prepared_at_utc": timestamp,
            "prepared_by": prepared_by,
            "passage_count": len(queue),
            "status": "ready",
            "epistemic_status": (
                "Passages indexés et ordonnés, "
                "mais pas encore lus ni interprétés."
            ),
        }
        updated["reading_queue"] = queue

        history = journal.get("change_history", [])

        if not isinstance(history, list):
            history = []

        updated["change_history"] = [
            *history,
            {
                "event": "reading_queue_prepared",
                "at_utc": timestamp,
                "by": prepared_by,
                "source_sha256": source_hash,
                "passage_count": len(queue),
                "reading_claimed": False,
                "reflection_claimed": False,
            },
        ]

        if commit:
            _write_atomic(path, updated)

        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    report = {
        "journal_id": journal_id,
        "source_sha256": source_hash,
        "passage_count": len(queue),
        "queued_passages": len(queue),
        "already_prepared": False,
        "committed": commit,
    }

    return updated, report


def record_validated_inference_result(
    journals_root: Path,
    journal_id: str,
    request: dict[str, Any],
    validated_result: dict[str, Any],
    committed_by: str = "eliot_jr",
    now: datetime | None = None,
    commit: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Inscrit atomiquement un résultat déjà validé.

    Une tentative sans réflexion peut être archivée, mais elle ne
    transforme pas le passage en lecture.

    Une rencontre n'est enregistrée que lorsque le résultat :
    - est validé ;
    - correspond exactement à la requête et au passage ;
    - identifie son moteur et son modèle ;
    - contient une sortie structurée et provisoire.
    """
    _require_legacy_external_reading_write(
        "record_validated_inference_result"
    )

    path = _journal_path(journals_root, journal_id)
    timestamp = _utc_now(now)

    if not isinstance(request, dict):
        raise ReadingJournalError(
            "La requête d'inférence est invalide."
        )

    if not isinstance(validated_result, dict):
        raise ReadingJournalError(
            "Le résultat validé est invalide."
        )

    if validated_result.get("validated") is not True:
        raise ReadingJournalError(
            "Le résultat n'a pas franchi la validation."
        )

    request_hash = str(
        request.get("request_sha256", "")
    ).strip()
    payload_hash = str(
        request.get("payload_sha256", "")
    ).strip()
    result_hash = str(
        validated_result.get("result_sha256", "")
    ).strip()

    if not request_hash or not payload_hash or not result_hash:
        raise ReadingJournalError(
            "Les empreintes d'audit sont incomplètes."
        )

    if (
        validated_result.get("request_sha256")
        != request_hash
    ):
        raise ReadingJournalError(
            "Le résultat ne correspond pas à cette tentative."
        )

    if (
        validated_result.get("payload_sha256")
        != payload_hash
    ):
        raise ReadingJournalError(
            "Le résultat ne correspond pas au contenu transmis."
        )

    passage = request.get("passage", {})

    if not isinstance(passage, dict):
        raise ReadingJournalError(
            "Le passage de la requête est invalide."
        )

    passage_id = str(
        passage.get("passage_id", "")
    ).strip()
    passage_hash = str(
        passage.get("passage_sha256", "")
    ).strip()

    if not passage_id or not passage_hash:
        raise ReadingJournalError(
            "L'identité du passage est incomplète."
        )

    reflection_produced = validated_result.get(
        "reflection_produced"
    )

    if not isinstance(reflection_produced, bool):
        raise ReadingJournalError(
            "reflection_produced doit être un booléen."
        )

    status = str(
        validated_result.get("status", "")
    ).strip()

    lock_path = path.with_suffix(path.suffix + ".lock")

    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)

        journal = _read_json(path)
        queue = journal.get("reading_queue", [])

        if not isinstance(queue, list):
            raise ReadingJournalError(
                "La file de lecture est invalide."
            )

        queue_index = next(
            (
                index
                for index, item in enumerate(queue)
                if (
                    isinstance(item, dict)
                    and item.get("passage_id") == passage_id
                )
            ),
            None,
        )

        if queue_index is None:
            raise ReadingJournalError(
                f"Passage absent de la file : {passage_id}"
            )

        queue_item = queue[queue_index]

        if (
            queue_item.get("passage_sha256")
            != passage_hash
        ):
            raise ReadingJournalError(
                "L'empreinte du passage ne correspond pas "
                "à la file de lecture."
            )

        encounters = journal.get("encounters", [])
        attempts = journal.get("inference_attempts", [])
        history = journal.get("change_history", [])

        if not isinstance(encounters, list):
            encounters = []

        if not isinstance(attempts, list):
            attempts = []

        if not isinstance(history, list):
            history = []

        existing_encounter = next(
            (
                item
                for item in encounters
                if (
                    isinstance(item, dict)
                    and item.get("result_sha256") == result_hash
                )
            ),
            None,
        )

        existing_attempt = next(
            (
                item
                for item in attempts
                if (
                    isinstance(item, dict)
                    and item.get("result_sha256") == result_hash
                )
            ),
            None,
        )

        if existing_encounter is not None:
            return journal, {
                "journal_id": journal_id,
                "passage_id": passage_id,
                "event": "encounter_already_recorded",
                "result_sha256": result_hash,
                "already_recorded": True,
                "committed": False,
            }

        if existing_attempt is not None:
            return journal, {
                "journal_id": journal_id,
                "passage_id": passage_id,
                "event": "attempt_already_recorded",
                "result_sha256": result_hash,
                "already_recorded": True,
                "committed": False,
            }

        updated = dict(journal)

        if not reflection_produced:
            attempt = {
                "attempt_number": len(attempts) + 1,
                "passage_id": passage_id,
                "passage_sha256": passage_hash,
                "attempted_at_utc": timestamp,
                "completed_at_utc": (
                    validated_result.get("completed_at_utc")
                ),
                "status": status,
                "engine_id": validated_result.get(
                    "engine_id"
                ),
                "model": validated_result.get("model"),
                "payload_sha256": payload_hash,
                "request_sha256": request_hash,
                "result_sha256": result_hash,
                "message": validated_result.get("message"),
                "reading_claimed": False,
                "reflection_claimed": False,
            }

            updated["inference_attempts"] = [
                *attempts,
                attempt,
            ]
            updated["change_history"] = [
                *history,
                {
                    "event": "inference_attempt_recorded",
                    "at_utc": timestamp,
                    "by": committed_by,
                    "passage_id": passage_id,
                    "status": status,
                    "result_sha256": result_hash,
                    "reading_claimed": False,
                    "reflection_claimed": False,
                },
            ]

            if commit:
                _write_atomic(path, updated)

            return updated, {
                "journal_id": journal_id,
                "passage_id": passage_id,
                "event": "inference_attempt_recorded",
                "status": status,
                "passage_status": queue_item.get("status"),
                "encounter_count": len(encounters),
                "reflection_recorded": False,
                "already_recorded": False,
                "committed": commit,
            }

        if status != "completed":
            raise ReadingJournalError(
                "Une rencontre ne peut être enregistrée "
                "qu'avec le statut completed."
            )

        if queue_item.get("status") != "queued":
            raise ReadingJournalError(
                f"Le passage {passage_id} n'est plus en attente."
            )

        model = validated_result.get("model")
        output = validated_result.get("output")

        if not isinstance(model, dict):
            raise ReadingJournalError(
                "L'attribution du modèle est absente."
            )

        if not isinstance(output, dict):
            raise ReadingJournalError(
                "La sortie structurée est absente."
            )

        updated_queue = [
            dict(item) if isinstance(item, dict) else item
            for item in queue
        ]

        updated_queue_item = dict(updated_queue[queue_index])
        updated_queue_item.update({
            "status": "encountered",
            "exposed_at_utc": timestamp,
            "inference_engine": {
                "engine_id": validated_result.get(
                    "engine_id"
                ),
                "model": model,
            },
            "reflection_status": "provisional_recorded",
            "payload_sha256": payload_hash,
            "request_sha256": request_hash,
            "result_sha256": result_hash,
        })
        updated_queue[queue_index] = updated_queue_item

        encounter = {
            "encounter_number": len(encounters) + 1,
            "encounter_id": (
                f"{journal_id}:{passage_id}:"
                f"{result_hash[:16]}"
            ),
            "passage_id": passage_id,
            "passage_order": passage.get("order"),
            "passage_sha256": passage_hash,
            "encountered_at_utc": timestamp,
            "engine_attribution": {
                "engine_id": validated_result.get(
                    "engine_id"
                ),
                "model": model,
            },
            "payload_sha256": payload_hash,
            "request_sha256": request_hash,
            "result_sha256": result_hash,
            "authorship_status": (
                "attributed_inference_output_integrated_"
                "by_eliot_jr_protocol"
            ),
            "epistemic_status": (
                "Sortie computationnelle provisoire, "
                "attribuée à un moteur identifié. "
                "Elle n'est ni une doctrine, ni une preuve "
                "de conscience, ni une conclusion définitive."
            ),
            "what_passage_says": output.get(
                "what_passage_says"
            ),
            "provisional_understanding": output.get(
                "provisional_understanding"
            ),
            "questions_or_objections": output.get(
                "questions_or_objections"
            ),
            "limits": output.get("limits"),
        }

        updated["reading_queue"] = updated_queue
        updated["encounters"] = [
            *encounters,
            encounter,
        ]
        updated["encounter_count"] = len(encounters) + 1
        updated["status"] = "reading"

        reading_plan = journal.get("reading_plan", {})

        if isinstance(reading_plan, dict):
            updated_plan = dict(reading_plan)
            updated_plan["status"] = "in_progress"
            updated_plan["encountered_passages"] = (
                len(encounters) + 1
            )
            updated_plan["remaining_passages"] = max(
                len(queue) - len(encounters) - 1,
                0,
            )
            updated["reading_plan"] = updated_plan

        updated["change_history"] = [
            *history,
            {
                "event": "validated_encounter_recorded",
                "at_utc": timestamp,
                "by": committed_by,
                "passage_id": passage_id,
                "engine_id": validated_result.get(
                    "engine_id"
                ),
                "model": model,
                "result_sha256": result_hash,
                "reflection_status": "provisional_recorded",
            },
        ]

        if commit:
            _write_atomic(path, updated)

    return updated, {
        "journal_id": journal_id,
        "passage_id": passage_id,
        "event": "validated_encounter_recorded",
        "status": "completed",
        "passage_status": "encountered",
        "encounter_count": len(encounters) + 1,
        "reflection_recorded": True,
        "already_recorded": False,
        "committed": commit,
    }
