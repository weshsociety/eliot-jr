from __future__ import annotations

import copy
import re
from datetime import datetime


_SHA256_PATTERN = re.compile(
    r"^[0-9a-fA-F]{64}$"
)


class EncounterTemporalityError(ValueError):
    pass


def _validate_utc_timestamp(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EncounterTemporalityError(
            "timestamp de revisite invalide"
        )

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise EncounterTemporalityError(
            "timestamp de revisite invalide"
        ) from exc

    if parsed.tzinfo is None:
        raise EncounterTemporalityError(
            "timestamp de revisite sans fuseau"
        )

    return value


def record_revisit(
    temporal_state: dict,
    *,
    revisited_at_utc: str,
    source_sha256: str,
) -> dict:
    """
    Retourne un nouvel état temporel avec une revisite ajoutée.

    Ne modifie jamais l'état fourni.
    Une revisite simple n'implique aucun changement épistémique.
    """

    if not isinstance(temporal_state, dict):
        raise EncounterTemporalityError(
            "temporal_state doit être un objet"
        )

    revisit_count = temporal_state.get(
        "revisit_count"
    )

    revisits = temporal_state.get(
        "revisits"
    )

    if (
        not isinstance(revisit_count, int)
        or isinstance(revisit_count, bool)
        or revisit_count < 0
    ):
        raise EncounterTemporalityError(
            "revisit_count invalide"
        )

    if not isinstance(revisits, list):
        raise EncounterTemporalityError(
            "revisits doit être une liste"
        )

    if revisit_count != len(revisits):
        raise EncounterTemporalityError(
            "revisit_count incohérent avec revisits"
        )

    timestamp = _validate_utc_timestamp(
        revisited_at_utc
    )

    if (
        not isinstance(source_sha256, str)
        or not _SHA256_PATTERN.fullmatch(
            source_sha256
        )
    ):
        raise EncounterTemporalityError(
            "source_sha256 invalide"
        )

    result = copy.deepcopy(
        temporal_state
    )

    result["revisits"].append({
        "revisited_at_utc": timestamp,
        "source_sha256": source_sha256.lower(),
        "epistemic_change": False,
    })

    result["revisit_count"] = (
        revisit_count + 1
    )

    return result
