from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from core.open_question_registry import (
    OpenQuestionRegistryError,
    load_open_question_registry,
)


REGISTRY_COLLISION_TERMS = {
    "desir",
    "desirs",
    "initiative",
    "initiatives",
    "volonte",
    "engagement",
    "revision",
    "faculte",
    "facultes",
}

DIRECT_QUERY_PATTERNS = (
    "quelles questions gardes tu ouvertes",
    "quelle question gardes tu ouverte",
    "quelles sont tes questions ouvertes",
    "quelle est ta question ouverte",
    "quelle est ta question ouverte actuelle",
    "as tu une question ouverte",
    "as tu des questions ouvertes",
    "montre moi tes questions ouvertes",
    "liste tes questions ouvertes",
)

INVESTIGATION_QUERY_PATTERNS = (
    "as tu commence a enqueter sur cette question",
    "as tu commence l enquete sur cette question",
    "enquetes tu sur cette question",
    "ou en est l enquete sur cette question",
    "cette question est elle en cours d enquete",
    "as tu commence a enqueter sur tes questions ouvertes",
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
        r"[^a-z0-9]+",
        " ",
        without_accents.lower(),
    ).strip()


def _query_kind(
    message: str,
) -> str | None:
    normalised = _normalise(message)

    if any(
        pattern in normalised
        for pattern in INVESTIGATION_QUERY_PATTERNS
    ):
        return "investigation"

    words = set(normalised.split())

    # Les questions portant explicitement sur un autre registre
    # doivent rester disponibles pour son propre routeur.
    if words & REGISTRY_COLLISION_TERMS:
        return None

    if any(
        pattern in normalised
        for pattern in DIRECT_QUERY_PATTERNS
    ):
        return "inventory"

    has_question = (
        "question" in words
        or "questions" in words
    )
    has_open = (
        "ouverte" in words
        or "ouvertes" in words
    )
    has_interrogative = bool(
        words
        & {
            "quelle",
            "quelles",
            "as",
            "liste",
            "montre",
        }
    )

    if (
        has_question
        and has_open
        and has_interrogative
    ):
        return "inventory"

    return None


def _plural(
    count: int,
    singular: str,
    plural: str,
) -> str:
    return singular if count == 1 else plural


def _question_lines(
    questions: list[dict[str, Any]],
    *,
    investigation_focus: bool,
) -> list[str]:
    lines: list[str] = []

    for question in questions:
        status = question.get(
            "status",
            "inconnu",
        )
        text = question.get(
            "question",
            "Question sans formulation disponible",
        )
        interaction = question.get(
            "first_interaction"
        )
        observation_count = question.get(
            "observation_count",
            0,
        )
        investigation = question.get(
            "investigation",
            {},
        )

        if not isinstance(
            investigation,
            dict,
        ):
            investigation = {}

        investigation_started = (
            investigation.get("started")
            is True
        )
        resolution = question.get(
            "resolution"
        )

        lines.append(
            f"• {text} [{status}]"
        )

        if interaction is not None:
            lines.append(
                "  Première inscription : "
                f"interaction {interaction}"
            )

        lines.append(
            "  "
            f"{observation_count} "
            f"{_plural(observation_count, 'preuve', 'preuves')} "
            "conservée"
            f"{'' if observation_count == 1 else 's'}"
        )

        if investigation_focus:
            lines.append(
                "  Enquête commencée : "
                f"{'oui' if investigation_started else 'non'}"
            )
            lines.append(
                "  Résolution enregistrée : "
                f"{'oui' if resolution is not None else 'non'}"
            )

    return lines


def open_question_orientation_response(
    message: str,
    registry_path: Path,
) -> tuple[
    str | None,
    dict[str, Any] | None,
    list[str],
]:
    """
    Consulte le registre vivant des questions ouvertes.

    Cette fonction ne relance pas l’extracteur, ne change aucun
    statut et ne démarre aucune enquête.
    """
    query_kind = _query_kind(message)

    if query_kind is None:
        return None, None, []

    try:
        registry = load_open_question_registry(
            registry_path
        )
    except OpenQuestionRegistryError as error:
        return (
            (
                "Je reconnais la demande, mais je ne peux pas "
                "consulter de manière fiable mon registre des "
                "questions ouvertes. Je préfère ne pas inventer "
                "son contenu."
            ),
            None,
            [
                f"open_question_registry: {error}"
            ],
        )

    questions = [
        question
        for question in registry.get(
            "questions",
            [],
        )
        if isinstance(question, dict)
    ]

    unresolved = [
        question
        for question in questions
        if question.get("status") in {
            "open",
            "investigating",
            "suspended",
        }
    ]

    unresolved.sort(
        key=lambda question: (
            question.get(
                "first_interaction"
            )
            is None,
            question.get(
                "first_interaction"
            )
            or 0,
            str(
                question.get(
                    "question_id",
                    "",
                )
            ),
        )
    )

    if not unresolved:
        return (
            (
                "Mon registre vivant ne contient actuellement "
                "aucune question explicitement conservée comme "
                "ouverte. Cela ne signifie pas que toute question "
                "est résolue ; seulement qu’aucune autre n’est "
                "encore inscrite selon le protocole strict."
            ),
            registry,
            [],
        )

    count = len(unresolved)

    if query_kind == "investigation":
        lines = [
            (
                "Je consulte l’état persistant de "
                f"{count} "
                f"{_plural(count, 'question ouverte', 'questions ouvertes')}."
            )
        ]
        lines.extend(
            _question_lines(
                unresolved,
                investigation_focus=True,
            )
        )
        lines.append(
            (
                "Cette consultation ne démarre pas l’enquête, "
                "ne change aucun statut et n’ajoute aucune "
                "résolution."
            )
        )

        return "\n".join(lines), registry, []

    lines = [
        (
            "Je conserve actuellement "
            f"{count} "
            f"{_plural(count, 'question explicitement laissée ouverte', 'questions explicitement laissées ouvertes')} :"
        )
    ]
    lines.extend(
        _question_lines(
            unresolved,
            investigation_focus=False,
        )
    )
    lines.append(
        (
            "Cette inscription conserve un non-savoir daté. "
            "Elle ne constitue ni une réponse acquise, ni une "
            "compréhension subjective, ni le commencement "
            "automatique d’une enquête."
        )
    )

    return "\n".join(lines), registry, []


def structured_open_question_orientation(
    registry: dict[str, Any],
) -> dict[str, Any]:
    questions = registry.get(
        "questions",
        [],
    )

    if not isinstance(questions, list):
        questions = []

    return {
        "question_count": registry.get(
            "question_count"
        ),
        "status_counts": registry.get(
            "status_counts"
        ),
        "subjective_understanding_claimed": (
            registry.get(
                "subjective_understanding_claimed"
            )
        ),
        "external_action_performed": (
            registry.get(
                "external_action_performed"
            )
        ),
        "questions": [
            {
                "question_id": question.get(
                    "question_id"
                ),
                "question": question.get(
                    "question"
                ),
                "status": question.get(
                    "status"
                ),
                "first_interaction": question.get(
                    "first_interaction"
                ),
                "observation_count": question.get(
                    "observation_count"
                ),
                "investigation_started": (
                    question.get(
                        "investigation",
                        {},
                    ).get("started")
                    if isinstance(
                        question.get(
                            "investigation"
                        ),
                        dict,
                    )
                    else None
                ),
                "resolution_recorded": (
                    question.get(
                        "resolution"
                    )
                    is not None
                ),
                "revisable": question.get(
                    "revisable"
                ),
            }
            for question in questions
            if isinstance(question, dict)
        ],
    }
