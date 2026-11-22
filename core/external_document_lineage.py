from __future__ import annotations

from datetime import datetime

from core.external_document_identity import (
    document_key_from_manifest,
)


class DocumentLineageError(ValueError):
    pass


def _timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise DocumentLineageError(
            "timestamp invalide"
        )

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise DocumentLineageError(
            "timestamp invalide"
        ) from exc

    if parsed.tzinfo is None:
        raise DocumentLineageError(
            "timestamp sans fuseau"
        )

    return parsed


def observed_after_relation(
    *,
    earlier: dict,
    later: dict,
) -> dict:
    """
    Décrit uniquement une chronologie d'observation
    entre deux snapshots du même document.

    Ne signifie ni remplacement, ni correction,
    ni supériorité épistémique.
    """

    if not isinstance(earlier, dict):
        raise DocumentLineageError(
            "snapshot antérieur invalide"
        )

    if not isinstance(later, dict):
        raise DocumentLineageError(
            "snapshot ultérieur invalide"
        )

    earlier_key = earlier.get(
        "document_key"
    )

    later_key = later.get(
        "document_key"
    )

    if (
        not isinstance(earlier_key, str)
        or not earlier_key
        or earlier_key != later_key
    ):
        raise DocumentLineageError(
            "documents différents"
        )

    earlier_snapshot = earlier.get(
        "snapshot_id"
    )

    later_snapshot = later.get(
        "snapshot_id"
    )

    if (
        not isinstance(earlier_snapshot, str)
        or not earlier_snapshot
        or not isinstance(later_snapshot, str)
        or not later_snapshot
    ):
        raise DocumentLineageError(
            "snapshot_id invalide"
        )

    if earlier_snapshot == later_snapshot:
        raise DocumentLineageError(
            "même snapshot"
        )

    earlier_time = _timestamp(
        earlier.get("observed_at_utc")
    )

    later_time = _timestamp(
        later.get("observed_at_utc")
    )

    if later_time <= earlier_time:
        raise DocumentLineageError(
            "chronologie non strictement croissante"
        )

    return {
        "relation_type": "observed_after",
        "document_key": earlier_key,
        "earlier_snapshot_id": (
            earlier_snapshot
        ),
        "later_snapshot_id": (
            later_snapshot
        ),
        "earlier_observed_at_utc": (
            earlier["observed_at_utc"]
        ),
        "later_observed_at_utc": (
            later["observed_at_utc"]
        ),
        "replacement_claimed": False,
        "correction_claimed": False,
        "epistemic_preference": False,
    }


def build_document_lineage(
    manifests: list[dict],
) -> list[dict]:
    """
    Construit une lignée chronologique dérivée
    pour un seul document logique.

    Aucun manifest n'est modifié.
    Aucune relation de remplacement ou correction
    n'est inférée.
    """

    if not isinstance(manifests, list):
        raise DocumentLineageError(
            "liste de manifests invalide"
        )

    if len(manifests) < 2:
        return []

    normalized = []
    document_keys = set()
    snapshot_ids = set()

    for manifest in manifests:
        if not isinstance(manifest, dict):
            raise DocumentLineageError(
                "manifest invalide"
            )

        try:
            document_key = (
                document_key_from_manifest(
                    manifest
                )
            )
        except ValueError as exc:
            raise DocumentLineageError(
                str(exc)
            ) from exc

        snapshot_id = manifest.get(
            "snapshot_id"
        )

        if (
            not isinstance(snapshot_id, str)
            or not snapshot_id
        ):
            raise DocumentLineageError(
                "snapshot_id invalide"
            )

        if snapshot_id in snapshot_ids:
            raise DocumentLineageError(
                "snapshot_id dupliqué"
            )

        observed_at = manifest.get(
            "observed_at_utc"
        )

        parsed = _timestamp(
            observed_at
        )

        snapshot_ids.add(
            snapshot_id
        )

        document_keys.add(
            document_key
        )

        normalized.append(
            {
                "snapshot_id": snapshot_id,
                "document_key": document_key,
                "observed_at_utc": observed_at,
                "_parsed_time": parsed,
            }
        )

    if len(document_keys) != 1:
        raise DocumentLineageError(
            "plusieurs documents dans la lignée"
        )

    normalized.sort(
        key=lambda item: (
            item["_parsed_time"],
            item["snapshot_id"],
        )
    )

    relations = []

    for index in range(
        len(normalized) - 1
    ):
        earlier = normalized[index]
        later = normalized[index + 1]

        relations.append(
            observed_after_relation(
                earlier={
                    "snapshot_id": (
                        earlier["snapshot_id"]
                    ),
                    "document_key": (
                        earlier["document_key"]
                    ),
                    "observed_at_utc": (
                        earlier[
                            "observed_at_utc"
                        ]
                    ),
                },
                later={
                    "snapshot_id": (
                        later["snapshot_id"]
                    ),
                    "document_key": (
                        later["document_key"]
                    ),
                    "observed_at_utc": (
                        later[
                            "observed_at_utc"
                        ]
                    ),
                },
            )
        )

    return relations
