from __future__ import annotations

import copy
from typing import Any, Callable

from core.response_choice import validate_response_choice
from core.response_deliberation_packet import (
    validate_response_deliberation_packet,
)


class ResponseChoiceProductionError(ValueError):
    """Échec explicite de production d'un choix valide."""


ChoiceProducer = Callable[
    [dict[str, Any]],
    dict[str, Any] | None,
]


def produce_response_choice_preview(
    *,
    deliberation_packet: dict[str, Any],
    producer: ChoiceProducer,
) -> dict[str, Any] | None:
    """
    Demande à un producteur injecté de produire éventuellement
    un response_choice à partir d'un paquet pré-choix valide.

    Cette fonction ne fournit aucun choix par défaut.

    Elle ne transforme jamais :
    - None en respond ;
    - une erreur en respond ;
    - une sortie invalide en choix valide.

    Le producteur reçoit une copie du paquet.
    """
    packet = validate_response_deliberation_packet(
        copy.deepcopy(deliberation_packet)
    )

    if not callable(producer):
        raise ResponseChoiceProductionError(
            "producer doit être appelable."
        )

    producer_input = copy.deepcopy(packet)

    try:
        raw_choice = producer(producer_input)
    except Exception as exc:
        raise ResponseChoiceProductionError(
            "Le producteur a échoué sans produire "
            "de choix valide."
        ) from exc

    if raw_choice is None:
        return None

    if not isinstance(raw_choice, dict):
        raise ResponseChoiceProductionError(
            "Le producteur doit renvoyer None ou "
            "un response_choice valide."
        )

    try:
        choice = validate_response_choice(
            copy.deepcopy(raw_choice)
        )
    except ValueError as exc:
        raise ResponseChoiceProductionError(
            "Le producteur a renvoyé un choix invalide."
        ) from exc

    if choice["request_ref"] != packet["request_ref"]:
        raise ResponseChoiceProductionError(
            "Le choix produit concerne une autre demande."
        )

    return choice
