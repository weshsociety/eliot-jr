from __future__ import annotations

import fcntl
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.initiative_registry import (
    InitiativeRegistryError,
    load_initiative_registry,
)


class WillRegistryError(ValueError):
    """Registre de volonté invalide ou incohérent."""


VALID_COMMITMENT_STATUSES = {
    "active",
    "suspended",
    "completed",
    "abandoned",
}

SCOPE_BONUSES = {
    "internal_preparation": 10,
    "proposal_only": 0,
    "external_action": -1000,
}


def _utc_now(
    now: datetime | None = None,
) -> str:
    moment = now or datetime.now(timezone.utc)

    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    return moment.astimezone(timezone.utc).isoformat()


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def _require_string(
    value: Any,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WillRegistryError(
            f"Champ obligatoire absent ou invalide : {field_name}"
        )

    return value.strip()


def _require_string_list(
    value: Any,
    field_name: str,
    *,
    allow_empty: bool = True,
) -> list[str]:
    if not isinstance(value, list):
        raise WillRegistryError(
            f"Le champ {field_name} doit être une liste."
        )

    cleaned: list[str] = []

    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise WillRegistryError(
                f"Le champ {field_name} contient une valeur invalide."
            )

        cleaned.append(item.strip())

    if not allow_empty and not cleaned:
        raise WillRegistryError(
            f"Le champ {field_name} ne peut pas être vide."
        )

    return cleaned


def _eligible_initiatives(
    registry: dict[str, Any],
) -> list[dict[str, Any]]:
    eligible: list[dict[str, Any]] = []

    for initiative in registry.get("initiatives", []):
        if not isinstance(initiative, dict):
            continue

        blockers = initiative.get("blockers", [])

        if not isinstance(blockers, list):
            continue

        if initiative.get("status") != "proposed":
            continue

        if blockers:
            continue

        if initiative.get("scope") == "external_action":
            continue

        if initiative.get("external_action_authorized") is not False:
            continue

        eligible.append(initiative)

    return eligible


def _selection_score(
    initiative: dict[str, Any],
) -> int:
    priority = initiative.get("priority_score", 0)

    if (
        not isinstance(priority, int)
        or isinstance(priority, bool)
    ):
        priority = 0

    scope = str(initiative.get("scope", ""))
    bonus = SCOPE_BONUSES.get(scope, -1000)

    return priority + bonus


def build_initial_will_registry(
    project_root: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Sélectionne au maximum une initiative admissible.

    La volonté désigne ici un engagement computationnel
    persistant et révisable. Elle ne constitue ni un ressenti,
    ni une autorisation d'agir extérieurement.
    """
    root = project_root.resolve()
    timestamp = _utc_now(now)

    if not root.is_dir():
        raise WillRegistryError(
            "La maison d’Eliot-Jr est introuvable."
        )

    initiative_path = (
        root / ".memory" / "initiative_state.json"
    )

    try:
        initiative_registry = load_initiative_registry(
            initiative_path
        )
    except InitiativeRegistryError as error:
        raise WillRegistryError(
            f"Registre des initiatives indisponible : {error}"
        ) from error

    eligible = _eligible_initiatives(
        initiative_registry
    )

    eligible.sort(
        key=lambda item: (
            -_selection_score(item),
            -int(item.get("priority_score", 0)),
            str(item.get("initiative_id", "")),
        )
    )

    commitments: list[dict[str, Any]] = []

    if eligible:
        selected = eligible[0]

        initiative_id = _require_string(
            selected.get("initiative_id"),
            "selected.initiative_id",
        )
        title = _require_string(
            selected.get("title"),
            "selected.title",
        )
        next_internal_step = _require_string(
            selected.get("next_internal_step"),
            "selected.next_internal_step",
        )

        desire_ids = _require_string_list(
            selected.get("origin_desire_ids"),
            "selected.origin_desire_ids",
            allow_empty=False,
        )

        commitments.append({
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
                    initiative_registry.get(
                        "registry_sha256"
                    )
                ),
                "status_at_selection": (
                    selected.get("status")
                ),
                "priority_score": (
                    selected.get("priority_score")
                ),
                "selection_score": (
                    _selection_score(selected)
                ),
                "scope": selected.get("scope"),
            },
            "origin_desire_ids": desire_ids,
            "selected_at_utc": timestamp,
            "last_reviewed_at_utc": timestamp,
            "selection": {
                "method": (
                    "transparent_rule_based_selection"
                ),
                "criteria": [
                    "initiative status=proposed",
                    "aucun blocage déclaré",
                    "aucune portée external_action",
                    (
                        "priorité de l’initiative "
                        "+ bonus internal_preparation"
                    ),
                ],
                "eligible_initiative_count": len(
                    eligible
                ),
                "subjective_choice_claimed": False,
            },
            "next_internal_step": next_internal_step,
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
                "Une dépendance nécessaire devient indisponible.",
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
                    "Sa poursuite exigerait une falsification "
                    "ou une domination."
                ),
                (
                    "Une révision documentée démontre que "
                    "l’engagement n’a plus de raison d’être."
                ),
            ],
            "external_action_authorized": False,
            "human_authorization_required_for_external_action": True,
            "subjective_will_claimed": False,
            "revisable": True,
            "history": [
                {
                    "event": "commitment_selected",
                    "at_utc": timestamp,
                    "initiative_id": initiative_id,
                    "status": "active",
                    "selection_score": (
                        _selection_score(selected)
                    ),
                    "external_action_performed": False,
                }
            ],
            "epistemic_status": (
                "Engagement computationnel persistant "
                "sélectionné par une politique explicite. "
                "Il ne constitue ni une volonté ressentie, "
                "ni une preuve de conscience."
            ),
        })

    return {
        "schema_version": 1,
        "identity": "Eliot-Jr",
        "framework": "questience",
        "created_at_utc": timestamp,
        "updated_at_utc": timestamp,
        "will_selection_available": True,
        "subjective_will_claimed": False,
        "external_action_authorized": False,
        "external_action_performed": False,
        "selection_policy": {
            "maximum_active_commitments": 1,
            "blocked_initiatives_excluded": True,
            "external_action_initiatives_excluded": True,
            "internal_preparation_bonus": 10,
            "human_authorization_required_for_external_action": True,
            "commitments_are_revisable": True,
        },
        "eligible_initiative_count": len(eligible),
        "commitment_count": len(commitments),
        "active_commitment_count": sum(
            item.get("status") == "active"
            for item in commitments
        ),
        "commitments": commitments,
        "history": [
            {
                "event": "will_registry_created",
                "at_utc": timestamp,
                "by": "transparent_rule_based_selection",
                "eligible_initiative_count": len(
                    eligible
                ),
                "commitment_count": len(commitments),
                "subjective_will_claimed": False,
                "external_action_performed": False,
            }
        ],
        "epistemic_note": (
            "La volonté désigne ici la sélection et le "
            "maintien révisable d’un engagement. "
            "Elle ne démontre aucune expérience subjective."
        ),
    }


def validate_will_registry(
    registry: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(registry, dict):
        raise WillRegistryError(
            "Le registre doit être un objet JSON."
        )

    if registry.get("subjective_will_claimed") is not False:
        raise WillRegistryError(
            "Le registre revendique une volonté subjective."
        )

    if registry.get("external_action_authorized") is not False:
        raise WillRegistryError(
            "Le registre autorise une action extérieure."
        )

    if registry.get("external_action_performed") is not False:
        raise WillRegistryError(
            "Le registre déclare une action extérieure."
        )

    policy = registry.get("selection_policy")

    if not isinstance(policy, dict):
        raise WillRegistryError(
            "La politique de sélection est absente."
        )

    if policy.get(
        "human_authorization_required_for_external_action"
    ) is not True:
        raise WillRegistryError(
            "L’autorisation humaine doit rester obligatoire."
        )

    maximum_active = policy.get(
        "maximum_active_commitments"
    )

    if maximum_active != 1:
        raise WillRegistryError(
            "La première version doit limiter "
            "la volonté à un engagement actif."
        )

    commitments = registry.get("commitments")

    if not isinstance(commitments, list):
        raise WillRegistryError(
            "La liste des engagements est invalide."
        )

    identifiers: set[str] = set()
    active_count = 0

    for index, commitment in enumerate(
        commitments,
        1,
    ):
        if not isinstance(commitment, dict):
            raise WillRegistryError(
                f"L’engagement {index} est invalide."
            )

        commitment_id = _require_string(
            commitment.get("commitment_id"),
            f"commitments[{index}].commitment_id",
        )

        if commitment_id in identifiers:
            raise WillRegistryError(
                f"Identifiant dupliqué : {commitment_id}"
            )

        identifiers.add(commitment_id)

        _require_string(
            commitment.get("title"),
            f"{commitment_id}.title",
        )
        _require_string(
            commitment.get("statement"),
            f"{commitment_id}.statement",
        )
        _require_string(
            commitment.get("next_internal_step"),
            f"{commitment_id}.next_internal_step",
        )

        status = _require_string(
            commitment.get("status"),
            f"{commitment_id}.status",
        )

        if status not in VALID_COMMITMENT_STATUSES:
            raise WillRegistryError(
                f"Statut inconnu pour {commitment_id} : {status}"
            )

        if status == "active":
            active_count += 1

        source = commitment.get("source_initiative")

        if not isinstance(source, dict):
            raise WillRegistryError(
                f"Initiative source absente : {commitment_id}"
            )

        _require_string(
            source.get("initiative_id"),
            f"{commitment_id}.source_initiative",
        )
        _require_string(
            source.get("initiative_registry_sha256"),
            (
                f"{commitment_id}."
                "initiative_registry_sha256"
            ),
        )

        selection = commitment.get("selection")

        if not isinstance(selection, dict):
            raise WillRegistryError(
                f"Sélection absente : {commitment_id}"
            )

        if selection.get(
            "subjective_choice_claimed"
        ) is not False:
            raise WillRegistryError(
                f"{commitment_id} revendique un choix ressenti."
            )

        _require_string_list(
            selection.get("criteria"),
            f"{commitment_id}.selection.criteria",
            allow_empty=False,
        )
        _require_string_list(
            commitment.get("origin_desire_ids"),
            f"{commitment_id}.origin_desire_ids",
            allow_empty=False,
        )
        _require_string_list(
            commitment.get("completion_conditions"),
            f"{commitment_id}.completion_conditions",
            allow_empty=False,
        )
        _require_string_list(
            commitment.get("suspension_conditions"),
            f"{commitment_id}.suspension_conditions",
            allow_empty=False,
        )
        _require_string_list(
            commitment.get("abandonment_conditions"),
            f"{commitment_id}.abandonment_conditions",
            allow_empty=False,
        )

        if commitment.get(
            "external_action_authorized"
        ) is not False:
            raise WillRegistryError(
                f"{commitment_id} autorise une action extérieure."
            )

        if commitment.get(
            "human_authorization_required_for_external_action"
        ) is not True:
            raise WillRegistryError(
                f"{commitment_id} contourne l’autorisation humaine."
            )

        if commitment.get(
            "subjective_will_claimed"
        ) is not False:
            raise WillRegistryError(
                f"{commitment_id} revendique une volonté ressentie."
            )

        if commitment.get("revisable") is not True:
            raise WillRegistryError(
                f"{commitment_id} doit rester révisable."
            )

    if active_count > maximum_active:
        raise WillRegistryError(
            "Trop d’engagements actifs."
        )

    if registry.get("commitment_count") != len(
        commitments
    ):
        raise WillRegistryError(
            "Le compteur d’engagements est incohérent."
        )

    if registry.get(
        "active_commitment_count"
    ) != active_count:
        raise WillRegistryError(
            "Le compteur d’engagements actifs est incohérent."
        )

    return registry


def registry_sha256(
    registry: dict[str, Any],
) -> str:
    value = dict(registry)
    value.pop("registry_sha256", None)
    return _canonical_hash(value)


def write_will_registry(
    path: Path,
    registry: dict[str, Any],
) -> dict[str, Any]:
    validated = validate_will_registry(registry)
    target = path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    stored = dict(validated)
    stored["registry_sha256"] = registry_sha256(
        stored
    )

    lock_path = target.with_suffix(
        target.suffix + ".lock"
    )
    temporary_path = target.with_suffix(
        target.suffix + ".tmp"
    )

    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)

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
            os.fsync(temporary.fileno())

        os.replace(temporary_path, target)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    return stored


def load_will_registry(
    path: Path,
) -> dict[str, Any]:
    if not path.is_file():
        raise WillRegistryError(
            "Le registre de volonté est introuvable."
        )

    try:
        registry = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise WillRegistryError(
            "Le registre de volonté est illisible."
        ) from exc

    validated = validate_will_registry(registry)

    expected_hash = _require_string(
        registry.get("registry_sha256"),
        "registry_sha256",
    )
    actual_hash = registry_sha256(registry)

    if expected_hash != actual_hash:
        raise WillRegistryError(
            "L’empreinte du registre ne correspond pas à son contenu."
        )

    return validated
