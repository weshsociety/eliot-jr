from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Protocol


class InferenceEngineError(ValueError):
    """Erreur contrôlée d’un moteur d’inférence."""


class InferenceEngine(Protocol):
    engine_id: str

    def infer(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        ...


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def build_reading_inference_request(
    journal: dict[str, Any],
    manifest: dict[str, Any],
    passage_id: str,
) -> dict[str, Any]:
    """
    Construit un paquet de lecture vérifiable.

    Cette opération ne signifie pas que le passage a été lu,
    compris ou interprété.
    """
    if not isinstance(journal, dict):
        raise InferenceEngineError(
            "Le journal de lecture est invalide."
        )

    if not isinstance(manifest, dict):
        raise InferenceEngineError(
            "Le manifeste de source est invalide."
        )

    passage_id = str(passage_id).strip()

    source_hash = str(
        manifest.get("source_sha256", "")
    ).strip()

    work = journal.get("work", {})
    reading_queue = journal.get("reading_queue", [])
    before = journal.get("before_reading", {})

    if not isinstance(work, dict):
        raise InferenceEngineError(
            "La section work est invalide."
        )

    if not isinstance(reading_queue, list):
        raise InferenceEngineError(
            "La file de lecture est invalide."
        )

    if not isinstance(before, dict):
        raise InferenceEngineError(
            "L’état avant lecture est invalide."
        )

    if work.get("source_sha256") != source_hash:
        raise InferenceEngineError(
            "Le manifeste ne correspond pas à la source du journal."
        )

    if before.get("status") != "recorded":
        raise InferenceEngineError(
            "L’état avant lecture n’a pas été enregistré."
        )

    queue_item = next(
        (
            item
            for item in reading_queue
            if (
                isinstance(item, dict)
                and item.get("passage_id") == passage_id
            )
        ),
        None,
    )

    if queue_item is None:
        raise InferenceEngineError(
            f"Passage absent de la file : {passage_id}"
        )

    if queue_item.get("status") != "queued":
        raise InferenceEngineError(
            f"Le passage {passage_id} n’est plus en attente."
        )

    passage = next(
        (
            item
            for item in manifest.get("passages", [])
            if (
                isinstance(item, dict)
                and item.get("passage_id") == passage_id
            )
        ),
        None,
    )

    if passage is None:
        raise InferenceEngineError(
            f"Passage absent du manifeste : {passage_id}"
        )

    if (
        passage.get("sha256")
        != queue_item.get("passage_sha256")
    ):
        raise InferenceEngineError(
            "L’empreinte du passage ne correspond pas à la file."
        )

    request_body = {
        "schema_version": 1,
        "task": "reading_encounter",
        "journal_id": journal.get("journal_id"),
        "work": {
            "work_id": work.get("work_id"),
            "author": work.get("author"),
            "title": work.get("title"),
            "edition": work.get("edition"),
            "corpus_status": "partial",
        },
        "source": {
            "source_file": manifest.get("source_file"),
            "source_sha256": source_hash,
        },
        "passage": {
            "passage_id": passage_id,
            "order": passage.get("order"),
            "passage_sha256": passage.get("sha256"),
            "text": passage.get("text"),
        },
        "before_reading": {
            "interaction_number": before.get(
                "interaction_number"
            ),
            "recorded_at_utc": before.get(
                "recorded_at_utc"
            ),
            "response_verbatim": before.get(
                "response_verbatim"
            ),
        },
        "instructions": {
            "mode": "encounter_not_doctrine",
            "requirements": [
                "Distinguer ce que dit le passage de toute interprétation.",
                "Ne pas inventer le contexte absent.",
                "Formuler une compréhension provisoire.",
                "Formuler au moins une question ou objection.",
                "Dire explicitement ce que ce passage ne permet pas de conclure.",
                "Ne pas présenter l’inspiration comme une adoption.",
            ],
        },
    }

    request_body["payload_sha256"] = _canonical_hash(
        request_body
    )
    request_body["created_at_utc"] = _utc_now()
    request_body["request_sha256"] = _canonical_hash(
        request_body
    )

    return request_body


class NullInferenceEngine:
    """
    Moteur témoin utilisé tant qu’aucun modèle réel n’est branché.
    """

    engine_id = "null_engine"

    def infer(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "status": "engine_unavailable",
            "engine_id": self.engine_id,
            "model": None,
            "payload_sha256": request.get(
                "payload_sha256"
            ),
            "request_sha256": request.get(
                "request_sha256"
            ),
            "reflection_produced": False,
            "output": None,
            "message": (
                "Aucun moteur d’inférence réel n’est actuellement "
                "branché. Le passage n’est pas déclaré comme lu "
                "ou interprété."
            ),
            "completed_at_utc": _utc_now(),
        }
