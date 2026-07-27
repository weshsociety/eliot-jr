from __future__ import annotations

import fcntl
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.open_question_extractor import (
    OpenQuestionExtractionError,
    extract_open_questions,
)


class OpenQuestionRegistryError(ValueError):
    """Registre des questions ouvertes invalide ou incohérent."""


VALID_QUESTION_STATUSES = {
    "open",
    "investigating",
    "answered",
    "suspended",
    "abandoned",
}


def _utc_now(
    now: datetime | None = None,
) -> str:
    moment = now or datetime.now(timezone.utc)

    if moment.tzinfo is None:
        moment = moment.replace(
            tzinfo=timezone.utc
        )

    return moment.astimezone(
        timezone.utc
    ).isoformat()


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(
        encoded
    ).hexdigest()


def _require_string(
    value: Any,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OpenQuestionRegistryError(
            f"Champ obligatoire absent ou invalide : "
            f"{field_name}"
        )

    return value.strip()


def _require_optional_string(
    value: Any,
    field_name: str,
) -> str | None:
    if value is None:
        return None

    return _require_string(
        value,
        field_name,
    )


def _validate_evidence(
    evidence: Any,
    *,
    question_id: str,
    evidence_index: int,
) -> dict[str, Any]:
    if not isinstance(evidence, dict):
        raise OpenQuestionRegistryError(
            f"Preuve invalide pour {question_id}."
        )

    prefix = (
        f"{question_id}.evidence"
        f"[{evidence_index}]"
    )

    _require_string(
        evidence.get("source"),
        f"{prefix}.source",
    )
    _require_string(
        evidence.get("source_type"),
        f"{prefix}.source_type",
    )
    _require_string(
        evidence.get("field_path"),
        f"{prefix}.field_path",
    )
    _require_string(
        evidence.get("rule"),
        f"{prefix}.rule",
    )
    _require_string(
        evidence.get("response_sha256"),
        f"{prefix}.response_sha256",
    )
    _require_string(
        evidence.get("response_excerpt"),
        f"{prefix}.response_excerpt",
    )

    interaction = evidence.get(
        "interaction_number"
    )

    if (
        interaction is not None
        and (
            not isinstance(interaction, int)
            or isinstance(interaction, bool)
            or interaction < 1
        )
    ):
        raise OpenQuestionRegistryError(
            f"Interaction invalide : {prefix}."
        )

    record_number = evidence.get(
        "record_number"
    )

    if (
        record_number is not None
        and (
            not isinstance(record_number, int)
            or isinstance(record_number, bool)
            or record_number < 1
        )
    ):
        raise OpenQuestionRegistryError(
            f"Numéro d’enregistrement invalide : "
            f"{prefix}."
        )

    _require_optional_string(
        evidence.get("timestamp"),
        f"{prefix}.timestamp",
    )

    return evidence


def build_initial_open_question_registry(
    project_root: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Construit le premier registre depuis l’extraction stricte.

    Cette fonction ne modifie ni la chronologie, ni la volonté,
    ni les journaux d’origine.
    """
    root = project_root.resolve()
    created_at_utc = _utc_now(now)

    if not root.is_dir():
        raise OpenQuestionRegistryError(
            "La maison d’Eliot-Jr est introuvable."
        )

    try:
        report = extract_open_questions(root)
    except OpenQuestionExtractionError as error:
        raise OpenQuestionRegistryError(
            f"Extraction stricte impossible : {error}"
        ) from error

    questions: list[dict[str, Any]] = []

    for extracted in report.get(
        "questions",
        [],
    ):
        if not isinstance(extracted, dict):
            continue

        question_id = _require_string(
            extracted.get("question_id"),
            "question.question_id",
        )
        question_text = _require_string(
            extracted.get("question"),
            f"{question_id}.question",
        )

        first_observed = _require_optional_string(
            extracted.get(
                "first_observed_at_utc"
            ),
            f"{question_id}.first_observed_at_utc",
        )

        evidence = [
            dict(item)
            for item in extracted.get(
                "evidence",
                [],
            )
            if isinstance(item, dict)
        ]

        questions.append({
            "question_id": question_id,
            "question": question_text,
            "question_normalised": _require_string(
                extracted.get(
                    "question_normalised"
                ),
                f"{question_id}.question_normalised",
            ),
            "question_sha256": _require_string(
                extracted.get(
                    "question_sha256"
                ),
                f"{question_id}.question_sha256",
            ),
            "status": "open",
            "origin": _require_string(
                extracted.get("origin"),
                f"{question_id}.origin",
            ),
            "first_interaction": extracted.get(
                "first_interaction"
            ),
            "first_observed_at_utc": (
                first_observed
            ),
            "last_observed_at_utc": (
                _require_optional_string(
                    extracted.get(
                        "last_observed_at_utc"
                    ),
                    (
                        f"{question_id}."
                        "last_observed_at_utc"
                    ),
                )
            ),
            "registered_at_utc": created_at_utc,
            "last_reviewed_at_utc": None,
            "observation_count": len(evidence),
            "evidence": evidence,
            "investigation": {
                "started": False,
                "started_at_utc": None,
                "source_count": 0,
                "notes": [],
            },
            "resolution": None,
            "revisable": True,
            "subjective_understanding_claimed": False,
            "external_action_authorized": False,
            "history": [
                {
                    "event": "open_question_registered",
                    "at_utc": created_at_utc,
                    "status": "open",
                    "source_report_sha256": (
                        report["report_sha256"]
                    ),
                    "observation_count": len(
                        evidence
                    ),
                    "understanding_claimed": False,
                    "external_action_performed": False,
                }
            ],
            "epistemic_status": (
                "Question conservée parce qu’une réponse "
                "explicite de non-savoir a été enregistrée. "
                "Son inscription ne constitue ni une réponse, "
                "ni une compréhension."
            ),
        })

    registry = {
        "schema_version": 1,
        "identity": "Eliot-Jr",
        "framework": "questience",
        "created_at_utc": created_at_utc,
        "updated_at_utc": created_at_utc,
        "source_extraction": {
            "mode": report["mode"],
            "report_sha256": report[
                "report_sha256"
            ],
            "dialogue_candidate_count": report[
                "dialogue_candidate_count"
            ],
            "documentary_evidence_count": report[
                "documentary_evidence_count"
            ],
            "simple_phrase_match_accepted": (
                report["source_policy"][
                    "simple_phrase_match_accepted"
                ]
            ),
            "strict_no_hit_required": (
                report["source_policy"][
                    "strict_no_hit_required"
                ]
            ),
        },
        "question_count": len(questions),
        "status_counts": {
            status: sum(
                question["status"] == status
                for question in questions
            )
            for status in sorted(
                VALID_QUESTION_STATUSES
            )
        },
        "questions": questions,
        "policy": {
            "strict_no_hit_required": True,
            "simple_phrase_match_forbidden": True,
            "resolution_requires_evidence": True,
            "silent_status_change_forbidden": True,
            "external_action_requires_authorization": True,
            "questions_remain_revisable": True,
        },
        "subjective_understanding_claimed": False,
        "external_action_performed": False,
        "history": [
            {
                "event": "open_question_registry_created",
                "at_utc": created_at_utc,
                "question_count": len(questions),
                "source_report_sha256": report[
                    "report_sha256"
                ],
                "external_action_performed": False,
            }
        ],
        "epistemic_note": (
            "Ce registre conserve des questions explicitement "
            "laissées ouvertes. Il ne transforme pas leur présence "
            "en connaissance, en réponse ou en expérience subjective."
        ),
    }

    return validate_open_question_registry(
        registry
    )


def validate_open_question_registry(
    registry: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(registry, dict):
        raise OpenQuestionRegistryError(
            "Le registre doit être un objet JSON."
        )

    if registry.get(
        "subjective_understanding_claimed"
    ) is not False:
        raise OpenQuestionRegistryError(
            "Le registre revendique une compréhension subjective."
        )

    if registry.get(
        "external_action_performed"
    ) is not False:
        raise OpenQuestionRegistryError(
            "Le registre déclare une action extérieure."
        )

    policy = registry.get("policy")

    if not isinstance(policy, dict):
        raise OpenQuestionRegistryError(
            "La politique du registre est absente."
        )

    if policy.get(
        "strict_no_hit_required"
    ) is not True:
        raise OpenQuestionRegistryError(
            "L’extraction stricte doit rester obligatoire."
        )

    if policy.get(
        "simple_phrase_match_forbidden"
    ) is not True:
        raise OpenQuestionRegistryError(
            "Une simple occurrence textuelle ne doit "
            "pas devenir une question ouverte."
        )

    if policy.get(
        "external_action_requires_authorization"
    ) is not True:
        raise OpenQuestionRegistryError(
            "Toute action extérieure doit rester autorisée."
        )

    source_extraction = registry.get(
        "source_extraction"
    )

    if not isinstance(
        source_extraction,
        dict,
    ):
        raise OpenQuestionRegistryError(
            "La provenance de l’extraction est absente."
        )

    _require_string(
        source_extraction.get(
            "report_sha256"
        ),
        "source_extraction.report_sha256",
    )

    if source_extraction.get(
        "simple_phrase_match_accepted"
    ) is not False:
        raise OpenQuestionRegistryError(
            "Le registre accepte une détection trop large."
        )

    questions = registry.get("questions")

    if not isinstance(questions, list):
        raise OpenQuestionRegistryError(
            "La liste des questions est invalide."
        )

    identifiers: set[str] = set()
    question_hashes: set[str] = set()
    status_counts = {
        status: 0
        for status in sorted(
            VALID_QUESTION_STATUSES
        )
    }

    for index, question in enumerate(
        questions,
        1,
    ):
        if not isinstance(question, dict):
            raise OpenQuestionRegistryError(
                f"La question {index} est invalide."
            )

        question_id = _require_string(
            question.get("question_id"),
            f"questions[{index}].question_id",
        )

        if question_id in identifiers:
            raise OpenQuestionRegistryError(
                f"Identifiant dupliqué : {question_id}"
            )

        identifiers.add(question_id)

        question_sha = _require_string(
            question.get("question_sha256"),
            f"{question_id}.question_sha256",
        )

        if question_sha in question_hashes:
            raise OpenQuestionRegistryError(
                "Deux questions possèdent la même empreinte."
            )

        question_hashes.add(question_sha)

        _require_string(
            question.get("question"),
            f"{question_id}.question",
        )
        _require_string(
            question.get(
                "question_normalised"
            ),
            f"{question_id}.question_normalised",
        )
        _require_string(
            question.get("origin"),
            f"{question_id}.origin",
        )
        _require_string(
            question.get(
                "registered_at_utc"
            ),
            f"{question_id}.registered_at_utc",
        )

        status = _require_string(
            question.get("status"),
            f"{question_id}.status",
        )

        if status not in VALID_QUESTION_STATUSES:
            raise OpenQuestionRegistryError(
                f"Statut inconnu pour {question_id} : "
                f"{status}"
            )

        status_counts[status] += 1

        first_interaction = question.get(
            "first_interaction"
        )

        if (
            first_interaction is not None
            and (
                not isinstance(
                    first_interaction,
                    int,
                )
                or isinstance(
                    first_interaction,
                    bool,
                )
                or first_interaction < 1
            )
        ):
            raise OpenQuestionRegistryError(
                f"Interaction initiale invalide : "
                f"{question_id}"
            )

        evidence = question.get("evidence")

        if (
            not isinstance(evidence, list)
            or not evidence
        ):
            raise OpenQuestionRegistryError(
                f"Aucune preuve pour {question_id}."
            )

        for evidence_index, item in enumerate(
            evidence,
            1,
        ):
            _validate_evidence(
                item,
                question_id=question_id,
                evidence_index=evidence_index,
            )

        if question.get(
            "observation_count"
        ) != len(evidence):
            raise OpenQuestionRegistryError(
                f"Compteur de preuves incohérent : "
                f"{question_id}"
            )

        if question.get(
            "revisable"
        ) is not True:
            raise OpenQuestionRegistryError(
                f"La question doit rester révisable : "
                f"{question_id}"
            )

        if question.get(
            "subjective_understanding_claimed"
        ) is not False:
            raise OpenQuestionRegistryError(
                f"{question_id} revendique une "
                "compréhension subjective."
            )

        if question.get(
            "external_action_authorized"
        ) is not False:
            raise OpenQuestionRegistryError(
                f"{question_id} autorise une "
                "action extérieure."
            )

        resolution = question.get(
            "resolution"
        )

        if (
            status in {
                "open",
                "investigating",
                "suspended",
            }
            and resolution is not None
        ):
            raise OpenQuestionRegistryError(
                f"{question_id} possède une résolution "
                "alors qu’elle demeure non résolue."
            )

        investigation = question.get(
            "investigation"
        )

        if not isinstance(
            investigation,
            dict,
        ):
            raise OpenQuestionRegistryError(
                f"État d’enquête absent : {question_id}"
            )

        if investigation.get("started") not in {
            True,
            False,
        }:
            raise OpenQuestionRegistryError(
                f"État d’enquête invalide : {question_id}"
            )

    if registry.get(
        "question_count"
    ) != len(questions):
        raise OpenQuestionRegistryError(
            "Le compteur des questions est incohérent."
        )

    if registry.get(
        "status_counts"
    ) != status_counts:
        raise OpenQuestionRegistryError(
            "Les compteurs de statut sont incohérents."
        )

    return registry


def registry_sha256(
    registry: dict[str, Any],
) -> str:
    value = dict(registry)
    value.pop("registry_sha256", None)

    return _canonical_hash(value)


def write_open_question_registry(
    path: Path,
    registry: dict[str, Any],
) -> dict[str, Any]:
    validated = validate_open_question_registry(
        registry
    )

    target = path.resolve()
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    stored = dict(validated)
    stored["registry_sha256"] = (
        registry_sha256(stored)
    )

    lock_path = target.with_suffix(
        target.suffix + ".lock"
    )
    temporary_path = target.with_suffix(
        target.suffix + ".tmp"
    )

    with lock_path.open(
        "a+",
        encoding="utf-8",
    ) as lock:
        fcntl.flock(
            lock.fileno(),
            fcntl.LOCK_EX,
        )

        with temporary_path.open(
            "w",
            encoding="utf-8",
        ) as temporary:
            json.dump(
                stored,
                temporary,
                ensure_ascii=False,
                indent=2,
            )
            temporary.write("\n")
            temporary.flush()
            os.fsync(
                temporary.fileno()
            )

        os.replace(
            temporary_path,
            target,
        )

        fcntl.flock(
            lock.fileno(),
            fcntl.LOCK_UN,
        )

    return stored


def load_open_question_registry(
    path: Path,
) -> dict[str, Any]:
    if not path.is_file():
        raise OpenQuestionRegistryError(
            "Le registre des questions ouvertes "
            "est introuvable."
        )

    try:
        registry = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as error:
        raise OpenQuestionRegistryError(
            "Le registre des questions ouvertes "
            "est illisible."
        ) from error

    validated = validate_open_question_registry(
        registry
    )

    expected_hash = _require_string(
        registry.get("registry_sha256"),
        "registry_sha256",
    )
    actual_hash = registry_sha256(
        registry
    )

    if expected_hash != actual_hash:
        raise OpenQuestionRegistryError(
            "L’empreinte du registre ne correspond "
            "pas à son contenu."
        )

    return validated
