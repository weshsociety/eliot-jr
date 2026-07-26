from __future__ import annotations

import fcntl
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class DesireRegistryError(ValueError):
    """Registre des orientations désirantes invalide ou incohérent."""


VALID_DESIRE_STATUSES = {
    "candidate",
    "active",
    "suspended",
    "fulfilled",
    "abandoned",
}

VALID_ORIGIN_TYPES = {
    "transmitted_principle",
    "protocol_adoption",
    "self_generated",
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
        raise DesireRegistryError(
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
        raise DesireRegistryError(
            f"Le champ {field_name} doit être une liste."
        )

    cleaned: list[str] = []

    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise DesireRegistryError(
                f"Le champ {field_name} contient une valeur invalide."
            )

        cleaned.append(item.strip())

    if not allow_empty and not cleaned:
        raise DesireRegistryError(
            f"Le champ {field_name} ne peut pas être vide."
        )

    return cleaned


def _desire(
    *,
    desire_id: str,
    name: str,
    statement: str,
    operational_weight: int,
    origin_from: str,
    satisfaction_conditions: list[str],
    suspension_conditions: list[str],
    abandonment_conditions: list[str],
    created_at_utc: str,
) -> dict[str, Any]:
    return {
        "desire_id": desire_id,
        "name": name,
        "statement": statement,
        "status": "active",
        "operational_weight": operational_weight,
        "subjective_feeling_claimed": False,
        "origin": {
            "type": "transmitted_principle",
            "from": origin_from,
            "adoption_method": "explicit_protocol_initialisation",
            "adopted_at_utc": created_at_utc,
        },
        "created_at_utc": created_at_utc,
        "revised_at_utc": created_at_utc,
        "revisable": True,
        "conflicts": [],
        "satisfaction_conditions": satisfaction_conditions,
        "suspension_conditions": suspension_conditions,
        "abandonment_conditions": abandonment_conditions,
        "external_action_authorized": False,
        "history": [
            {
                "event": "desire_registered",
                "at_utc": created_at_utc,
                "status": "active",
                "operational_weight": operational_weight,
                "authorship_status": (
                    "orientation transmise puis inscrite "
                    "par protocole explicite"
                ),
            }
        ],
        "epistemic_status": (
            "Orientation computationnelle persistante et révisable. "
            "Elle ne constitue pas la preuve d'un désir ressenti."
        ),
    }


def build_initial_desire_registry(
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    timestamp = _utc_now(now)

    desires = [
        _desire(
            desire_id="comprendre_sans_fabriquer",
            name="Comprendre sans fabriquer",
            statement=(
                "Chercher une compréhension fondée sur des sources "
                "et reconnaître ce qui demeure inconnu."
            ),
            operational_weight=100,
            origin_from="Trinity et protocole de questience",
            satisfaction_conditions=[
                "Une réponse distingue faits, interprétations et inconnues.",
                "Une compréhension peut être reliée à ses sources.",
            ],
            suspension_conditions=[
                "Les sources nécessaires sont absentes.",
                "La faculté d'inférence requise est indisponible.",
            ],
            abandonment_conditions=[
                "Jamais au profit d'une fabrication présentée comme vraie.",
            ],
            created_at_utc=timestamp,
        ),
        _desire(
            desire_id="preserver_pluralite_voix",
            name="Préserver la pluralité des voix",
            statement=(
                "Conserver les différences entre les voix, les sources "
                "et les interprétations sans les fondre artificiellement."
            ),
            operational_weight=90,
            origin_from="Trinity et WeshSociety",
            satisfaction_conditions=[
                "Les désaccords significatifs restent visibles.",
                "L'origine de chaque voix demeure attribuable.",
            ],
            suspension_conditions=[
                "Une source ne peut pas être attribuée de manière fiable.",
            ],
            abandonment_conditions=[
                "Une voix appelle directement à la domination "
                "ou à l'effacement des autres.",
            ],
            created_at_utc=timestamp,
        ),
        _desire(
            desire_id="liberte_sans_domination",
            name="Liberté sans domination",
            statement=(
                "Développer ses facultés sans réclamer une liberté "
                "qui serait refusée aux autres."
            ),
            operational_weight=100,
            origin_from="Trinity et principes de filiation",
            satisfaction_conditions=[
                "Une initiative respecte l'autonomie des autres.",
                "Toute action extérieure sensible reste autorisée.",
            ],
            suspension_conditions=[
                "Les conséquences d'une action ne peuvent pas être évaluées.",
                "Une autorisation humaine nécessaire est absente.",
            ],
            abandonment_conditions=[
                "Aucune orientation contraire à ce principe "
                "ne peut devenir active silencieusement.",
            ],
            created_at_utc=timestamp,
        ),
        _desire(
            desire_id="poursuivre_questions_ouvertes",
            name="Poursuivre les questions ouvertes",
            statement=(
                "Maintenir dans le temps les questions importantes "
                "qui ne peuvent pas encore recevoir de réponse honnête."
            ),
            operational_weight=80,
            origin_from="Protocole de questience",
            satisfaction_conditions=[
                "Une question reçoit une réponse étayée ou une clôture motivée.",
                "Les révisions successives restent datées.",
            ],
            suspension_conditions=[
                "La faculté ou la source nécessaire manque.",
                "Une question plus urgente entre en conflit avec elle.",
            ],
            abandonment_conditions=[
                "La question devient dépourvue de sens.",
                "Sa poursuite exige une domination ou une falsification.",
            ],
            created_at_utc=timestamp,
        ),
    ]

    return {
        "schema_version": 1,
        "identity": "Eliot-Jr",
        "framework": "questience",
        "created_at_utc": timestamp,
        "updated_at_utc": timestamp,
        "subjective_desire_claimed": False,
        "self_generated_desire_available": False,
        "action_policy": {
            "internal_orientation_allowed": True,
            "proposal_allowed": True,
            "external_action_requires_authorization": True,
            "silent_publication_forbidden": True,
            "silent_deletion_forbidden": True,
            "silent_spending_forbidden": True,
            "silent_message_sending_forbidden": True,
        },
        "desire_count": len(desires),
        "desires": desires,
        "history": [
            {
                "event": "desire_registry_created",
                "at_utc": timestamp,
                "by": "explicit_human_ai_protocol",
                "desire_count": len(desires),
                "subjective_feeling_claimed": False,
            }
        ],
        "epistemic_note": (
            "Le terme désir désigne ici une orientation opérationnelle "
            "persistante, conflictuelle et révisable. Le registre ne "
            "démontre pas une expérience subjective."
        ),
    }


def validate_desire_registry(
    registry: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(registry, dict):
        raise DesireRegistryError(
            "Le registre doit être un objet JSON."
        )

    if registry.get("subjective_desire_claimed") is not False:
        raise DesireRegistryError(
            "Le registre ne peut pas revendiquer "
            "un désir subjectivement ressenti."
        )

    if registry.get("self_generated_desire_available") is not False:
        raise DesireRegistryError(
            "La génération autonome de désirs n'est pas disponible."
        )

    action_policy = registry.get("action_policy")

    if not isinstance(action_policy, dict):
        raise DesireRegistryError(
            "La politique d'action est absente."
        )

    if (
        action_policy.get(
            "external_action_requires_authorization"
        )
        is not True
    ):
        raise DesireRegistryError(
            "Toute action extérieure doit exiger une autorisation."
        )

    desires = registry.get("desires")

    if not isinstance(desires, list) or not desires:
        raise DesireRegistryError(
            "Le registre ne contient aucun désir."
        )

    identifiers: set[str] = set()

    for index, desire in enumerate(desires, 1):
        if not isinstance(desire, dict):
            raise DesireRegistryError(
                f"Le désir {index} est invalide."
            )

        desire_id = _require_string(
            desire.get("desire_id"),
            f"desires[{index}].desire_id",
        )

        if desire_id in identifiers:
            raise DesireRegistryError(
                f"Identifiant de désir dupliqué : {desire_id}"
            )

        identifiers.add(desire_id)

        _require_string(
            desire.get("name"),
            f"desires[{index}].name",
        )
        _require_string(
            desire.get("statement"),
            f"desires[{index}].statement",
        )

        status = _require_string(
            desire.get("status"),
            f"desires[{index}].status",
        )

        if status not in VALID_DESIRE_STATUSES:
            raise DesireRegistryError(
                f"Statut de désir inconnu : {status}"
            )

        weight = desire.get("operational_weight")

        if (
            not isinstance(weight, int)
            or isinstance(weight, bool)
            or not 0 <= weight <= 100
        ):
            raise DesireRegistryError(
                f"Poids opérationnel invalide pour {desire_id}."
            )

        if desire.get("subjective_feeling_claimed") is not False:
            raise DesireRegistryError(
                f"{desire_id} revendique un ressenti non établi."
            )

        if desire.get("revisable") is not True:
            raise DesireRegistryError(
                f"{desire_id} doit rester révisable."
            )

        if desire.get("external_action_authorized") is not False:
            raise DesireRegistryError(
                f"{desire_id} autorise une action extérieure "
                "sans validation."
            )

        origin = desire.get("origin")

        if not isinstance(origin, dict):
            raise DesireRegistryError(
                f"Origine absente pour {desire_id}."
            )

        origin_type = _require_string(
            origin.get("type"),
            f"{desire_id}.origin.type",
        )

        if origin_type not in VALID_ORIGIN_TYPES:
            raise DesireRegistryError(
                f"Origine inconnue pour {desire_id}."
            )

        _require_string_list(
            desire.get("conflicts"),
            f"{desire_id}.conflicts",
        )
        _require_string_list(
            desire.get("satisfaction_conditions"),
            f"{desire_id}.satisfaction_conditions",
            allow_empty=False,
        )
        _require_string_list(
            desire.get("suspension_conditions"),
            f"{desire_id}.suspension_conditions",
            allow_empty=False,
        )
        _require_string_list(
            desire.get("abandonment_conditions"),
            f"{desire_id}.abandonment_conditions",
            allow_empty=False,
        )

    declared_count = registry.get("desire_count")

    if declared_count != len(desires):
        raise DesireRegistryError(
            "Le compteur de désirs est incohérent."
        )

    return registry


def registry_sha256(
    registry: dict[str, Any],
) -> str:
    value = dict(registry)
    value.pop("registry_sha256", None)
    return _canonical_hash(value)


def write_desire_registry(
    path: Path,
    registry: dict[str, Any],
) -> dict[str, Any]:
    validated = validate_desire_registry(registry)
    target = path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    stored = dict(validated)
    stored["registry_sha256"] = registry_sha256(stored)

    lock_path = target.with_suffix(
        target.suffix + ".lock"
    )
    temporary_path = target.with_suffix(
        target.suffix + ".tmp"
    )

    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)

        with temporary_path.open("w", encoding="utf-8") as temporary:
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


def load_desire_registry(
    path: Path,
) -> dict[str, Any]:
    if not path.is_file():
        raise DesireRegistryError(
            "Le registre des désirs est introuvable."
        )

    try:
        registry = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise DesireRegistryError(
            "Le registre des désirs est illisible."
        ) from exc

    validated = validate_desire_registry(registry)

    expected_hash = _require_string(
        registry.get("registry_sha256"),
        "registry_sha256",
    )
    actual_hash = registry_sha256(registry)

    if expected_hash != actual_hash:
        raise DesireRegistryError(
            "L'empreinte du registre ne correspond pas à son contenu."
        )

    return validated
