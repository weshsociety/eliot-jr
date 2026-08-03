import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch

import laboratory.enrich_claim_context as context_module


class ClaimContextTests(unittest.TestCase):
    def test_source_state_detects_change(self):
        self.assertEqual(
            context_module.determine_source_state("abc", "abc"),
            "unchanged",
        )
        self.assertEqual(
            context_module.determine_source_state("abc", "def"),
            "changed_since_candidate_extraction",
        )

    def test_changed_source_is_quarantined_before_enrichment(self):
        original_content = "# Note\nUne affirmation ancienne.\n"
        current_content = "# Note\nUne affirmation modifiée.\n"
        original_sha = hashlib.sha256(
            original_content.encode("utf-8")
        ).hexdigest()

        source_report = {
            "schema": "eliot-jr.claim-candidates.v2",
            "candidates": [
                {
                    "candidate_id": "claim_00001",
                    "source_path": "01_Acteurs/Test.md",
                    "source_sha256": original_sha,
                    "line_start": 2,
                    "line_end": 2,
                    "verbatim_excerpt": "Une affirmation ancienne.",
                    "surface_categories": ["surface_statement"],
                    "matched_markers": [],
                    "truth_status": "not_assessed",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_path = root / "input.json"
            output_path = root / "output.json"
            input_path.write_text(
                json.dumps(source_report),
                encoding="utf-8",
            )

            with (
                patch.object(context_module, "INPUT", input_path),
                patch.object(context_module, "OUTPUT", output_path),
                patch.object(
                    context_module,
                    "read_note",
                    return_value=current_content,
                ),
                patch.object(sys, "argv", ["enrich_claim_context.py"]),
                redirect_stdout(io.StringIO()),
            ):
                return_code = context_module.main()

            report = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(return_code, 1)
        self.assertEqual(report["input_candidate_count"], 1)
        self.assertEqual(report["candidate_count"], 0)
        self.assertEqual(report["blocked_candidate_count"], 1)
        self.assertEqual(report["relations_created"], 0)
        self.assertFalse(report["core_modified"])


if __name__ == "__main__":
    unittest.main()
