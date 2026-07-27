from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.initiative_registry import (
    InitiativeRegistryError,
    load_initiative_registry,
)
from core.will_registry import (
    WillRegistryError,
    _eligible_initiatives,
    _selection_score,
    load_will_registry,
    registry_sha256,
    validate_will_registry,
    write_will_registry,
)


class WillRenewalError(ValueError):
    """Renouvellement du registre de volonté impossible."""


def _utc_now(
    now: datetime | None = None,
) -> str:
    moment = now or datetime.now(timezone.utc)

    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    return moment.astimezone(
        timezone.utc
    ).isoformat()


def _require_string(
    value: Any,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WillRenewalError(
            f"Champ obligatoire absent : {field_name}"
        )

    return value.strip()


def _require_string_list(
    value: Any,
    field_name: str,
) -> list[str]:
    if not isinstance(value, list) or not value:
        raise WillRenewalError(
            f"Liste obligatoire absente : {field_name}"
        )

    cleaned: list[str] = []

    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise WillRenewalError(
                f"Valeur invalide dans {field_name}."
            )

        cleaned.append(item.strip())

    return cleaned


def _commitment_index(
    registry: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    for commitment in registry.get(
        "commitments",
        [],
    ):
        if not isinstance(commitment, dict):
            continue

        commitment_id = commitment.get(
            "commitment_id"
        )

        if isinstance(commitment_id, str):
            result[commitment_id] = commitment

    return result


def _referenced_initiatives(
    registry: dict[str, Any],
) -> set[str]:
    result: set[str] = set()

    for commitment in registry.get(
        "commitments",
        [],
    ):
        if not isinstance(commitment, dict):
            continue

        source = commitment.get(
            "source_initiative"
        )

        if not isinstance(source, dict):
            continue

        initiative_id = source.get(
            "initiative_id"
        )

        if (
            isinstance(initiative_id, str)
            and initiative_id.strip()
        ):
            result.add(
                initiative_id.strip()
            )

    return result


def _ranked_unengaged_candidates(
    initiative_registry: dict[str, Any],
    will_registry: dict[str, Any],
) -> list[dict[str, Any]]:
    referenced = _referenced_initiatives(
        will_registry
    )

    candidates = [
        initiative
        for initiative in _eligible_initiatives(
            initiative_registry
        )
        if initiative.get(
            "initiative_id"
        ) not in referenced
    ]

    candidates.sort(
        key=lambda item: (
            -_selection_score(item),
            -int(
                item.get(
                    "priority_score",
                    0,
                )
            ),
            str(
                item.get(
                    "initiative_id",
                    "",
                )
            ),
        )
    )

    return candidates


def _build_commitment(
    *,
    initiative: dict[str, Any],
    initiative_registry_sha256: str,
    eligible_count: int,
    selected_at_utc: str,
) -> dict[str, Any]:
    initiative_id = _require_string(
        initiative.get("initiative_id"),
        "initiative.initiative_id",
    )
    title = _require_string(
        initiative.get("title"),
        "initiative.title",
    )
    next_internal_step = _require_string(
        initiative.get(
            "next_internal_step"
        ),
        "initiative.next_internal_step",
    )
    desire_ids = _require_string_list(
        initiative.get(
            "origin_desire_ids"
        ),
        "initiative.origin_desire_ids",
    )

    return {
        "commitment_id": (
            f"engagement_{initiative_id}"
        ),
        "title": title,
        "statement": (
            "Maintenir l’initiative sélectionnée et "
            "poursuivre son étape intérieure vérifiable "
            "tant qu’aucune condition de suspension ou "
            "d’abandon n’est rencontrée."
        ),
        "status": "active",
        "source_initiative": {
            "initiative_id": initiative_id,
            "initiative_registry_sha256": (
                initiative_registry_sha256
            ),
            "status_at_selection": initiative.get(
                "status"
            ),
            "priority_score": initiative.get(
                "priority_score"
            ),
            "selection_score": (
                _selection_score(initiative)
            ),
            "scope": initiative.get("scope"),
        },
        "origin_desire_ids": desire_ids,
        "selected_at_utc": selected_at_utc,
        "last_reviewed_at_utc": (
            selected_at_utc
        ),
        "selection": {
            "method": (
                "transparent_rule_based_renewal"
            ),
            "criteria": [
                "initiative status=proposed",
                "aucun blocage déclaré",
                "aucune portée external_action",
                (
                    "initiative jamais engagée "
                    "auparavant"
                ),
                (
                    "classement déterministe "
                    "par score de sélection"
                ),
            ],
            "eligible_initiative_count": (
                eligible_count
            ),
            "subjective_choice_claimed": False,
        },
        "next_internal_step": (
            next_internal_step
        ),
        "completion_conditions": [
            (
                "L’étape intérieure est réalisée "
                "et son résultat est vérifié."
            ),
            (
                "L’initiative source peut être "
                "déclarée completed sans fabrication."
            ),
        ],
        "suspension_conditions": [
            (
                "Une dépendance nécessaire "
                "devient indisponible."
            ),
            "Un blocage vérifié apparaît.",
            (
                "L’étape entrerait en conflit avec "
                "liberté sans domination."
            ),
            (
                "L’étape exige une action extérieure "
                "non autorisée."
            ),
        ],
        "abandonment_conditions": [
            "L’initiative source est invalidée.",
            (
                "Sa poursuite exigerait une "
                "falsification ou une domination."
            ),
            (
                "Une révision documentée démontre "
                "que l’engagement n’a plus de "
                "raison d’être."
            ),
        ],
        "external_action_authorized": False,
        (
            "human_authorization_required_"
            "for_external_action"
        ): True,
        "subjective_will_claimed": False,
        "revisable": True,
        "history": [
            {
                "event": "commitment_selected",
                "at_utc": selected_at_utc,
                "initiative_id": initiative_id,
                "status": "active",
                "selection_score": (
                    _selection_score(
                        initiative
                    )
                ),
                "selection_mode": (
                    "renewal_append_only"
                ),
                (
                    "application_"
                    "explicitly_requested"
                ): True,
                (
                    "external_action_"
                    "performed"
                ): False,
            }
        ],
        "epistemic_status": (
            "Engagement computationnel persistant "
            "sélectionné par une politique explicite. "
            "Il ne constitue ni une volonté ressentie, "
            "ni une preuve de conscience."
        ),
    }


def renew_will_gate(
    *,
    will_path: Path,
    initiative_path: Path,
    expected_will_registry_sha256: str,
    expected_initiative_registry_sha256: str,
    expected_initiative_id: str,
    commit: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Ajoute au maximum un nouvel engagement actif.

    commit=False ne réalise aucune écriture.
    commit=True modifie uniquement will_state.json.
    """
    expected_will_hash = _require_string(
        expected_will_registry_sha256,
        "expected_will_registry_sha256",
    )
    expected_initiative_hash = (
        _require_string(
            expected_initiative_registry_sha256,
            (
                "expected_initiative_"
                "registry_sha256"
            ),
        )
    )
    initiative_id = _require_string(
        expected_initiative_id,
        "expected_initiative_id",
    )
    commitment_id = (
        f"engagement_{initiative_id}"
    )

    try:
        will_registry = load_will_registry(
            will_path
        )
    except WillRegistryError as error:
        raise WillRenewalError(
            f"Registre de volonté indisponible : {error}"
        ) from error

    try:
        initiative_registry = (
            load_initiative_registry(
                initiative_path
            )
        )
    except InitiativeRegistryError as error:
        raise WillRenewalError(
            "Registre des initiatives "
            f"indisponible : {error}"
        ) from error

    commitments = _commitment_index(
        will_registry
    )
    existing = commitments.get(
        commitment_id
    )

    # L’idempotence est vérifiée avant les contrôles
    # d’empreinte : une relance avec les empreintes
    # antérieures ne peut pas produire de doublon.
    if existing is not None:
        source = existing.get(
            "source_initiative"
        )

        if (
            not isinstance(source, dict)
            or source.get("initiative_id")
            != initiative_id
        ):
            raise WillRenewalError(
                "L’identifiant d’engagement existe "
                "avec une autre initiative source."
            )

        return {
            "commit_requested": commit,
            "expected_initiative_id": (
                initiative_id
            ),
            "commitment_id": commitment_id,
            "already_applied": True,
            "selection_required": False,
            "selection_applied": False,
            "application_record_required": False,
            "application_record_applied": False,
            "current_active_commitment_count": (
                will_registry.get(
                    "active_commitment_count"
                )
            ),
            "target_active_commitment_count": (
                will_registry.get(
                    "active_commitment_count"
                )
            ),
            "eligible_unengaged_count": 0,
            "external_action_performed": False,
            "subjective_will_claimed": False,
            "registry": will_registry,
        }

    if will_registry.get(
        "registry_sha256"
    ) != expected_will_hash:
        raise WillRenewalError(
            "Le registre de volonté a changé. "
            "Un nouvel aperçu est requis."
        )

    if initiative_registry.get(
        "registry_sha256"
    ) != expected_initiative_hash:
        raise WillRenewalError(
            "Le registre des initiatives a changé. "
            "Un nouvel aperçu est requis."
        )

    active_count = will_registry.get(
        "active_commitment_count"
    )

    if active_count != 0:
        raise WillRenewalError(
            "Un engagement actif existe déjà."
        )

    policy = will_registry.get(
        "selection_policy"
    )

    if (
        not isinstance(policy, dict)
        or policy.get(
            "maximum_active_commitments"
        )
        != 1
    ):
        raise WillRenewalError(
            "La politique de volonté est invalide."
        )

    candidates = (
        _ranked_unengaged_candidates(
            initiative_registry,
            will_registry,
        )
    )

    if not candidates:
        raise WillRenewalError(
            "Aucune initiative admissible "
            "et jamais engagée n’est disponible."
        )

    selected = candidates[0]
    selected_id = _require_string(
        selected.get("initiative_id"),
        "selected.initiative_id",
    )

    if selected_id != initiative_id:
        raise WillRenewalError(
            "L’initiative attendue n’est plus "
            "la candidate déterministe de tête."
        )

    timestamp = _utc_now(now)
    candidate = deepcopy(
        will_registry
    )
    new_commitment = _build_commitment(
        initiative=selected,
        initiative_registry_sha256=(
            expected_initiative_hash
        ),
        eligible_count=len(candidates),
        selected_at_utc=timestamp,
    )

    candidate.setdefault(
        "commitments",
        [],
    ).append(new_commitment)

    history = candidate.setdefault(
        "history",
        [],
    )

    if not isinstance(history, list):
        raise WillRenewalError(
            "L’historique du registre "
            "de volonté est invalide."
        )

    history.append({
        "event": "will_renewal_applied",
        "at_utc": timestamp,
        "initiative_id": initiative_id,
        "commitment_id": commitment_id,
        "selection_score": (
            _selection_score(selected)
        ),
        "eligible_unengaged_count": (
            len(candidates)
        ),
        "previous_active_commitment_count": 0,
        "new_active_commitment_count": 1,
        "renewal_mode": "append_only",
        "application_explicitly_requested": True,
        "external_action_performed": False,
        "subjective_will_claimed": False,
    })

    candidate["updated_at_utc"] = timestamp
    candidate[
        "eligible_initiative_count"
    ] = len(candidates)
    candidate["commitment_count"] = len(
        candidate["commitments"]
    )
    candidate[
        "active_commitment_count"
    ] = sum(
        isinstance(commitment, dict)
        and commitment.get("status")
        == "active"
        for commitment in candidate[
            "commitments"
        ]
    )
    candidate["registry_sha256"] = (
        registry_sha256(candidate)
    )

    try:
        validate_will_registry(candidate)
    except WillRegistryError as error:
        raise WillRenewalError(
            f"État candidat invalide : {error}"
        ) from error

    stored = candidate

    if commit:
        try:
            stored = write_will_registry(
                will_path,
                candidate,
            )
        except WillRegistryError as error:
            raise WillRenewalError(
                "Écriture du registre impossible : "
                f"{error}"
            ) from error

    return {
        "commit_requested": commit,
        "expected_initiative_id": (
            initiative_id
        ),
        "commitment_id": commitment_id,
        "already_applied": False,
        "selection_required": True,
        "selection_applied": bool(commit),
        "application_record_required": True,
        "application_record_applied": (
            bool(commit)
        ),
        "current_active_commitment_count": 0,
        "target_active_commitment_count": 1,
        "eligible_unengaged_count": (
            len(candidates)
        ),
        "selection_score": (
            _selection_score(selected)
        ),
        "external_action_performed": False,
        "subjective_will_claimed": False,
        "registry": stored,
    }
