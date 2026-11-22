from __future__ import annotations

import hashlib
import json


class ExternalDocumentIdentityError(ValueError):
    pass


def document_key_for(
    *,
    source_system: str,
    source_path: str,
    document_id: str | None = None,
) -> str:
    """
    Produit une identité logique stable du document.

    L'identité ne dépend jamais du contenu ni de son SHA.

    Si document_id existe, il est prioritaire sur source_path.
    source_system reste toujours partie de l'identité.
    """

    if (
        not isinstance(source_system, str)
        or not source_system.strip()
    ):
        raise ExternalDocumentIdentityError(
            "source_system invalide"
        )

    if (
        not isinstance(source_path, str)
        or not source_path.strip()
    ):
        raise ExternalDocumentIdentityError(
            "source_path invalide"
        )

    source_system = source_system.strip()

    if document_id is not None:
        if (
            not isinstance(document_id, str)
            or not document_id.strip()
        ):
            raise ExternalDocumentIdentityError(
                "document_id invalide"
            )

        identity = {
            "source_system": source_system,
            "document_id": document_id.strip(),
        }

    else:
        identity = {
            "source_system": source_system,
            "source_path": source_path,
        }

    canonical = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    digest = hashlib.sha256(
        canonical
    ).hexdigest()

    return f"doc_{digest[:24]}"

def document_key_from_manifest(
    manifest: dict,
) -> str:
    """
    Dérive l'identité logique d'un manifest existant.

    Un manifest legacy peut ne pas contenir document_key.
    Dans ce cas la clé est calculée en mémoire seulement.

    Si document_key existe déjà, elle doit correspondre
    exactement à l'identité dérivée.
    """

    if not isinstance(manifest, dict):
        raise ExternalDocumentIdentityError(
            "manifest invalide"
        )

    derived = document_key_for(
        source_system=manifest.get(
            "source_system"
        ),
        source_path=manifest.get(
            "source_path"
        ),
        document_id=manifest.get(
            "document_id"
        ),
    )

    existing = manifest.get(
        "document_key"
    )

    if existing is None:
        return derived

    if (
        not isinstance(existing, str)
        or existing != derived
    ):
        raise ExternalDocumentIdentityError(
            "document_key incompatible avec le manifest"
        )

    return existing
