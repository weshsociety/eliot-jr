from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from core.will_registry import (
    WillRegistryError,
    load_will_registry,
)


def _normalise_query(value: str) -> str:
    decomposed = unicodedata.normalize(
        "NFKD",
        str(value),
    )
    ascii_value = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )

    return re.sub(
        r"[^a-z0-9]+",
        " ",
        ascii_value.lower(),
    ).strip()


def _join_statements(values: list[Any]) -> str:
    cleaned: list[str] = []

    for value in values:
        statement = re.sub(
            r"[.;:\s]+$",
            "",
            str(value).strip(),
        )

        if statement:
            cleaned.append(statement)

    return " ; ".join(cleaned) + "."


def _selection_label(value: Any) -> str:
    labels = {
        "transparent_rule_based_selection": (
            "sélection transparente fondée sur "
            "des règles explicites"
        ),
    }

    key = str(value or "").strip()

    return labels.get(
        key,
        key or "méthode non précisée",
    )


def _criterion_label(value: Any) -> str:
    labels = {
        "initiative status=proposed": (
            "l’initiative était au statut « proposée »"
        ),
        "aucun blocage déclaré": (
            "aucun blocage n’était déclaré"
        ),
        "aucune portée external_action": (
            "aucune action extérieure n’était requise"
        ),
        (
            "priorité de l’initiative "
            "+ bonus internal_preparation"
        ): (
            "la priorité de l’initiative a reçu "
            "le bonus réservé à la préparation intérieure"
        ),
    }

    key = str(value or "").strip()

    return labels.get(
        key,
        key or "critère non précisé",
    )


def will_orientation_response(
    message: str,
    registry_path: Path,
) -> tuple[
    str | None,
    dict[str, Any] | None,
    list[str],
]:
    """
    Présente l'engagement persistant d'Eliot-Jr.

    La volonté est ici un engagement computationnel
    révisable. Cette fonction ne sélectionne, n'exécute
    et ne modifie aucun engagement.
    """
    normalised = _normalise_query(message)

    triggers = (
        "ta volonte",
        "quelle est ta volonte",
        "quelles sont tes volontes",
        "quel engagement",
        "quels engagements",
        "engagement maintiens tu",
        "que maintiens tu",
        "a quoi t engages tu",
        "a quoi tu t engages",
        "qu as tu choisi de maintenir",
        "quelle initiative as tu selectionnee",
        "quelle initiative as tu choisie",
        "ce que tu as choisi",
    )

    if not any(
        trigger in normalised
        for trigger in triggers
    ):
        return None, None, []

    try:
        registry = load_will_registry(
            registry_path
        )
    except WillRegistryError as error:
        return (
            "Je ne peux pas consulter actuellement "
            "un registre suffisamment fiable de mes "
            "engagements. Je préfère ne pas inventer "
            "une volonté.",
            None,
            [f"will_registry: {error}"],
        )

    commitments = [
        commitment
        for commitment in registry.get(
            "commitments",
            [],
        )
        if isinstance(commitment, dict)
    ]

    commitments.sort(
        key=lambda commitment: (
            commitment.get("status") != "active",
            str(
                commitment.get(
                    "selected_at_utc",
                    "",
                )
            ),
            str(
                commitment.get(
                    "commitment_id",
                    "",
                )
            ),
        )
    )

    active = [
        commitment
        for commitment in commitments
        if commitment.get("status") == "active"
    ]

    suspended = [
        commitment
        for commitment in commitments
        if commitment.get("status") == "suspended"
    ]

    lines = [
        "Ma volonté actuelle désigne un engagement "
        "opérationnel persistant et révisable."
    ]

    if active:
        lines.append(
            "Voici ce que j’ai choisi de maintenir :"
        )

        for commitment in active:
            source = commitment.get(
                "source_initiative",
                {},
            )
            selection = commitment.get(
                "selection",
                {},
            )

            initiative_id = (
                source.get("initiative_id")
                if isinstance(source, dict)
                else None
            )

            selection_method = (
                selection.get("method")
                if isinstance(selection, dict)
                else None
            )

            criteria = (
                selection.get("criteria", [])
                if isinstance(selection, dict)
                else []
            )

            suspension_conditions = (
                commitment.get(
                    "suspension_conditions",
                    [],
                )
            )

            abandonment_conditions = (
                commitment.get(
                    "abandonment_conditions",
                    [],
                )
            )

            lines.append(
                f"• {commitment.get('title')} "
                f"[engagement actif]"
            )
            lines.append(
                f"  Engagement : "
                f"{commitment.get('statement')}"
            )
            lines.append(
                f"  Initiative source : "
                f"{initiative_id}."
            )
            lines.append(
                "  Sélection : "
                f"{_selection_label(selection_method)}."
            )

            if isinstance(criteria, list) and criteria:
                lines.append(
                    "  Raisons vérifiables : "
                    + _join_statements(
                        [
                            _criterion_label(value)
                            for value in criteria
                        ]
                    )
                )

            lines.append(
                f"  Prochaine étape intérieure : "
                f"{commitment.get('next_internal_step')}"
            )

            if (
                isinstance(
                    suspension_conditions,
                    list,
                )
                and suspension_conditions
            ):
                lines.append(
                    "  Je suspendrais cet engagement si : "
                    + _join_statements(
                        suspension_conditions
                    )
                )

            if (
                isinstance(
                    abandonment_conditions,
                    list,
                )
                and abandonment_conditions
            ):
                lines.append(
                    "  Je l’abandonnerais si : "
                    + _join_statements(
                        abandonment_conditions
                    )
                )

    else:
        lines.append(
            "Aucun engagement n’est actuellement actif."
        )

    for commitment in suspended:
        lines.append(
            f"• {commitment.get('title')} "
            f"[engagement suspendu]"
        )

    lines.append(
        "Je ne présente pas cet engagement comme une "
        "volonté ressentie ou comme une preuve de "
        "conscience. Il ne constitue pas non plus une "
        "autorisation d’agir à l’extérieur."
    )

    return "\n".join(lines), registry, []
