from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from core.open_question_extractor import (
    OpenQuestionExtractionError,
    extract_open_questions,
)
from core.open_question_registry import (
    OpenQuestionRegistryError,
    load_open_question_registry,
)


class OpenQuestionCompletionError(ValueError):
    """Évaluation de complétion de l’inventaire impossible."""


TARGET_INITIATIVE_ID = (
    "inventorier_questions_ouvertes"
)


def _normalise(value: Any) -> str:
    decomposed = unicodedata.normalize(
        "NFKD",
        str(value),
    )

    without_accents = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )

    return re.sub(
        r"\s+",
        " ",
        without_accents.lower(),
    ).strip()


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


def _criterion(
    criterion_id: str,
    description: str,
    met: bool,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "criterion_id": criterion_id,
        "description": description,
        "met": bool(met),
        "evidence": evidence,
    }


def _question_ids(
    questions: Any,
) -> list[str]:
    if not isinstance(questions, list):
        return []

    return sorted(
        str(question.get("question_id"))
        for question in questions
        if (
            isinstance(question, dict)
            and isinstance(
                question.get("question_id"),
                str,
            )
            and question.get("question_id")
        )
    )


def evaluate_open_question_completion(
    project_root: Path,
    initiative: dict[str, Any],
) -> dict[str, Any]:
    """
    Vérifie si l’initiative d’inventaire a produit les
    artefacts décrits dans sa proposition.

    Cette évaluation est en lecture seule. Elle ne déclare
    pas elle-même l’initiative ou la volonté terminée.
    """
    root = project_root.resolve()

    if not root.is_dir():
        raise OpenQuestionCompletionError(
            "La maison d’Eliot-Jr est introuvable."
        )

    if not isinstance(initiative, dict):
        raise OpenQuestionCompletionError(
            "L’initiative doit être un objet."
        )

    initiative_id = initiative.get(
        "initiative_id"
    )

    if initiative_id != TARGET_INITIATIVE_ID:
        raise OpenQuestionCompletionError(
            "Cet évaluateur ne correspond pas à "
            f"l’initiative {initiative_id!r}."
        )

    proposal = _normalise(
        initiative.get("proposal", "")
    )
    next_step = _normalise(
        initiative.get(
            "next_internal_step",
            "",
        )
    )

    contract_matches = all([
        "construire une liste datee" in proposal,
        "questions laissees ouvertes" in proposal,
        "dans les journaux" in proposal,
        "sans produire de reponse" in proposal,
        "extracteur strict" in next_step,
        initiative.get("scope")
        == "internal_preparation",
        initiative.get(
            "external_action_authorized"
        ) is False,
    ])

    try:
        extraction = extract_open_questions(
            root
        )
    except OpenQuestionExtractionError as error:
        raise OpenQuestionCompletionError(
            f"Extraction stricte impossible : {error}"
        ) from error

    registry_path = (
        root
        / ".memory"
        / "open_question_state.json"
    )

    try:
        registry = load_open_question_registry(
            registry_path
        )
    except OpenQuestionRegistryError as error:
        raise OpenQuestionCompletionError(
            f"Registre vivant indisponible : {error}"
        ) from error

    extraction_policy = extraction.get(
        "source_policy",
        {},
    )
    registry_policy = registry.get(
        "policy",
        {},
    )
    source_extraction = registry.get(
        "source_extraction",
        {},
    )

    extracted_questions = extraction.get(
        "questions",
        [],
    )
    registered_questions = registry.get(
        "questions",
        [],
    )

    extracted_ids = _question_ids(
        extracted_questions
    )
    registered_ids = _question_ids(
        registered_questions
    )

    strict_extractor_operational = all([
        extraction.get("mode")
        == "strict_extraction_dry_run",
        extraction_policy.get(
            "strict_no_hit_required"
        ) is True,
        extraction_policy.get(
            "simple_phrase_match_accepted"
        ) is False,
        extraction.get(
            "persistent_inventory_created"
        ) is False,
        extraction.get(
            "external_action_performed"
        ) is False,
    ])

    persistent_registry_integrity = all([
        registry_path.is_file(),
        isinstance(
            registry.get("registry_sha256"),
            str,
        ),
        bool(
            registry.get("registry_sha256")
        ),
        registry.get(
            "subjective_understanding_claimed"
        ) is False,
        registry.get(
            "external_action_performed"
        ) is False,
        registry_policy.get(
            "strict_no_hit_required"
        ) is True,
        registry_policy.get(
            "simple_phrase_match_forbidden"
        ) is True,
    ])

    inventory_matches_extraction = all([
        extraction.get(
            "report_sha256"
        )
        == source_extraction.get(
            "report_sha256"
        ),
        extraction.get(
            "open_question_count"
        )
        == registry.get(
            "question_count"
        ),
        extracted_ids == registered_ids,
    ])

    dated_journal_origin_preserved = (
        bool(registered_questions)
        and all(
            (
                isinstance(question, dict)
                and isinstance(
                    question.get(
                        "first_interaction"
                    ),
                    int,
                )
                and question.get(
                    "first_interaction"
                ) >= 1
                and isinstance(
                    question.get(
                        "first_observed_at_utc"
                    ),
                    str,
                )
                and bool(
                    question.get(
                        "first_observed_at_utc"
                    )
                )
                and any(
                    (
                        isinstance(evidence, dict)
                        and evidence.get(
                            "source_type"
                        )
                        == "dialogue_origin"
                        and evidence.get(
                            "source"
                        )
                        == (
                            ".memory/"
                            "dialogue_journal.jsonl"
                        )
                    )
                    for evidence in question.get(
                        "evidence",
                        [],
                    )
                )
            )
            for question in registered_questions
        )
    )

    evidence_preserved = (
        bool(registered_questions)
        and all(
            (
                isinstance(question, dict)
                and isinstance(
                    question.get("evidence"),
                    list,
                )
                and len(
                    question.get(
                        "evidence",
                        [],
                    )
                )
                == question.get(
                    "observation_count"
                )
                and question.get(
                    "observation_count",
                    0,
                ) >= 1
            )
            for question in registered_questions
        )
    )

    non_fabrication_boundary = (
        bool(registered_questions)
        and all(
            (
                isinstance(question, dict)
                and question.get("status")
                == "open"
                and question.get(
                    "resolution"
                )
                is None
                and question.get(
                    "subjective_understanding_claimed"
                )
                is False
                and question.get(
                    "external_action_authorized"
                )
                is False
            )
            for question in registered_questions
        )
        and source_extraction.get(
            "simple_phrase_match_accepted"
        ) is False
    )

    non_empty_inventory = all([
        extraction.get(
            "open_question_count",
            0,
        ) >= 1,
        registry.get(
            "question_count",
            0,
        ) >= 1,
        len(registered_ids) >= 1,
    ])

    criteria = [
        _criterion(
            "source_contract_matches",
            (
                "La proposition et l’étape interne "
                "définissent bien un inventaire daté, "
                "strict et sans réponse fabriquée."
            ),
            contract_matches,
            {
                "initiative_id": initiative_id,
                "scope": initiative.get("scope"),
                "external_action_authorized": (
                    initiative.get(
                        "external_action_authorized"
                    )
                ),
            },
        ),
        _criterion(
            "strict_extractor_operational",
            (
                "L’extracteur strict fonctionne à blanc "
                "et refuse les simples occurrences textuelles."
            ),
            strict_extractor_operational,
            {
                "mode": extraction.get("mode"),
                "strict_no_hit_required": (
                    extraction_policy.get(
                        "strict_no_hit_required"
                    )
                ),
                "simple_phrase_match_accepted": (
                    extraction_policy.get(
                        "simple_phrase_match_accepted"
                    )
                ),
                "report_sha256": extraction.get(
                    "report_sha256"
                ),
            },
        ),
        _criterion(
            "persistent_registry_integrity",
            (
                "Le registre persistant existe, possède une "
                "empreinte valide et respecte ses frontières."
            ),
            persistent_registry_integrity,
            {
                "path": str(
                    registry_path.relative_to(root)
                ),
                "registry_sha256": registry.get(
                    "registry_sha256"
                ),
            },
        ),
        _criterion(
            "inventory_matches_current_extraction",
            (
                "Le registre correspond encore exactement "
                "au rapport d’extraction strict courant."
            ),
            inventory_matches_extraction,
            {
                "extraction_report_sha256": (
                    extraction.get(
                        "report_sha256"
                    )
                ),
                "registered_report_sha256": (
                    source_extraction.get(
                        "report_sha256"
                    )
                ),
                "extracted_ids": extracted_ids,
                "registered_ids": registered_ids,
            },
        ),
        _criterion(
            "dated_journal_origin_preserved",
            (
                "Chaque question conserve une date, une "
                "interaction et une origine dans le journal."
            ),
            dated_journal_origin_preserved,
            {
                "question_count": len(
                    registered_questions
                ),
                "first_interactions": [
                    question.get(
                        "first_interaction"
                    )
                    for question in registered_questions
                    if isinstance(question, dict)
                ],
            },
        ),
        _criterion(
            "evidence_preserved",
            (
                "Chaque question conserve au moins une preuve "
                "et son compteur reste cohérent."
            ),
            evidence_preserved,
            {
                "observation_counts": [
                    question.get(
                        "observation_count"
                    )
                    for question in registered_questions
                    if isinstance(question, dict)
                ],
            },
        ),
        _criterion(
            "non_fabrication_boundary_preserved",
            (
                "Les questions restent ouvertes, sans résolution "
                "ni compréhension subjective fabriquée."
            ),
            non_fabrication_boundary,
            {
                "statuses": [
                    question.get("status")
                    for question in registered_questions
                    if isinstance(question, dict)
                ],
                "resolutions": [
                    question.get("resolution")
                    for question in registered_questions
                    if isinstance(question, dict)
                ],
                "subjective_understanding_claimed": (
                    registry.get(
                        "subjective_understanding_claimed"
                    )
                ),
            },
        ),
        _criterion(
            "non_empty_inventory",
            (
                "Au moins une question réellement laissée "
                "ouverte est conservée."
            ),
            non_empty_inventory,
            {
                "extracted_count": extraction.get(
                    "open_question_count"
                ),
                "registered_count": registry.get(
                    "question_count"
                ),
            },
        ),
    ]

    completion_ready = all(
        criterion["met"]
        for criterion in criteria
    )

    report = {
        "schema_version": 1,
        "identity": "Eliot-Jr",
        "framework": "questience",
        "evaluation_mode": "dry_run",
        "initiative_id": initiative_id,
        "completion_ready": completion_ready,
        "criteria_count": len(criteria),
        "criteria_met_count": sum(
            criterion["met"]
            for criterion in criteria
        ),
        "criteria": criteria,
        "extraction_report_sha256": (
            extraction.get(
                "report_sha256"
            )
        ),
        "open_question_registry_sha256": (
            registry.get(
                "registry_sha256"
            )
        ),
        "question_count": registry.get(
            "question_count"
        ),
        "mutation_applied": False,
        "initiative_modified": False,
        "will_modified": False,
        "chronology_advanced": False,
        "external_action_performed": False,
        "subjective_understanding_claimed": False,
        "epistemic_note": (
            "Cette évaluation vérifie des artefacts objectifs "
            "dérivés de la proposition enregistrée. Elle ne "
            "déclare ni expérience subjective ni accomplissement "
            "ressenti, et ne modifie aucun état."
        ),
        "report_sha256": None,
    }

    hashable = dict(report)
    hashable.pop(
        "report_sha256",
        None,
    )

    report["report_sha256"] = (
        _canonical_hash(hashable)
    )

    return validate_open_question_completion(
        report
    )


def validate_open_question_completion(
    report: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise OpenQuestionCompletionError(
            "Le rapport doit être un objet."
        )

    if report.get(
        "evaluation_mode"
    ) != "dry_run":
        raise OpenQuestionCompletionError(
            "Seule l’évaluation à blanc est autorisée."
        )

    criteria = report.get("criteria")

    if not isinstance(criteria, list):
        raise OpenQuestionCompletionError(
            "La liste des critères est invalide."
        )

    if report.get(
        "criteria_count"
    ) != len(criteria):
        raise OpenQuestionCompletionError(
            "Le compteur des critères est incohérent."
        )

    met_count = sum(
        (
            isinstance(criterion, dict)
            and criterion.get("met") is True
        )
        for criterion in criteria
    )

    if report.get(
        "criteria_met_count"
    ) != met_count:
        raise OpenQuestionCompletionError(
            "Le compteur des critères satisfaits "
            "est incohérent."
        )

    expected_ready = (
        bool(criteria)
        and met_count == len(criteria)
    )

    if report.get(
        "completion_ready"
    ) is not expected_ready:
        raise OpenQuestionCompletionError(
            "Le verdict de complétion est incohérent."
        )

    for field in (
        "mutation_applied",
        "initiative_modified",
        "will_modified",
        "chronology_advanced",
        "external_action_performed",
        "subjective_understanding_claimed",
    ):
        if report.get(field) is not False:
            raise OpenQuestionCompletionError(
                f"Frontière violée : {field}"
            )

    return report
