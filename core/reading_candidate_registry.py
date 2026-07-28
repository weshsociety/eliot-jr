from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import fcntl
import hashlib
import json
import os
import tempfile

from core.inference_validation import (
    validate_inference_result,
)
from core.reading_journal import (
    record_validated_inference_result,
)


class ReadingCandidateError(ValueError):
    pass

LEGACY_EXTERNAL_READING_WRITES_ENABLED = False

LEGACY_EXTERNAL_READING_FREEZE_REASON = (
    "Le registre historique des candidates LLM est gelé. "
    "Les candidates existantes restent vérifiables et "
    "migrables, mais aucune nouvelle candidate, revue "
    "obligatoire ou application historique ne peut être écrite."
)


def _require_legacy_external_reading_write(
    operation: str,
) -> None:
    if LEGACY_EXTERNAL_READING_WRITES_ENABLED:
        return

    raise ReadingCandidateError(
        f"{LEGACY_EXTERNAL_READING_FREEZE_REASON} "
        f"Opération refusée : {operation}."
    )



ACCEPTED_DECISIONS = {
    "accepted",
    "accepted_with_reservation",
}

ALLOWED_DECISIONS = {
    *ACCEPTED_DECISIONS,
    "rejected",
}


def _utc_now(
    now: datetime | None = None,
) -> str:
    value = now or datetime.now(timezone.utc)

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc).isoformat()


def _canonical_hash(
    value: dict[str, Any],
) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def _read_json(
    path: Path,
) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise ReadingCandidateError(
            f"Fichier JSON illisible : {path}"
        ) from exc

    if not isinstance(value, dict):
        raise ReadingCandidateError(
            f"Objet JSON attendu : {path}"
        )

    return value


def _write_atomic(
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
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)

        json.dump(
            value,
            handle,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())

    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def _candidate_hash(
    candidate: dict[str, Any],
) -> str:
    payload = deepcopy(candidate)
    payload.pop("candidate_sha256", None)

    return _canonical_hash(payload)


def _replace_candidate_hash(
    candidate: dict[str, Any],
    previous_hash: str,
) -> dict[str, Any]:
    updated = deepcopy(candidate)
    updated.pop("candidate_sha256", None)
    updated["previous_candidate_sha256"] = (
        previous_hash
    )
    updated["candidate_sha256"] = (
        _canonical_hash(updated)
    )

    return updated


def _candidate_filename(
    journal_id: str,
    passage_id: str,
    result_sha256: str,
) -> str:
    return (
        f"{journal_id}__"
        f"{passage_id}__"
        f"{result_sha256[:16]}.json"
    )


def _extract_identity(
    request: dict[str, Any],
) -> tuple[str, str]:
    journal_id = str(
        request.get("journal_id", "")
    ).strip()

    passage = request.get("passage", {})

    if not isinstance(passage, dict):
        raise ReadingCandidateError(
            "Le passage de la requête est invalide."
        )

    passage_id = str(
        passage.get("passage_id", "")
    ).strip()

    if not journal_id or not passage_id:
        raise ReadingCandidateError(
            "journal_id ou passage_id absent."
        )

    return journal_id, passage_id


def verify_candidate(
    candidate_path: Path,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
]:
    candidate = _read_json(candidate_path)

    stored_hash = str(
        candidate.get("candidate_sha256", "")
    ).strip()

    if not stored_hash:
        raise ReadingCandidateError(
            "Empreinte de candidate absente."
        )

    calculated_hash = _candidate_hash(candidate)

    if calculated_hash != stored_hash:
        raise ReadingCandidateError(
            "L’empreinte de la candidate "
            "n’est plus conforme."
        )

    request = candidate.get("request")
    stored_result = candidate.get(
        "validated_result"
    )

    if not isinstance(request, dict):
        raise ReadingCandidateError(
            "Requête candidate invalide."
        )

    if not isinstance(stored_result, dict):
        raise ReadingCandidateError(
            "Résultat candidat invalide."
        )

    journal_id, passage_id = (
        _extract_identity(request)
    )

    if (
        candidate.get("journal_id")
        != journal_id
        or candidate.get("passage_id")
        != passage_id
    ):
        raise ReadingCandidateError(
            "L’identité de la candidate "
            "ne correspond pas à sa requête."
        )

    validated_result = (
        validate_inference_result(
            request=request,
            result=stored_result,
        )
    )

    if (
        validated_result["result_sha256"]
        != stored_result.get("result_sha256")
    ):
        raise ReadingCandidateError(
            "L’empreinte du résultat "
            "n’est plus conforme."
        )

    report = {
        "candidate_path": str(candidate_path),
        "candidate_sha256": stored_hash,
        "journal_id": journal_id,
        "passage_id": passage_id,
        "result_sha256": validated_result[
            "result_sha256"
        ],
        "reflection_produced": validated_result[
            "reflection_produced"
        ],
        "candidate_status": candidate.get(
            "candidate_status"
        ),
        "verified": True,
    }

    return candidate, report


def create_candidate(
    *,
    candidates_root: Path,
    request: dict[str, Any],
    validated_result: dict[str, Any],
) -> tuple[
    Path,
    dict[str, Any],
]:
    _require_legacy_external_reading_write(
        "create_candidate"
    )

    normalized = validate_inference_result(
        request=request,
        result=validated_result,
    )

    if normalized["reflection_produced"] is not True:
        raise ReadingCandidateError(
            "Une candidate de rencontre doit "
            "contenir une réflexion validée."
        )

    journal_id, passage_id = (
        _extract_identity(request)
    )

    result_sha256 = normalized[
        "result_sha256"
    ]

    candidate = {
        "schema_version": 1,
        "candidate_status": (
            "pending_human_review"
        ),
        "journal_id": journal_id,
        "passage_id": passage_id,
        "created_at_utc": normalized[
            "completed_at_utc"
        ],
        "request": deepcopy(request),
        "validated_result": normalized,
        "review": {
            "decision": None,
            "reviewed_at_utc": None,
            "reviewed_by": None,
            "comment": None,
            "explicit_human_confirmation": False,
        },
        "application": {
            "applied": False,
            "applied_at_utc": None,
            "applied_by": None,
        },
        "review_history": [],
        "application_history": [],
        "claims": {
            "journal_modified": False,
            "encounter_recorded": False,
            "doctrine_adopted": False,
            "subjective_experience_claimed": False,
            "external_action_performed": False,
        },
    }

    candidate["candidate_sha256"] = (
        _candidate_hash(candidate)
    )

    candidate_path = (
        candidates_root
        / _candidate_filename(
            journal_id,
            passage_id,
            result_sha256,
        )
    )

    lock_path = candidate_path.with_suffix(
        candidate_path.suffix + ".lock"
    )

    candidate_path.parent.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )

    with lock_path.open(
        "a+",
        encoding="utf-8",
    ) as lock:
        fcntl.flock(
            lock.fileno(),
            fcntl.LOCK_EX,
        )

        if candidate_path.exists():
            existing, report = verify_candidate(
                candidate_path
            )

            if existing != candidate:
                raise ReadingCandidateError(
                    "Une candidate différente "
                    "occupe déjà ce chemin."
                )

            report.update({
                "created": False,
                "already_exists": True,
            })

            return candidate_path, report

        _write_atomic(
            candidate_path,
            candidate,
        )

        fcntl.flock(
            lock.fileno(),
            fcntl.LOCK_UN,
        )

    return candidate_path, {
        "candidate_path": str(candidate_path),
        "candidate_sha256": candidate[
            "candidate_sha256"
        ],
        "journal_id": journal_id,
        "passage_id": passage_id,
        "result_sha256": result_sha256,
        "created": True,
        "already_exists": False,
    }


def review_candidate(
    *,
    candidate_path: Path,
    decision: str,
    reviewed_by: str,
    comment: str = "",
    explicit_human_confirmation: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    _require_legacy_external_reading_write(
        "review_candidate"
    )

    decision = str(decision).strip()
    reviewed_by = str(reviewed_by).strip()
    comment = str(comment).strip()

    if decision not in ALLOWED_DECISIONS:
        raise ReadingCandidateError(
            f"Décision inconnue : {decision}"
        )

    if not reviewed_by:
        raise ReadingCandidateError(
            "L’auteur de la revue est requis."
        )

    if (
        decision in ACCEPTED_DECISIONS
        and explicit_human_confirmation is not True
    ):
        raise ReadingCandidateError(
            "Une acceptation exige une "
            "confirmation humaine explicite."
        )

    lock_path = candidate_path.with_suffix(
        candidate_path.suffix + ".lock"
    )

    with lock_path.open(
        "a+",
        encoding="utf-8",
    ) as lock:
        fcntl.flock(
            lock.fileno(),
            fcntl.LOCK_EX,
        )

        candidate, verification = (
            verify_candidate(candidate_path)
        )

        existing_review = candidate.get(
            "review",
            {},
        )

        if not isinstance(existing_review, dict):
            existing_review = {}

        same_review = (
            existing_review.get("decision")
            == decision
            and existing_review.get("reviewed_by")
            == reviewed_by
            and str(
                existing_review.get(
                    "comment",
                    "",
                )
            ).strip()
            == comment
            and existing_review.get(
                "explicit_human_confirmation"
            )
            is explicit_human_confirmation
        )

        if same_review:
            return {
                **verification,
                "reviewed": True,
                "already_reviewed": True,
                "written": False,
                "decision": decision,
            }

        if existing_review.get("decision"):
            raise ReadingCandidateError(
                "La candidate possède déjà "
                "une revue différente."
            )

        if (
            candidate.get(
                "application",
                {},
            ).get("applied")
            is True
        ):
            raise ReadingCandidateError(
                "Une candidate appliquée "
                "ne peut plus être revue."
            )

        timestamp = _utc_now(now)

        review_event = {
            "decision": decision,
            "reviewed_at_utc": timestamp,
            "reviewed_by": reviewed_by,
            "comment": comment,
            "candidate_sha256_before_review": (
                candidate["candidate_sha256"]
            ),
            "result_sha256": candidate[
                "validated_result"
            ]["result_sha256"],
            "explicit_human_confirmation": (
                explicit_human_confirmation
            ),
        }

        updated = deepcopy(candidate)

        history = list(
            updated.get(
                "review_history",
                [],
            )
        )
        history.append(review_event)

        updated["review"] = review_event
        updated["review_history"] = history

        if decision == "accepted":
            updated["candidate_status"] = (
                "accepted_pending_application"
            )
        elif decision == (
            "accepted_with_reservation"
        ):
            updated["candidate_status"] = (
                "accepted_with_reservation_"
                "pending_application"
            )
        else:
            updated["candidate_status"] = "rejected"

        previous_hash = candidate[
            "candidate_sha256"
        ]

        updated = _replace_candidate_hash(
            updated,
            previous_hash,
        )

        _write_atomic(
            candidate_path,
            updated,
        )

        fcntl.flock(
            lock.fileno(),
            fcntl.LOCK_UN,
        )

    return {
        "candidate_path": str(candidate_path),
        "candidate_sha256": updated[
            "candidate_sha256"
        ],
        "decision": decision,
        "reviewed": True,
        "already_reviewed": False,
        "written": True,
    }


def _find_matching_encounter(
    journal: dict[str, Any],
    *,
    passage_id: str,
    result_sha256: str,
) -> dict[str, Any] | None:
    encounters = journal.get(
        "encounters",
        [],
    )

    if not isinstance(encounters, list):
        return None

    return next(
        (
            encounter
            for encounter in encounters
            if (
                isinstance(encounter, dict)
                and encounter.get("passage_id")
                == passage_id
                and encounter.get("result_sha256")
                == result_sha256
            )
        ),
        None,
    )


def apply_candidate(
    *,
    candidate_path: Path,
    journals_root: Path,
    applied_by: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    _require_legacy_external_reading_write(
        "apply_candidate"
    )

    applied_by = str(applied_by).strip()

    if not applied_by:
        raise ReadingCandidateError(
            "L’auteur de l’application est requis."
        )

    lock_path = candidate_path.with_suffix(
        candidate_path.suffix + ".lock"
    )

    with lock_path.open(
        "a+",
        encoding="utf-8",
    ) as lock:
        fcntl.flock(
            lock.fileno(),
            fcntl.LOCK_EX,
        )

        candidate, verification = (
            verify_candidate(candidate_path)
        )

        review = candidate.get("review", {})

        if not isinstance(review, dict):
            raise ReadingCandidateError(
                "Revue humaine absente."
            )

        decision = review.get("decision")

        if decision not in ACCEPTED_DECISIONS:
            raise ReadingCandidateError(
                "La candidate n’est pas acceptée."
            )

        if (
            review.get(
                "explicit_human_confirmation"
            )
            is not True
        ):
            raise ReadingCandidateError(
                "Confirmation humaine absente."
            )

        journal_id = verification["journal_id"]
        passage_id = verification["passage_id"]
        result_sha256 = verification[
            "result_sha256"
        ]

        journal_path = (
            journals_root
            / f"{journal_id}.json"
        )

        if not journal_path.is_file():
            raise ReadingCandidateError(
                "Journal de lecture introuvable."
            )

        journal = _read_json(journal_path)

        existing_encounter = (
            _find_matching_encounter(
                journal,
                passage_id=passage_id,
                result_sha256=result_sha256,
            )
        )

        application = candidate.get(
            "application",
            {},
        )

        already_marked = (
            isinstance(application, dict)
            and application.get("applied")
            is True
        )

        if already_marked:
            if existing_encounter is None:
                raise ReadingCandidateError(
                    "Candidate marquée appliquée "
                    "sans rencontre correspondante."
                )

            return {
                **verification,
                "applied": True,
                "already_applied": True,
                "written": False,
                "encounter_id": (
                    existing_encounter.get(
                        "encounter_id"
                    )
                ),
            }

        application_time = (
            now or datetime.now(timezone.utc)
        )

        _, record_report = (
            record_validated_inference_result(
                journals_root=journals_root,
                journal_id=journal_id,
                request=candidate["request"],
                validated_result=candidate[
                    "validated_result"
                ],
                committed_by=applied_by,
                now=application_time,
                commit=True,
            )
        )

        journal_after = _read_json(
            journal_path
        )

        encounter = _find_matching_encounter(
            journal_after,
            passage_id=passage_id,
            result_sha256=result_sha256,
        )

        if encounter is None:
            raise ReadingCandidateError(
                "La rencontre validée n’a pas "
                "été retrouvée après application."
            )

        timestamp = _utc_now(
            application_time
        )

        application_event = {
            "applied": True,
            "applied_at_utc": timestamp,
            "applied_by": applied_by,
            "journal_id": journal_id,
            "passage_id": passage_id,
            "encounter_id": encounter.get(
                "encounter_id"
            ),
            "record_report": record_report,
            "external_action_performed": False,
        }

        updated = deepcopy(candidate)

        history = list(
            updated.get(
                "application_history",
                [],
            )
        )
        history.append(application_event)

        updated["application"] = (
            application_event
        )
        updated["application_history"] = history

        if decision == "accepted":
            updated["candidate_status"] = (
                "accepted_applied"
            )
        else:
            updated["candidate_status"] = (
                "accepted_with_reservation_applied"
            )

        updated["claims"] = {
            "journal_modified": True,
            "encounter_recorded": True,
            "reflection_status": (
                "provisional_recorded"
            ),
            "doctrine_adopted": False,
            "subjective_experience_claimed": False,
            "external_action_performed": False,
        }

        previous_hash = candidate[
            "candidate_sha256"
        ]

        updated = _replace_candidate_hash(
            updated,
            previous_hash,
        )

        _write_atomic(
            candidate_path,
            updated,
        )

        fcntl.flock(
            lock.fileno(),
            fcntl.LOCK_UN,
        )

    return {
        "candidate_path": str(candidate_path),
        "candidate_sha256": updated[
            "candidate_sha256"
        ],
        "result_sha256": result_sha256,
        "applied": True,
        "already_applied": False,
        "written": True,
        "encounter_id": encounter.get(
            "encounter_id"
        ),
        "record_report": record_report,
    }
