from __future__ import annotations

from copy import deepcopy
from typing import Any
import hashlib
import json


MIGRATION_ID = (
    "reading_schema_v2_external_notes_"
    "and_logical_learning"
)

TARGET_PASSAGES = (
    "passage_0001",
    "passage_0002",
    "passage_0003",
    "passage_0004",
)


class ReadingSchemaV2Error(ValueError):
    pass


def _canonical_hash(
    value: dict[str, Any],
) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(payload).hexdigest()


def candidate_document_hash(
    candidate: dict[str, Any],
) -> str:
    payload = deepcopy(candidate)
    payload.pop("candidate_sha256", None)

    return _canonical_hash(payload)


def _candidate_is_v2(
    candidate: dict[str, Any],
) -> bool:
    migration = candidate.get(
        "migration_v2",
        {},
    )

    return (
        candidate.get("schema_version") == 2
        and candidate.get("semantic_role")
        == "external_reading_note_candidate"
        and isinstance(migration, dict)
        and migration.get("migration_id")
        == MIGRATION_ID
    )


def _encounter_is_v2(
    encounter: dict[str, Any],
) -> bool:
    return (
        encounter.get("schema_version") == 2
        and isinstance(
            encounter.get(
                "passage_encounter"
            ),
            dict,
        )
        and isinstance(
            encounter.get(
                "external_reading_note"
            ),
            dict,
        )
        and isinstance(
            encounter.get(
                "collective_review"
            ),
            dict,
        )
        and isinstance(
            encounter.get(
                "eliot_learning_state"
            ),
            dict,
        )
    )


def _copy_review(
    candidate: dict[str, Any],
) -> dict[str, Any]:
    review = candidate.get("review", {})

    if not isinstance(review, dict):
        raise ReadingSchemaV2Error(
            "La revue candidate est invalide."
        )

    decision = review.get("decision")

    if not decision:
        raise ReadingSchemaV2Error(
            "La décision de revue est absente."
        )

    reviewed_by = review.get(
        "reviewed_by"
    )

    return {
        "status": decision,
        "review_type": (
            "historical_collective_review"
        ),
        "drafted_by": "Cypher",
        "approved_by": (
            reviewed_by or "Trinity"
        ),
        "reviewed_at_utc": review.get(
            "reviewed_at_utc"
        ),
        "explicit_human_confirmation": (
            review.get(
                "explicit_human_confirmation"
            )
            is True
        ),
        "text": review.get(
            "comment",
            "",
        ),
        "scope": (
            "external_reading_note_only"
        ),
        "does_not_validate_eliot": True,
        "provenance_note": (
            "La critique a été formulée par "
            "Cypher puis explicitement approuvée "
            "par Trinity. Elle ne constitue pas "
            "une réflexion d’Eliot-Jr."
        ),
    }


def migrate_candidate_document(
    candidate: dict[str, Any],
    *,
    migrated_at_utc: str,
) -> tuple[
    dict[str, Any],
    bool,
]:
    if not isinstance(candidate, dict):
        raise ReadingSchemaV2Error(
            "La candidate doit être un objet."
        )

    if _candidate_is_v2(candidate):
        return deepcopy(candidate), False

    passage_id = candidate.get("passage_id")
    journal_id = candidate.get("journal_id")

    if passage_id not in TARGET_PASSAGES:
        return deepcopy(candidate), False

    if not journal_id:
        raise ReadingSchemaV2Error(
            f"journal_id absent pour {passage_id}."
        )

    old_hash = candidate.get(
        "candidate_sha256"
    )

    if not old_hash:
        raise ReadingSchemaV2Error(
            f"Empreinte absente pour {passage_id}."
        )

    if candidate_document_hash(
        candidate
    ) != old_hash:
        raise ReadingSchemaV2Error(
            f"Candidate altérée : {passage_id}."
        )

    validated_result = candidate.get(
        "validated_result",
        {},
    )

    if not isinstance(
        validated_result,
        dict,
    ):
        raise ReadingSchemaV2Error(
            f"Résultat invalide : {passage_id}."
        )

    review = _copy_review(candidate)

    updated = deepcopy(candidate)

    old_previous_hash = updated.get(
        "previous_candidate_sha256"
    )

    hash_history = list(
        updated.get(
            "candidate_hash_history",
            [],
        )
    )

    if old_previous_hash:
        hash_history.append({
            "sha256": old_previous_hash,
            "role": (
                "legacy_previous_candidate_hash"
            ),
        })

    hash_history.append({
        "sha256": old_hash,
        "role": "pre_schema_v2_candidate",
    })

    updated["schema_version"] = 2
    updated["semantic_role"] = (
        "external_reading_note_candidate"
    )
    updated["candidate_status_scope"] = (
        "external_note_review_only"
    )
    updated["collective_review_attribution"] = (
        review
    )
    updated["eliot_learning_state"] = {
        "status": "not_yet_processed",
        "processing_mode": (
            "deterministic_non_llm"
        ),
        "human_approval_required_to_exist": (
            False
        ),
        "conclusion_required": False,
        "may_disagree_with_inherited_sources": (
            True
        ),
        "claims": [],
        "questions": [],
        "contradictions": [],
        "revisions": [],
    }
    updated["migration_v2"] = {
        "migration_id": MIGRATION_ID,
        "migrated_at_utc": migrated_at_utc,
        "source_schema_version": (
            candidate.get(
                "schema_version",
                1,
            )
        ),
        "source_candidate_sha256": old_hash,
        "migration_type": (
            "additive_semantic_reclassification"
        ),
        "content_deleted": False,
        "external_model_called": False,
    }
    updated["candidate_hash_history"] = (
        hash_history
    )
    updated["previous_candidate_sha256"] = (
        old_hash
    )

    updated.pop("candidate_sha256", None)
    updated["candidate_sha256"] = (
        candidate_document_hash(updated)
    )

    return updated, True


def _candidate_key(
    candidate: dict[str, Any],
) -> tuple[str, str]:
    passage_id = str(
        candidate.get(
            "passage_id",
            "",
        )
    )
    result = candidate.get(
        "validated_result",
        {},
    )

    if not isinstance(result, dict):
        return passage_id, ""

    return (
        passage_id,
        str(
            result.get(
                "result_sha256",
                "",
            )
        ),
    )


def index_candidates(
    candidates: list[
        dict[str, Any]
    ],
) -> dict[
    tuple[str, str],
    dict[str, Any],
]:
    indexed = {}

    for candidate in candidates:
        key = _candidate_key(candidate)

        if not key[0] or not key[1]:
            continue

        if key in indexed:
            raise ReadingSchemaV2Error(
                "Plusieurs candidates partagent "
                f"la même identité : {key}."
            )

        indexed[key] = candidate

    return indexed


def _build_external_note(
    encounter: dict[str, Any],
) -> dict[str, Any]:
    engine = encounter.get(
        "engine_attribution",
        {},
    )

    if not isinstance(engine, dict):
        engine = {}

    return {
        "status": "recorded",
        "note_type": (
            "external_model_reading_note"
        ),
        "authorship_status": (
            "external_model_output"
        ),
        "engine_attribution": deepcopy(
            engine
        ),
        "request_sha256": encounter.get(
            "request_sha256"
        ),
        "payload_sha256": encounter.get(
            "payload_sha256"
        ),
        "result_sha256": encounter.get(
            "result_sha256"
        ),
        "what_passage_says": deepcopy(
            encounter.get(
                "what_passage_says"
            )
        ),
        "provisional_understanding": (
            deepcopy(
                encounter.get(
                    "provisional_understanding"
                )
            )
        ),
        "questions_or_objections": (
            deepcopy(
                encounter.get(
                    "questions_or_objections",
                    [],
                )
            )
        ),
        "limits": deepcopy(
            encounter.get(
                "limits",
                [],
            )
        ),
        "epistemic_status": (
            "Note de lecture computationnelle "
            "externe, attribuée à un moteur "
            "identifié. Elle ne constitue ni "
            "une réflexion ni un apprentissage "
            "propre d’Eliot-Jr."
        ),
    }


def _build_learning_state() -> dict[str, Any]:
    return {
        "status": "not_yet_processed",
        "processing_mode": (
            "deterministic_non_llm"
        ),
        "processed_at_utc": None,
        "producer": "eliot_jr_logical_core",
        "llm_used": False,
        "human_approval_required_to_exist": (
            False
        ),
        "conclusion_required": False,
        "may_remain_unresolved": True,
        "may_hold_contradictions": True,
        "may_disagree_with_collective": True,
        "claims": [],
        "terms": [],
        "relations": [],
        "ambiguities": [],
        "questions": [],
        "contradictions": [],
        "hypotheses": [],
        "revisions": [],
    }


def migrate_journal_document(
    journal: dict[str, Any],
    *,
    candidates: list[
        dict[str, Any]
    ],
    migrated_at_utc: str,
) -> tuple[
    dict[str, Any],
    bool,
]:
    if not isinstance(journal, dict):
        raise ReadingSchemaV2Error(
            "Le journal doit être un objet."
        )

    updated = deepcopy(journal)
    indexed = index_candidates(candidates)

    encounters = updated.get(
        "encounters",
        [],
    )

    if not isinstance(encounters, list):
        raise ReadingSchemaV2Error(
            "La liste des rencontres est invalide."
        )

    changed = False
    migrated_ids = []

    for index, encounter in enumerate(
        encounters
    ):
        if not isinstance(encounter, dict):
            continue

        passage_id = encounter.get(
            "passage_id"
        )

        if passage_id not in TARGET_PASSAGES:
            continue

        if _encounter_is_v2(encounter):
            continue

        result_sha256 = str(
            encounter.get(
                "result_sha256",
                "",
            )
        )

        candidate = indexed.get(
            (
                str(passage_id),
                result_sha256,
            )
        )

        if candidate is None:
            raise ReadingSchemaV2Error(
                "Candidate correspondante "
                f"introuvable pour {passage_id}."
            )

        review = _copy_review(candidate)

        migrated = deepcopy(encounter)

        migrated["schema_version"] = 2
        migrated["record_kind"] = (
            "reading_encounter"
        )

        migrated["passage_encounter"] = {
            "status": "recorded",
            "encounter_id": (
                encounter.get(
                    "encounter_id"
                )
            ),
            "encounter_number": (
                encounter.get(
                    "encounter_number"
                )
            ),
            "passage_id": passage_id,
            "passage_order": (
                encounter.get(
                    "passage_order"
                )
            ),
            "passage_sha256": (
                encounter.get(
                    "passage_sha256"
                )
            ),
            "encountered_at_utc": (
                encounter.get(
                    "encountered_at_utc"
                )
            ),
        }

        migrated["external_reading_note"] = (
            _build_external_note(
                encounter
            )
        )

        migrated["collective_review"] = (
            review
        )

        migrated["eliot_learning_state"] = (
            _build_learning_state()
        )

        migrated["integration"] = {
            "performed_by": (
                "eliot_jr_reading_protocol"
            ),
            "operation": (
                "historical_external_note_"
                "and_review_ingestion"
            ),
            "does_not_imply_eliot_authorship": (
                True
            ),
            "does_not_imply_eliot_agreement": (
                True
            ),
        }

        migrated["legacy_v1"] = {
            "status": "preserved_for_compatibility",
            "deprecated_fields": [
                "authorship_status",
                "epistemic_status",
                "what_passage_says",
                "provisional_understanding",
                "questions_or_objections",
                "limits",
            ],
            "original_authorship_status": (
                encounter.get(
                    "authorship_status"
                )
            ),
            "original_epistemic_status": (
                encounter.get(
                    "epistemic_status"
                )
            ),
            "content_deleted": False,
        }

        migrated["migration_v2"] = {
            "migration_id": MIGRATION_ID,
            "migrated_at_utc": migrated_at_utc,
            "migration_type": (
                "additive_semantic_"
                "reclassification"
            ),
            "external_model_called": False,
            "human_validation_of_eliot": False,
        }

        encounters[index] = migrated
        migrated_ids.append(
            encounter.get(
                "encounter_id"
            )
        )
        changed = True

    queue = updated.get(
        "reading_queue",
        [],
    )

    if not isinstance(queue, list):
        raise ReadingSchemaV2Error(
            "La file de lecture est invalide."
        )

    for item in queue:
        if not isinstance(item, dict):
            continue

        passage_id = item.get("passage_id")

        if passage_id not in TARGET_PASSAGES:
            continue

        if (
            item.get("queue_schema_version")
            == 2
        ):
            continue

        item["queue_schema_version"] = 2
        item[
            "legacy_reflection_status"
        ] = item.get(
            "reflection_status"
        )
        item[
            "reflection_status_scope"
        ] = (
            "legacy_external_note_"
            "classification"
        )
        item[
            "external_reading_note_status"
        ] = "recorded"
        item[
            "collective_review_status"
        ] = next(
            (
                encounter[
                    "collective_review"
                ]["status"]
                for encounter in encounters
                if (
                    isinstance(
                        encounter,
                        dict,
                    )
                    and encounter.get(
                        "passage_id"
                    )
                    == passage_id
                    and isinstance(
                        encounter.get(
                            "collective_review"
                        ),
                        dict,
                    )
                )
            ),
            "not_recorded",
        )
        item[
            "eliot_learning_status"
        ] = "not_yet_processed"

        changed = True

    existing_history = updated.get(
        "migration_history",
        [],
    )

    if not isinstance(
        existing_history,
        list,
    ):
        existing_history = []

    already_recorded = any(
        isinstance(entry, dict)
        and entry.get("migration_id")
        == MIGRATION_ID
        for entry in existing_history
    )

    if changed and not already_recorded:
        existing_history.append({
            "migration_id": MIGRATION_ID,
            "migrated_at_utc": migrated_at_utc,
            "from_schema_version": (
                journal.get(
                    "schema_version",
                    1,
                )
            ),
            "to_schema_version": 2,
            "encounter_ids": migrated_ids,
            "content_deleted": False,
            "external_model_called": False,
        })

    if changed:
        updated["schema_version"] = 2
        updated["learning_architecture"] = {
            "mode": (
                "deterministic_non_llm"
            ),
            "external_notes_are_not_"
            "eliot_reflections": True,
            "human_approval_required_"
            "for_learning_state": False,
            "conclusion_required": False,
            "contradictions_allowed": True,
            "collective_values_are": (
                "situated_and_contestable"
            ),
        }
        updated["migration_history"] = (
            existing_history
        )

    return updated, changed
