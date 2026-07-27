from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any


class AttributionSchemaError(ValueError):
    """Attribution commune invalide ou incohérente."""


SCHEMA_VERSION = 1

VALID_ORIGIN_SYSTEMS = {
    "octopus",
    "open_questions",
    "reading",
    "library",
    "dialogue",
}

VALID_CONTRIBUTOR_ROLES = {
    "author",
    "translator",
    "provided_by",
    "registered_by",
}

VALID_LOCATOR_FIELDS = {
    "node_id",
    "question_id",
    "journal_id",
    "work_id",
    "passage_id",
    "record_number",
    "field_path",
    "interaction_number",
    "section",
    "memory_id",
    "journal_line",
    "result_index",
    "json_path",
    "page_numbers",
    "order",
}

EPISTEMIC_NOTE = (
    "Cette attribution conserve l’origine et l’emplacement "
    "d’un élément consulté. Elle ne transforme ni une "
    "hypothèse en fait, ni une provenance en validation."
)


def _canonical_json(
    value: Any,
) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _canonical_hash(
    value: Any,
) -> str:
    return hashlib.sha256(
        _canonical_json(value).encode(
            "utf-8"
        )
    ).hexdigest()


def _require_string(
    value: Any,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AttributionSchemaError(
            f"Champ obligatoire absent : {field_name}"
        )

    return value.strip()


def _optional_string(
    value: Any,
    field_name: str,
) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise AttributionSchemaError(
            f"Le champ {field_name} doit être une chaîne."
        )

    cleaned = value.strip()

    return cleaned or None


def _validate_timestamp(
    value: Any,
    field_name: str,
) -> str | None:
    cleaned = _optional_string(
        value,
        field_name,
    )

    if cleaned is None:
        return None

    try:
        datetime.fromisoformat(
            cleaned.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise AttributionSchemaError(
            f"Horodatage invalide : {field_name}"
        ) from error

    return cleaned


def _clean_mapping(
    value: dict[str, Any],
) -> dict[str, Any]:
    return {
        key: child
        for key, child in value.items()
        if child is not None
    }


def _contributors(
    *items: tuple[str, Any],
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for role, name in items:
        if name is None:
            continue

        if not isinstance(name, str):
            continue

        cleaned = name.strip()

        if not cleaned:
            continue

        identity = (
            role,
            cleaned,
        )

        if identity in seen:
            continue

        seen.add(identity)
        result.append({
            "role": role,
            "name": cleaned,
        })

    return result


def _hash_entry(
    value: Any,
    *,
    scope: str,
) -> list[dict[str, str]]:
    if value is None:
        return []

    if not isinstance(value, str):
        return []

    cleaned = value.strip().lower()

    if not cleaned:
        return []

    return [{
        "algorithm": "sha256",
        "value": cleaned,
        "scope": scope,
    }]


def _identity_payload(
    attribution: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": attribution.get(
            "schema_version"
        ),
        "origin_system": attribution.get(
            "origin_system"
        ),
        "source_type": attribution.get(
            "source_type"
        ),
        "title": attribution.get("title"),
        "source_file": attribution.get(
            "source_file"
        ),
        "raw_attribution": attribution.get(
            "raw_attribution"
        ),
        "contributors": attribution.get(
            "contributors"
        ),
        "locator": attribution.get("locator"),
        "hashes": attribution.get("hashes"),
    }


def attribution_id(
    attribution: dict[str, Any],
) -> str:
    digest = _canonical_hash(
        _identity_payload(attribution)
    )

    return f"attr_{digest[:24]}"


def build_attribution(
    *,
    origin_system: str,
    source_type: str,
    title: str | None = None,
    source_file: str | None = None,
    raw_attribution: str | None = None,
    contributors: list[dict[str, str]] | None = None,
    locator: dict[str, Any] | None = None,
    hashes: list[dict[str, str]] | None = None,
    status: str | None = None,
    observed_at_utc: str | None = None,
    excerpt: str | None = None,
    native_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    attribution = {
        "schema_version": SCHEMA_VERSION,
        "origin_system": origin_system,
        "source_type": source_type,
        "title": title,
        "source_file": source_file,
        "raw_attribution": raw_attribution,
        "contributors": contributors or [],
        "locator": _clean_mapping(
            locator or {}
        ),
        "hashes": hashes or [],
        "status": status,
        "observed_at_utc": observed_at_utc,
        "excerpt": excerpt,
        "native_fields": deepcopy(
            native_fields or {}
        ),
        "external_action_performed": False,
        "subjective_interpretation_claimed": False,
        "epistemic_note": EPISTEMIC_NOTE,
    }

    attribution["attribution_id"] = (
        attribution_id(attribution)
    )

    return validate_attribution(
        attribution
    )


def validate_attribution(
    attribution: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(attribution, dict):
        raise AttributionSchemaError(
            "L’attribution doit être un objet."
        )

    if attribution.get(
        "schema_version"
    ) != SCHEMA_VERSION:
        raise AttributionSchemaError(
            "Version de schéma inconnue."
        )

    origin_system = _require_string(
        attribution.get("origin_system"),
        "origin_system",
    )

    if origin_system not in VALID_ORIGIN_SYSTEMS:
        raise AttributionSchemaError(
            f"Système d’origine inconnu : {origin_system}"
        )

    _require_string(
        attribution.get("source_type"),
        "source_type",
    )

    for field_name in (
        "title",
        "source_file",
        "raw_attribution",
        "status",
        "excerpt",
    ):
        _optional_string(
            attribution.get(field_name),
            field_name,
        )

    _validate_timestamp(
        attribution.get(
            "observed_at_utc"
        ),
        "observed_at_utc",
    )

    contributors = attribution.get(
        "contributors"
    )

    if not isinstance(contributors, list):
        raise AttributionSchemaError(
            "La liste des contributeurs est invalide."
        )

    contributor_keys: set[
        tuple[str, str]
    ] = set()

    for index, contributor in enumerate(
        contributors,
        1,
    ):
        if not isinstance(contributor, dict):
            raise AttributionSchemaError(
                f"Contributeur invalide : {index}"
            )

        role = _require_string(
            contributor.get("role"),
            f"contributors[{index}].role",
        )
        name = _require_string(
            contributor.get("name"),
            f"contributors[{index}].name",
        )

        if role not in VALID_CONTRIBUTOR_ROLES:
            raise AttributionSchemaError(
                f"Rôle de contributeur inconnu : {role}"
            )

        key = (
            role,
            name,
        )

        if key in contributor_keys:
            raise AttributionSchemaError(
                "Contributeur dupliqué."
            )

        contributor_keys.add(key)

    locator = attribution.get(
        "locator"
    )

    if not isinstance(locator, dict):
        raise AttributionSchemaError(
            "Le localisateur doit être un objet."
        )

    unknown_locator_fields = (
        set(locator)
        - VALID_LOCATOR_FIELDS
    )

    if unknown_locator_fields:
        raise AttributionSchemaError(
            "Champs de localisation inconnus : "
            + ", ".join(
                sorted(
                    unknown_locator_fields
                )
            )
        )

    for key, value in locator.items():
        if isinstance(value, bool):
            raise AttributionSchemaError(
                f"Localisateur booléen invalide : {key}"
            )

        if not isinstance(
            value,
            (
                str,
                int,
            ),
        ):
            raise AttributionSchemaError(
                f"Valeur de localisation invalide : {key}"
            )

        if (
            isinstance(value, str)
            and not value.strip()
        ):
            raise AttributionSchemaError(
                f"Localisateur vide : {key}"
            )

    hashes = attribution.get("hashes")

    if not isinstance(hashes, list):
        raise AttributionSchemaError(
            "La liste des empreintes est invalide."
        )

    hash_keys: set[
        tuple[str, str]
    ] = set()

    for index, hash_item in enumerate(
        hashes,
        1,
    ):
        if not isinstance(hash_item, dict):
            raise AttributionSchemaError(
                f"Empreinte invalide : {index}"
            )

        algorithm = _require_string(
            hash_item.get("algorithm"),
            f"hashes[{index}].algorithm",
        )
        value = _require_string(
            hash_item.get("value"),
            f"hashes[{index}].value",
        ).lower()
        scope = _require_string(
            hash_item.get("scope"),
            f"hashes[{index}].scope",
        )

        if algorithm != "sha256":
            raise AttributionSchemaError(
                "Seules les empreintes SHA-256 "
                "sont actuellement admises."
            )

        if (
            len(value) != 64
            or any(
                character
                not in "0123456789abcdef"
                for character in value
            )
        ):
            raise AttributionSchemaError(
                "Empreinte SHA-256 invalide."
            )

        key = (
            value,
            scope,
        )

        if key in hash_keys:
            raise AttributionSchemaError(
                "Empreinte dupliquée."
            )

        hash_keys.add(key)

    native_fields = attribution.get(
        "native_fields"
    )

    if not isinstance(native_fields, dict):
        raise AttributionSchemaError(
            "Les champs natifs doivent former un objet."
        )

    if attribution.get(
        "external_action_performed"
    ) is not False:
        raise AttributionSchemaError(
            "L’attribution déclare une action extérieure."
        )

    if attribution.get(
        "subjective_interpretation_claimed"
    ) is not False:
        raise AttributionSchemaError(
            "L’attribution revendique une "
            "interprétation subjective."
        )

    anchored = any([
        attribution.get("source_file"),
        attribution.get(
            "raw_attribution"
        ),
        bool(locator),
        bool(hashes),
    ])

    if not anchored:
        raise AttributionSchemaError(
            "L’attribution ne possède aucun ancrage."
        )

    expected_id = _require_string(
        attribution.get(
            "attribution_id"
        ),
        "attribution_id",
    )
    actual_id = attribution_id(
        attribution
    )

    if expected_id != actual_id:
        raise AttributionSchemaError(
            "L’identifiant d’attribution ne "
            "correspond pas à son contenu."
        )

    return attribution


def validate_attribution_collection(
    attributions: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    if not isinstance(attributions, list):
        raise AttributionSchemaError(
            "La collection doit être une liste."
        )

    identifiers: set[str] = set()
    origins: Counter[str] = Counter()
    source_types: Counter[str] = Counter()

    for attribution in attributions:
        validated = validate_attribution(
            attribution
        )
        identifier = validated[
            "attribution_id"
        ]

        if identifier in identifiers:
            raise AttributionSchemaError(
                "Identifiant d’attribution dupliqué : "
                f"{identifier}"
            )

        identifiers.add(identifier)
        origins[
            validated["origin_system"]
        ] += 1
        source_types[
            validated["source_type"]
        ] += 1

    return {
        "schema_version": SCHEMA_VERSION,
        "attribution_count": len(
            attributions
        ),
        "unique_attribution_count": len(
            identifiers
        ),
        "origin_counts": dict(
            sorted(origins.items())
        ),
        "source_type_counts": dict(
            sorted(
                source_types.items()
            )
        ),
        "duplicate_count": 0,
        "external_action_performed": False,
        "subjective_interpretation_claimed": False,
    }


def from_octopus_node(
    node: dict[str, Any],
    *,
    source_file: str = (
        "octopus/octopus_data.json"
    ),
) -> dict[str, Any]:
    return build_attribution(
        origin_system="octopus",
        source_type=(
            "free_text_attribution"
        ),
        title=node.get("name"),
        source_file=source_file,
        raw_attribution=node.get("src"),
        locator={
            "section": "nodes",
            "node_id": node.get("id"),
        },
        status=node.get("status"),
        native_fields={
            "date": node.get("date"),
            "src": node.get("src"),
            "status": node.get("status"),
        },
    )


def from_open_question_evidence(
    evidence: dict[str, Any],
    *,
    question_id: str,
    question_text: str | None = None,
) -> dict[str, Any]:
    return build_attribution(
        origin_system="open_questions",
        source_type=_require_string(
            evidence.get("source_type"),
            "evidence.source_type",
        ),
        title=question_text,
        source_file=evidence.get(
            "source"
        ),
        locator={
            "question_id": question_id,
            "record_number": evidence.get(
                "record_number"
            ),
            "field_path": evidence.get(
                "field_path"
            ),
            "interaction_number": (
                evidence.get(
                    "interaction_number"
                )
            ),
        },
        hashes=_hash_entry(
            evidence.get(
                "response_sha256"
            ),
            scope="response",
        ),
        observed_at_utc=evidence.get(
            "timestamp"
        ),
        excerpt=evidence.get(
            "response_excerpt"
        ),
        native_fields={
            "rule": evidence.get("rule"),
            "source_type": evidence.get(
                "source_type"
            ),
        },
    )


def from_reading_work(
    work: dict[str, Any],
    *,
    journal_id: str,
) -> dict[str, Any]:
    return build_attribution(
        origin_system="reading",
        source_type="registered_work",
        title=work.get("title"),
        source_file=work.get(
            "source_file"
        ),
        contributors=_contributors(
            (
                "author",
                work.get("author"),
            ),
            (
                "translator",
                work.get("translator"),
            ),
            (
                "registered_by",
                work.get(
                    "source_registered_by"
                ),
            ),
        ),
        locator={
            "journal_id": journal_id,
            "work_id": work.get(
                "work_id"
            ),
        },
        hashes=_hash_entry(
            work.get("source_sha256"),
            scope="source_file",
        ),
        status=work.get(
            "source_status"
        ),
        observed_at_utc=work.get(
            "source_registered_at_utc"
        ),
        native_fields={
            "edition": work.get("edition"),
            "source_size_bytes": (
                work.get(
                    "source_size_bytes"
                )
            ),
        },
    )


def from_reading_passage(
    passage: dict[str, Any],
    *,
    work: dict[str, Any],
    journal_id: str,
) -> dict[str, Any]:
    return build_attribution(
        origin_system="reading",
        source_type="queued_passage",
        title=work.get("title"),
        source_file=work.get(
            "source_file"
        ),
        contributors=_contributors(
            (
                "author",
                work.get("author"),
            ),
            (
                "translator",
                work.get("translator"),
            ),
        ),
        locator={
            "journal_id": journal_id,
            "work_id": work.get(
                "work_id"
            ),
            "passage_id": passage.get(
                "passage_id"
            ),
            "order": passage.get("order"),
        },
        hashes=_hash_entry(
            passage.get(
                "passage_sha256"
            ),
            scope="passage",
        ),
        status=passage.get("status"),
        observed_at_utc=passage.get(
            "queued_at_utc"
        ),
        native_fields={
            "word_count": passage.get(
                "word_count"
            ),
            "character_count": (
                passage.get(
                    "character_count"
                )
            ),
            "exposed_at_utc": passage.get(
                "exposed_at_utc"
            ),
            "inference_engine": (
                passage.get(
                    "inference_engine"
                )
            ),
            "reflection_status": (
                passage.get(
                    "reflection_status"
                )
            ),
        },
    )


def from_library_source(
    source: dict[str, Any],
    *,
    containing_file: str,
    json_path: str,
    title: str | None = None,
) -> dict[str, Any]:
    return build_attribution(
        origin_system="library",
        source_type=_require_string(
            source.get("type"),
            "library_source.type",
        ),
        title=title,
        source_file=containing_file,
        contributors=_contributors(
            (
                "provided_by",
                source.get("provided_by"),
            ),
        ),
        locator={
            "json_path": json_path,
            "page_numbers": source.get(
                "page_numbers"
            ),
        },
        status=source.get(
            "completeness"
        ),
        native_fields=source,
    )


def from_dialogue_source(
    source: dict[str, Any],
    *,
    journal_line: int,
    result_index: int,
) -> dict[str, Any]:
    return build_attribution(
        origin_system="dialogue",
        source_type="retrieved_memory",
        title=source.get("title"),
        source_file=source.get("file"),
        locator={
            "section": source.get(
                "section"
            ),
            "memory_id": source.get(
                "memory_id"
            ),
            "journal_line": journal_line,
            "result_index": result_index,
        },
        native_fields={
            "score": source.get("score"),
        },
    )
