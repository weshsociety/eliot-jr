from __future__ import annotations

from copy import deepcopy
import unittest

from laboratory.investigation_schema_validation import (
    InvestigationSchemaError,
    expected_encounter_packet_id,
    expected_encounter_packet_sha256,
    expected_relation_candidate_sha256,
    expected_relation_id,
    load_schema,
    validate_encounter_packet,
    validate_relation_candidate,
)


SOURCE_HASH = "a" * 64


def relation_candidate() -> dict:
    relation = {
        "schema": "eliot-jr.relation-candidate.v1",
        "relation_id": "rel_" + "0" * 24,
        "candidate_sha256": "0" * 64,
        "investigation_id": "epstein_trou_de_souris",
        "subject": {
            "surface": "Bill Gates",
            "entity_id": "bill_gates",
            "entity_type": "person",
        },
        "predicate": {
            "surface": "a rencontré",
            "normalized": "met_with",
        },
        "object": {
            "surface": "Jeffrey Epstein",
            "entity_id": "jeffrey_epstein",
            "entity_type": "person",
        },
        "basis": "table",
        "status": "candidate",
        "source": {
            "source_path": "01_Acteurs/Bill_Gates.md",
            "source_sha256": SOURCE_HASH,
            "source_current_sha256": SOURCE_HASH,
            "source_state": "unchanged",
            "line_start": 41,
            "line_end": 41,
            "verbatim_excerpt": (
                "| 2011-2014 | Rencontres avec Epstein "
                "(~12 fois en personne) | DOJ Files 2026 |"
            ),
            "claim_candidate_id": "claim_00009",
        },
        "qualifiers": {
            "negated": False,
            "hypothetical": False,
            "causal_claim_in_source": False,
            "attributed_to": None,
            "temporal_expression": "2011-2014",
            "inference_note": None,
        },
        "epistemic_state": {
            "truth_status": "not_assessed",
            "causality": "not_established",
            "confidence": "not_assessed",
            "contradictions": [],
        },
        "extraction": {
            "created_by": "deterministic_relation_extractor",
            "extractor_version": "v1",
            "created_at_utc": "2026-08-03T14:30:00Z",
            "llm_used": False,
            "core_modified": False,
            "octopus_modified": False,
            "publication_performed": False,
        },
        "review": None,
    }
    relation["relation_id"] = expected_relation_id(relation)
    relation["candidate_sha256"] = (
        expected_relation_candidate_sha256(relation)
    )
    return relation


def accepted_relation() -> dict:
    relation = relation_candidate()
    relation["status"] = "accepted_for_encounter"
    relation["review"] = {
        "decision": "accepted_for_encounter",
        "decision_type": "collective",
        "reviewed_by": ["Trinity", "Cypher"],
        "reviewed_at_utc": "2026-08-03T14:40:00Z",
        "comment": (
            "Acceptée pour rencontre, sans validation de vérité."
        ),
        "reviewed_candidate_sha256": relation[
            "candidate_sha256"
        ],
        "explicit_human_confirmation": True,
    }
    return relation


def encounter_packet() -> dict:
    relation = accepted_relation()
    packet = {
        "schema": "eliot-jr.investigation-encounter-packet.v1",
        "packet_id": "enc_" + "0" * 24,
        "packet_sha256": "0" * 64,
        "encounter_type": "investigation_relation_candidate",
        "investigation_id": relation["investigation_id"],
        "relation_id": relation["relation_id"],
        "relation_candidate_sha256": relation[
            "candidate_sha256"
        ],
        "prepared_at_utc": "2026-08-03T14:45:00Z",
        "prepared_by": "prepare_eliot_encounter_v1",
        "source_attribution": {
            "source_path": relation["source"]["source_path"],
            "source_sha256": relation["source"]["source_sha256"],
            "source_state": "unchanged",
            "line_start": relation["source"]["line_start"],
            "line_end": relation["source"]["line_end"],
            "verbatim_excerpt": relation["source"][
                "verbatim_excerpt"
            ],
            "claim_candidate_id": relation["source"][
                "claim_candidate_id"
            ],
        },
        "external_claim": {
            "subject": deepcopy(relation["subject"]),
            "predicate": deepcopy(relation["predicate"]),
            "object": deepcopy(relation["object"]),
            "basis": relation["basis"],
            "negated": relation["qualifiers"]["negated"],
            "hypothetical": relation["qualifiers"][
                "hypothetical"
            ],
            "causal_claim_in_source": relation["qualifiers"][
                "causal_claim_in_source"
            ],
        },
        "review": deepcopy(relation["review"]),
        "epistemic_state": {
            "truth_status": "not_assessed",
            "causality": "not_established",
            "contradictions": [],
        },
        "eliot_learning_state": {
            "status": "not_yet_processed",
            "conclusion_required": False,
        },
        "safeguards": {
            "human_review_required": True,
            "memory_written": False,
            "journal_written": False,
            "core_modified": False,
            "octopus_modified": False,
            "publication_performed": False,
        },
    }
    packet["packet_id"] = expected_encounter_packet_id(packet)
    packet["packet_sha256"] = expected_encounter_packet_sha256(
        packet
    )
    return packet


class InvestigationSchemaTests(unittest.TestCase):
    def test_schema_documents_are_valid_draft_2020_12(self) -> None:
        relation_schema = load_schema("relation_candidate")
        packet_schema = load_schema("encounter_packet")
        self.assertEqual(
            relation_schema["$schema"],
            "https://json-schema.org/draft/2020-12/schema",
        )
        self.assertEqual(
            packet_schema["$schema"],
            "https://json-schema.org/draft/2020-12/schema",
        )

    def test_valid_candidate_relation_is_accepted(self) -> None:
        relation = relation_candidate()
        validated = validate_relation_candidate(relation)
        self.assertEqual(validated, relation)
        self.assertEqual(relation["status"], "candidate")
        self.assertIsNone(relation["review"])

    def test_unknown_property_is_refused(self) -> None:
        relation = relation_candidate()
        relation["silent_truth_score"] = 0.99
        with self.assertRaises(InvestigationSchemaError):
            validate_relation_candidate(relation)

    def test_changed_source_cannot_be_accepted_for_encounter(self) -> None:
        relation = accepted_relation()
        relation["source"]["source_state"] = "changed"
        relation["source"]["source_current_sha256"] = "b" * 64
        relation["relation_id"] = expected_relation_id(relation)
        relation["candidate_sha256"] = (
            expected_relation_candidate_sha256(relation)
        )
        relation["review"]["reviewed_candidate_sha256"] = relation[
            "candidate_sha256"
        ]
        with self.assertRaises(InvestigationSchemaError):
            validate_relation_candidate(relation)

    def test_acceptance_requires_explicit_human_confirmation(self) -> None:
        relation = accepted_relation()
        relation["review"]["decision_type"] = "mechanical"
        relation["review"]["explicit_human_confirmation"] = False
        with self.assertRaises(InvestigationSchemaError):
            validate_relation_candidate(relation)

    def test_review_is_bound_to_candidate_hash(self) -> None:
        relation = accepted_relation()
        relation["review"]["reviewed_candidate_sha256"] = "b" * 64
        with self.assertRaises(InvestigationSchemaError):
            validate_relation_candidate(relation)

    def test_line_range_must_be_coherent(self) -> None:
        relation = relation_candidate()
        relation["source"]["line_end"] = 40
        relation["relation_id"] = expected_relation_id(relation)
        relation["candidate_sha256"] = (
            expected_relation_candidate_sha256(relation)
        )
        with self.assertRaises(InvestigationSchemaError):
            validate_relation_candidate(relation)


    def test_invalid_timestamp_is_refused_by_format_checker(self) -> None:
        relation = relation_candidate()
        relation["extraction"]["created_at_utc"] = "3 août 2026"
        relation["candidate_sha256"] = (
            expected_relation_candidate_sha256(relation)
        )
        with self.assertRaises(InvestigationSchemaError):
            validate_relation_candidate(relation)

    def test_inference_requires_an_explicit_note(self) -> None:
        relation = relation_candidate()
        relation["basis"] = "inference"
        relation["relation_id"] = expected_relation_id(relation)
        relation["candidate_sha256"] = (
            expected_relation_candidate_sha256(relation)
        )
        with self.assertRaises(InvestigationSchemaError):
            validate_relation_candidate(relation)

    def test_valid_encounter_packet_is_non_writing(self) -> None:
        packet = encounter_packet()
        validated = validate_encounter_packet(packet)
        self.assertEqual(validated, packet)
        self.assertFalse(packet["safeguards"]["memory_written"])
        self.assertFalse(packet["safeguards"]["octopus_modified"])
        self.assertFalse(packet["safeguards"]["publication_performed"])

    def test_packet_requires_reviewed_candidate_version(self) -> None:
        packet = encounter_packet()
        packet["review"]["reviewed_candidate_sha256"] = "c" * 64
        packet["packet_id"] = expected_encounter_packet_id(packet)
        packet["packet_sha256"] = expected_encounter_packet_sha256(
            packet
        )
        with self.assertRaises(InvestigationSchemaError):
            validate_encounter_packet(packet)

    def test_packet_hash_detects_silent_change(self) -> None:
        packet = encounter_packet()
        packet["external_claim"]["predicate"]["surface"] = (
            "aurait rencontré"
        )
        with self.assertRaises(InvestigationSchemaError):
            validate_encounter_packet(packet)


if __name__ == "__main__":
    unittest.main()
