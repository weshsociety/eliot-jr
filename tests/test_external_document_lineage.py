import unittest

from core.external_document_lineage import (
    DocumentLineageError,
    observed_after_relation,
)


class ExternalDocumentLineageTests(
    unittest.TestCase
):
    def snapshot(
        self,
        snapshot_id,
        observed_at,
        document_key="doc_test",
    ):
        return {
            "snapshot_id": snapshot_id,
            "document_key": document_key,
            "observed_at_utc": observed_at,
        }

    def test_same_document_can_form_chronology(self):
        relation = observed_after_relation(
            earlier=self.snapshot(
                "snapshot_a",
                "2026-09-23T10:00:00+00:00",
            ),
            later=self.snapshot(
                "snapshot_b",
                "2026-09-24T10:00:00+00:00",
            ),
        )

        self.assertEqual(
            relation["relation_type"],
            "observed_after",
        )

        self.assertEqual(
            relation["document_key"],
            "doc_test",
        )

    def test_relation_does_not_claim_replacement(
        self,
    ):
        relation = observed_after_relation(
            earlier=self.snapshot(
                "snapshot_a",
                "2026-09-23T10:00:00+00:00",
            ),
            later=self.snapshot(
                "snapshot_b",
                "2026-09-24T10:00:00+00:00",
            ),
        )

        self.assertFalse(
            relation["replacement_claimed"]
        )

        self.assertFalse(
            relation["correction_claimed"]
        )

        self.assertFalse(
            relation["epistemic_preference"]
        )

    def test_different_documents_are_rejected(self):
        with self.assertRaises(
            DocumentLineageError
        ):
            observed_after_relation(
                earlier=self.snapshot(
                    "snapshot_a",
                    "2026-09-23T10:00:00+00:00",
                    document_key="doc_a",
                ),
                later=self.snapshot(
                    "snapshot_b",
                    "2026-09-24T10:00:00+00:00",
                    document_key="doc_b",
                ),
            )

    def test_same_snapshot_is_not_a_new_version(
        self,
    ):
        with self.assertRaises(
            DocumentLineageError
        ):
            observed_after_relation(
                earlier=self.snapshot(
                    "snapshot_a",
                    "2026-09-23T10:00:00+00:00",
                ),
                later=self.snapshot(
                    "snapshot_a",
                    "2026-09-24T10:00:00+00:00",
                ),
            )

    def test_reverse_chronology_is_rejected(self):
        with self.assertRaises(
            DocumentLineageError
        ):
            observed_after_relation(
                earlier=self.snapshot(
                    "snapshot_a",
                    "2026-09-24T10:00:00+00:00",
                ),
                later=self.snapshot(
                    "snapshot_b",
                    "2026-09-23T10:00:00+00:00",
                ),
            )


if __name__ == "__main__":
    unittest.main()
