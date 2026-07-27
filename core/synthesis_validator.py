from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
from typing import Any

from core.attribution_schema import (
    AttributionSchemaError,
    build_attribution,
    validate_attribution_collection,
)


class SynthesisValidationError(ValueError):
    """Résultat de dialogue impossible à valider."""


SYNTHESIS_FOOTER = (
    "Je construis cette réponse à partir de ma "
    "bibliothèque synchronisée et de mes archives "
    "locales, sans ajouter de fait extérieur."
)


LEGACY_SYNTHESIS_FOOTER = (
    "Je construis cette réponse à partir de mes "
    "archives locales, sans ajouter de fait extérieur."
)


def _canonical_hash(
    value: Any,
) -> str:
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
        raise SynthesisValidationError(
            f"Champ obligatoire absent : {field_name}"
        )

    return value.strip()


def _extract_bullet_lines(
    response: str,
) -> list[str]:
    return [
        line.strip()
        for line in response.splitlines()
        if line.strip().startswith("• ")
    ]


def _validate_relative_file(
    value: Any,
    field_name: str,
) -> str:
    cleaned = _require_string(
        value,
        field_name,
    )

    path = PurePosixPath(cleaned)

    if path.is_absolute() or ".." in path.parts:
        raise SynthesisValidationError(
            f"Chemin de source interdit : {cleaned}"
        )

    return cleaned


def _source_identity(
    source: dict[str, Any],
) -> tuple[str, str, str, str | None]:
    return (
        str(source.get("file", "")).strip(),
        str(source.get("section", "")).strip(),
        str(source.get("title", "")).strip(),
        (
            str(source.get("memory_id")).strip()
            if source.get("memory_id") is not None
            else None
        ),
    )


def _validate_source(
    source: dict[str, Any],
    *,
    source_index: int,
) -> dict[str, Any]:
    if not isinstance(source, dict):
        raise SynthesisValidationError(
            f"Source invalide à l’index {source_index}."
        )

    source_file = _validate_relative_file(
        source.get("file"),
        f"sources[{source_index}].file",
    )
    section = _require_string(
        source.get("section"),
        f"sources[{source_index}].section",
    )
    title = _require_string(
        source.get("title"),
        f"sources[{source_index}].title",
    )

    score = source.get("score")

    if (
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or score <= 0
    ):
        raise SynthesisValidationError(
            f"Score invalide pour la source {source_index}."
        )

    memory_id = source.get("memory_id")

    if memory_id is not None:
        memory_id = _require_string(
            memory_id,
            f"sources[{source_index}].memory_id",
        )

        if not memory_id.startswith("memory_"):
            raise SynthesisValidationError(
                f"Identifiant mémoire invalide : {memory_id}"
            )

    return {
        "file": source_file,
        "section": section,
        "title": title,
        "score": score,
        "memory_id": memory_id,
    }


def _match_bullets_to_sources(
    *,
    bullet_lines: list[str],
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if len(bullet_lines) != len(sources):
        raise SynthesisValidationError(
            "Le nombre de fragments affichés ne correspond "
            "pas au nombre de sources."
        )

    matches: list[dict[str, Any]] = []

    for index, (
        bullet,
        source,
    ) in enumerate(
        zip(
            bullet_lines,
            sources,
            strict=True,
        ),
        1,
    ):
        expected_prefix = (
            f"• {source['title']} — "
        )

        if not bullet.startswith(expected_prefix):
            raise SynthesisValidationError(
                "Le fragment affiché à la position "
                f"{index} ne correspond pas à sa source."
            )

        excerpt = bullet[
            len(expected_prefix):
        ].strip()

        if not excerpt:
            raise SynthesisValidationError(
                f"Le fragment {index} ne contient aucun texte."
            )

        matches.append({
            "position": index,
            "title": source["title"],
            "excerpt": excerpt,
            "source_file": source["file"],
            "section": source["section"],
            "memory_id": source["memory_id"],
        })

    return matches


def _build_attributions(
    *,
    sources: list[dict[str, Any]],
    journal_line: int | None,
) -> list[dict[str, Any]]:
    attributions: list[dict[str, Any]] = []

    for result_index, source in enumerate(
        sources,
        1,
    ):
        locator: dict[str, Any] = {
            "section": source["section"],
            "result_index": result_index,
        }

        if source["memory_id"] is not None:
            locator["memory_id"] = (
                source["memory_id"]
            )

        if journal_line is not None:
            if (
                isinstance(journal_line, bool)
                or not isinstance(journal_line, int)
                or journal_line < 1
            ):
                raise SynthesisValidationError(
                    "Le numéro de ligne du journal est invalide."
                )

            locator["journal_line"] = journal_line

        attribution = build_attribution(
            origin_system="dialogue",
            source_type="retrieved_memory",
            title=source["title"],
            source_file=source["file"],
            locator=locator,
            native_fields={
                "score": source["score"],
            },
        )

        attributions.append(attribution)

    validate_attribution_collection(
        attributions
    )

    return attributions



def validate_dialogue_result(
    result: dict[str, Any],
    *,
    journal_line: int | None = None,
    mode: str = "strict",
) -> dict[str, Any]:
    """
    Valide une réponse déjà produite.

    mode="strict" protège les futures réponses.
    mode="historical_audit" conserve les anomalies
    anciennes sous forme d’avertissements.

    Cette fonction ne modifie aucun journal, aucune
    mémoire et aucun registre.
    """
    if mode not in {
        "strict",
        "historical_audit",
    }:
        raise SynthesisValidationError(
            f"Mode de validation inconnu : {mode}"
        )

    historical_audit = (
        mode == "historical_audit"
    )

    if not isinstance(result, dict):
        raise SynthesisValidationError(
            "Le résultat doit être un objet."
        )

    response = _require_string(
        result.get("response"),
        "response",
    )

    raw_sources = result.get(
        "sources",
        [],
    )

    if not isinstance(raw_sources, list):
        raise SynthesisValidationError(
            "Le champ sources doit être une liste."
        )

    bullet_lines = _extract_bullet_lines(
        response
    )
    warnings: list[str] = []

    if not raw_sources:
        report = {
            "schema_version": 1,
            "validation_mode": mode,
            "validation_status": "valid",
            "response_kind": (
                "non_retrieval_response"
            ),
            "source_count": 0,
            "bullet_count": len(
                bullet_lines
            ),
            "attribution_count": 0,
            "source_alignment_verified": False,
            "source_order_verified": False,
            "footer_verified": False,
            "footer_variant": None,
            "duplicate_source_count": 0,
            "warnings": [],
            "external_action_performed": False,
            "subjective_understanding_claimed": False,
        }
        report["validation_sha256"] = (
            _canonical_hash(report)
        )
        return report

    sources = [
        _validate_source(
            source,
            source_index=index,
        )
        for index, source in enumerate(
            raw_sources,
            1,
        )
    ]

    identity_positions: dict[
        tuple[str, str, str, str | None],
        list[int],
    ] = {}

    for position, source in enumerate(
        sources,
        1,
    ):
        identity = _source_identity(
            source
        )
        identity_positions.setdefault(
            identity,
            [],
        ).append(position)

    duplicate_groups = {
        identity: positions
        for identity, positions
        in identity_positions.items()
        if len(positions) > 1
    }

    duplicate_source_count = sum(
        len(positions) - 1
        for positions in duplicate_groups.values()
    )

    if duplicate_groups:
        duplicate_message = (
            "Une même identité de source apparaît "
            "plusieurs fois."
        )

        if not historical_audit:
            raise SynthesisValidationError(
                duplicate_message
            )

        warnings.append(
            "legacy_duplicate_sources: "
            + duplicate_message
        )

    matches: list[dict[str, Any]] = []
    source_alignment_verified = False
    source_order_verified = False

    if bullet_lines:
        try:
            matches = _match_bullets_to_sources(
                bullet_lines=bullet_lines,
                sources=sources,
            )
        except SynthesisValidationError as error:
            if not historical_audit:
                raise

            warnings.append(
                "legacy_source_alignment: "
                f"{error}"
            )
        else:
            source_alignment_verified = True
            source_order_verified = True

        response_kind = (
            "retrieval_synthesis"
        )
    else:
        response_kind = (
            "legacy_non_retrieval_with_sources"
        )
        missing_bullets_message = (
            "Des sources sont présentes sans "
            "fragments documentaires affichés."
        )

        if not historical_audit:
            raise SynthesisValidationError(
                missing_bullets_message
            )

        warnings.append(
            "legacy_sources_without_synthesis: "
            + missing_bullets_message
        )

    current_footer = (
        response.rstrip().endswith(
            SYNTHESIS_FOOTER
        )
    )
    legacy_footer = (
        response.rstrip().endswith(
            LEGACY_SYNTHESIS_FOOTER
        )
    )

    footer_verified = current_footer
    footer_variant: str | None = None

    if current_footer:
        footer_variant = "current"
    elif legacy_footer:
        footer_variant = "legacy"

        if historical_audit:
            footer_verified = True
            warnings.append(
                "legacy_footer: ancienne frontière "
                "de provenance conservée."
            )
        else:
            raise SynthesisValidationError(
                "La synthèse utilise une ancienne "
                "frontière de provenance."
            )
    else:
        missing_footer_message = (
            "La synthèse ne conserve pas sa "
            "frontière explicite de provenance."
        )

        if not historical_audit:
            raise SynthesisValidationError(
                missing_footer_message
            )

        warnings.append(
            "legacy_missing_footer: "
            + missing_footer_message
        )

    attributions: list[
        dict[str, Any]
    ] = []

    try:
        attributions = _build_attributions(
            sources=sources,
            journal_line=journal_line,
        )
    except (
        AttributionSchemaError,
        SynthesisValidationError,
    ) as error:
        if not historical_audit:
            raise SynthesisValidationError(
                "Attribution commune invalide : "
                f"{error}"
            ) from error

        warnings.append(
            "legacy_attribution_failure: "
            f"{error}"
        )

    validation_status = (
        "valid_with_warnings"
        if warnings
        else "valid"
    )

    report = {
        "schema_version": 1,
        "validation_mode": mode,
        "validation_status": (
            validation_status
        ),
        "response_kind": response_kind,
        "source_count": len(sources),
        "bullet_count": len(
            bullet_lines
        ),
        "attribution_count": len(
            attributions
        ),
        "source_alignment_verified": (
            source_alignment_verified
        ),
        "source_order_verified": (
            source_order_verified
        ),
        "footer_verified": (
            footer_verified
        ),
        "footer_variant": (
            footer_variant
        ),
        "duplicate_source_count": (
            duplicate_source_count
        ),
        "duplicate_groups": [
            {
                "file": identity[0],
                "section": identity[1],
                "title": identity[2],
                "memory_id": identity[3],
                "positions": positions,
            }
            for identity, positions
            in duplicate_groups.items()
        ],
        "matches": matches,
        "attribution_ids": [
            attribution[
                "attribution_id"
            ]
            for attribution in attributions
        ],
        "warnings": warnings,
        "external_action_performed": False,
        "subjective_understanding_claimed": False,
        "epistemic_note": (
            "La validation confirme la présence, "
            "l’ordre et la traçabilité des sources "
            "lorsque ces éléments sont disponibles. "
            "Elle ne confirme pas à elle seule la "
            "vérité matérielle des affirmations."
        ),
    }

    report["validation_sha256"] = (
        _canonical_hash(report)
    )

    return report
