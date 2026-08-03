#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA_ROOT = (
    ROOT
    / "investigations"
    / "epstein_trou_de_souris"
    / "schemas"
)

SCHEMA_FILES = {
    "relation_candidate": "relation_candidate.schema.json",
    "encounter_packet": "encounter_packet.schema.json",
}


class InvestigationSchemaError(ValueError):
    """Document d’enquête invalide, incohérent ou non traçable."""


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        canonical_json(value).encode("utf-8")
    ).hexdigest()


def load_schema(
    schema_name: str,
    *,
    schema_root: Path | None = None,
) -> dict[str, Any]:
    if schema_name not in SCHEMA_FILES:
        raise InvestigationSchemaError(
            f"Schéma inconnu : {schema_name}"
        )

    root = schema_root or DEFAULT_SCHEMA_ROOT
    path = root / SCHEMA_FILES[schema_name]

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise InvestigationSchemaError(
            f"Schéma introuvable : {path}"
        ) from error
    except json.JSONDecodeError as error:
        raise InvestigationSchemaError(
            f"Schéma JSON corrompu : {path}"
        ) from error

    if not isinstance(payload, dict):
        raise InvestigationSchemaError(
            f"Le schéma doit être un objet : {path}"
        )

    try:
        Draft202012Validator.check_schema(payload)
    except SchemaError as error:
        raise InvestigationSchemaError(
            f"Schéma Draft 2020-12 invalide : {path}: {error.message}"
        ) from error

    return payload


def _format_error(error: ValidationError) -> str:
    path = "$"
    for part in error.absolute_path:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"

    return f"{path}: {error.message}"


def _validate_json_schema(
    instance: Any,
    schema_name: str,
    *,
    schema_root: Path | None = None,
) -> None:
    schema = load_schema(
        schema_name,
        schema_root=schema_root,
    )
    validator = Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    )
    errors = sorted(
        validator.iter_errors(instance),
        key=lambda item: (
            tuple(str(part) for part in item.absolute_path),
            item.message,
        ),
    )

    if errors:
        details = "; ".join(
            _format_error(error)
            for error in errors[:8]
        )
        raise InvestigationSchemaError(
            f"{schema_name} invalide : {details}"
        )


def relation_identity_payload(
    relation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": relation.get("schema"),
        "investigation_id": relation.get("investigation_id"),
        "subject": deepcopy(relation.get("subject")),
        "predicate": deepcopy(relation.get("predicate")),
        "object": deepcopy(relation.get("object")),
        "basis": relation.get("basis"),
        "source": deepcopy(relation.get("source")),
        "qualifiers": deepcopy(relation.get("qualifiers")),
    }


def expected_relation_id(
    relation: dict[str, Any],
) -> str:
    return "rel_" + canonical_sha256(
        relation_identity_payload(relation)
    )[:24]


def relation_candidate_payload(
    relation: dict[str, Any],
) -> dict[str, Any]:
    payload = deepcopy(relation)
    payload.pop("candidate_sha256", None)
    payload.pop("review", None)
    payload.pop("status", None)
    return payload


def expected_relation_candidate_sha256(
    relation: dict[str, Any],
) -> str:
    return canonical_sha256(
        relation_candidate_payload(relation)
    )


def encounter_packet_payload(
    packet: dict[str, Any],
) -> dict[str, Any]:
    payload = deepcopy(packet)
    payload.pop("packet_sha256", None)
    return payload


def expected_encounter_packet_sha256(
    packet: dict[str, Any],
) -> str:
    return canonical_sha256(
        encounter_packet_payload(packet)
    )


def expected_encounter_packet_id(
    packet: dict[str, Any],
) -> str:
    identity = {
        "schema": packet.get("schema"),
        "investigation_id": packet.get("investigation_id"),
        "relation_id": packet.get("relation_id"),
        "relation_candidate_sha256": packet.get(
            "relation_candidate_sha256"
        ),
        "reviewed_candidate_sha256": (
            packet.get("review", {}) or {}
        ).get("reviewed_candidate_sha256"),
    }
    return "enc_" + canonical_sha256(identity)[:24]


def validate_relation_candidate(
    relation: Any,
    *,
    schema_root: Path | None = None,
) -> dict[str, Any]:
    _validate_json_schema(
        relation,
        "relation_candidate",
        schema_root=schema_root,
    )

    if not isinstance(relation, dict):
        raise InvestigationSchemaError(
            "La relation doit être un objet."
        )

    source = relation["source"]

    if source["line_end"] < source["line_start"]:
        raise InvestigationSchemaError(
            "source.line_end doit être supérieur ou égal à line_start."
        )

    if (
        source["source_state"] == "unchanged"
        and source["source_current_sha256"]
        != source["source_sha256"]
    ):
        raise InvestigationSchemaError(
            "Une source déclarée inchangée doit conserver la même empreinte."
        )

    expected_id = expected_relation_id(relation)
    if relation["relation_id"] != expected_id:
        raise InvestigationSchemaError(
            "relation_id ne correspond pas au contenu sourcé."
        )

    expected_hash = expected_relation_candidate_sha256(relation)
    if relation["candidate_sha256"] != expected_hash:
        raise InvestigationSchemaError(
            "candidate_sha256 ne correspond pas à la relation."
        )

    review = relation.get("review")
    if review is not None:
        if (
            review["reviewed_candidate_sha256"]
            != relation["candidate_sha256"]
        ):
            raise InvestigationSchemaError(
                "La revue ne porte pas sur cette version candidate."
            )

        if relation["status"] != review["decision"]:
            raise InvestigationSchemaError(
                "Le statut de relation doit correspondre à la décision de revue."
            )

    if (
        relation["status"] == "accepted_for_encounter"
        and source["source_state"] != "unchanged"
    ):
        raise InvestigationSchemaError(
            "Une source modifiée ou absente ne peut pas être acceptée pour rencontre."
        )

    return deepcopy(relation)


def validate_encounter_packet(
    packet: Any,
    *,
    schema_root: Path | None = None,
) -> dict[str, Any]:
    _validate_json_schema(
        packet,
        "encounter_packet",
        schema_root=schema_root,
    )

    if not isinstance(packet, dict):
        raise InvestigationSchemaError(
            "Le paquet de rencontre doit être un objet."
        )

    source = packet["source_attribution"]
    if source["line_end"] < source["line_start"]:
        raise InvestigationSchemaError(
            "source_attribution.line_end doit être supérieur ou égal à line_start."
        )

    if (
        packet["review"]["reviewed_candidate_sha256"]
        != packet["relation_candidate_sha256"]
    ):
        raise InvestigationSchemaError(
            "Le paquet ne référence pas la version revue de la relation."
        )

    expected_id = expected_encounter_packet_id(packet)
    if packet["packet_id"] != expected_id:
        raise InvestigationSchemaError(
            "packet_id ne correspond pas à la relation revue."
        )

    expected_hash = expected_encounter_packet_sha256(packet)
    if packet["packet_sha256"] != expected_hash:
        raise InvestigationSchemaError(
            "packet_sha256 ne correspond pas au paquet."
        )

    return deepcopy(packet)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Valide un objet d’enquête Eliot-Jr sans écrire dans les registres."
        )
    )
    parser.add_argument(
        "schema_name",
        choices=("relation_candidate", "encounter_packet"),
    )
    parser.add_argument("json_path", type=Path)
    args = parser.parse_args()

    try:
        instance = json.loads(
            args.json_path.read_text(encoding="utf-8")
        )
        if args.schema_name == "relation_candidate":
            validate_relation_candidate(instance)
        else:
            validate_encounter_packet(instance)
    except (
        OSError,
        json.JSONDecodeError,
        InvestigationSchemaError,
    ) as error:
        print(json.dumps({
            "valid": False,
            "schema": args.schema_name,
            "path": str(args.json_path),
            "error": str(error),
            "memory_written": False,
            "octopus_modified": False,
        }, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps({
        "valid": True,
        "schema": args.schema_name,
        "path": str(args.json_path),
        "memory_written": False,
        "octopus_modified": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
