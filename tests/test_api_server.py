from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from core.synthesis_validator import SynthesisValidationError
from voix.api import server


class ApiServerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_max_content_length = server.app.config[
            "MAX_CONTENT_LENGTH"
        ]
        self.original_max_message_chars = server.app.config[
            "MAX_DIALOGUE_MESSAGE_CHARS"
        ]
        server.app.config.update(
            TESTING=True,
            MAX_CONTENT_LENGTH=64 * 1024,
            MAX_DIALOGUE_MESSAGE_CHARS=8_000,
        )
        self.client = server.app.test_client()

    def tearDown(self) -> None:
        server.app.config.update(
            MAX_CONTENT_LENGTH=self.original_max_content_length,
            MAX_DIALOGUE_MESSAGE_CHARS=self.original_max_message_chars,
        )

    def test_index_uses_live_route_map(self) -> None:
        response = self.client.get("/api/")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(
            payload["endpoint_count"],
            len(payload["endpoints"]),
        )
        self.assertEqual(
            payload["endpoints"],
            server.public_endpoint_paths(),
        )
        self.assertIn("/api/see", payload["endpoints"])
        self.assertIn("/api/dialogue", payload["endpoints"])

    def test_security_headers_are_present(self) -> None:
        response = self.client.get("/api/status")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(
            response.headers["X-Content-Type-Options"],
            "nosniff",
        )
        self.assertEqual(
            response.headers["Referrer-Policy"],
            "no-referrer",
        )

    def test_status_timestamp_is_explicit_utc(self) -> None:
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["timestamp_timezone"], "UTC")
        self.assertTrue(payload["timestamp"].endswith("Z"))
        parsed = datetime.fromisoformat(
            payload["timestamp"].replace("Z", "+00:00")
        )
        self.assertIsNotNone(parsed.tzinfo)

    def test_memory_reports_observed_state_without_completeness_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            memory = root / "memory"
            wisdom = root / "wisdom"
            library = root / "library"
            memory.mkdir()
            wisdom.mkdir()
            (memory / "one.json").write_text("{}", encoding="utf-8")
            (wisdom / "two.json").write_text("{}", encoding="utf-8")

            with patch.object(
                server,
                "MEMORY_ROOTS",
                {
                    "memory": memory,
                    "wisdom": wisdom,
                    "library": library,
                },
            ):
                response = self.client.get("/api/memory")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "partial")
        self.assertFalse(payload["completeness_claimed"])
        self.assertEqual(payload["total_json_files_observed"], 2)
        self.assertEqual(
            payload["integrity_status"],
            "not_audited_by_this_endpoint",
        )

    def test_see_refuses_to_claim_unimplemented_memory_write(self) -> None:
        response = self.client.post(
            "/api/see",
            json={"observation": "Un fragment vérifiable."},
        )
        self.assertEqual(response.status_code, 501)
        payload = response.get_json()
        self.assertEqual(
            payload["error_type"],
            "memory_write_not_implemented",
        )
        self.assertFalse(payload["memory_written"])
        self.assertFalse(payload["journal_written"])
        self.assertFalse(payload["external_action_performed"])

    def test_see_requires_json_and_observation(self) -> None:
        not_json = self.client.post(
            "/api/see",
            data="texte",
            content_type="text/plain",
        )
        self.assertEqual(not_json.status_code, 415)
        self.assertEqual(
            not_json.get_json()["error_type"],
            "json_content_type_required",
        )

        missing = self.client.post("/api/see", json={})
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(
            missing.get_json()["error_type"],
            "observation_required",
        )

    def test_malformed_json_returns_json_error(self) -> None:
        response = self.client.post(
            "/api/dialogue",
            data='{"message":',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.is_json)
        self.assertEqual(
            response.get_json()["error_type"],
            "malformed_json",
        )

    def test_dialogue_validates_message_type_and_length(self) -> None:
        non_string = self.client.post(
            "/api/dialogue",
            json={"message": 42},
        )
        self.assertEqual(non_string.status_code, 400)
        self.assertEqual(
            non_string.get_json()["error_type"],
            "message_required",
        )

        server.app.config["MAX_DIALOGUE_MESSAGE_CHARS"] = 4
        too_long = self.client.post(
            "/api/dialogue",
            json={"message": "12345"},
        )
        self.assertEqual(too_long.status_code, 413)
        self.assertEqual(
            too_long.get_json()["error_type"],
            "message_too_long",
        )

    def test_dialogue_delegates_to_core(self) -> None:
        expected = {
            "response": "Réponse attribuée.",
            "journal_written": True,
        }
        with patch.object(
            server.eliot_jr,
            "think",
            return_value=expected,
        ) as think:
            response = self.client.post(
                "/api/dialogue",
                json={"message": "  question vérifiable  "},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), expected)
        think.assert_called_once_with("question vérifiable")

    def test_dialogue_exposes_synthesis_refusal_without_write_claim(self) -> None:
        with patch.object(
            server.eliot_jr,
            "think",
            side_effect=SynthesisValidationError("source absente"),
        ):
            response = self.client.post(
                "/api/dialogue",
                json={"message": "Fais une synthèse."},
            )

        self.assertEqual(response.status_code, 422)
        payload = response.get_json()
        self.assertEqual(
            payload["error_type"],
            "synthesis_validation_failed",
        )
        self.assertFalse(payload["journal_written"])
        self.assertFalse(payload["fragment_usage_recorded"])
        self.assertFalse(payload["temporal_state_committed"])
        self.assertFalse(payload["external_action_performed"])

    def test_dialogue_rejects_non_object_core_result(self) -> None:
        with patch.object(
            server.eliot_jr,
            "think",
            return_value="résultat invalide",
        ):
            response = self.client.post(
                "/api/dialogue",
                json={"message": "Question."},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json()["error_type"],
            "dialogue_result_invalid",
        )

    def test_request_body_limit_returns_json_413(self) -> None:
        server.app.config["MAX_CONTENT_LENGTH"] = 64
        response = self.client.post(
            "/api/dialogue",
            data=json.dumps({"message": "x" * 200}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 413)
        self.assertTrue(response.is_json)
        self.assertEqual(
            response.get_json()["error_type"],
            "request_too_large",
        )

    def test_corrupt_local_graph_returns_503_not_500(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            wisdom = Path(temp_dir)
            (wisdom / "voice_of_eliot.json").write_text(
                "{broken",
                encoding="utf-8",
            )
            with patch.object(server, "WISDOM_PATH", wisdom):
                response = self.client.get("/api/voice-of-eliot")

        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.is_json)
        self.assertEqual(
            response.get_json()["error_type"],
            "local_json_unavailable",
        )

    def test_backup_scan_reports_missing_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "absent"
            with patch.object(server, "BACKUP_PATH", missing):
                response = self.client.get("/api/scan-backup")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json()["error_type"],
            "backup_path_unavailable",
        )

    def test_unknown_endpoint_and_wrong_method_return_json(self) -> None:
        unknown = self.client.get("/api/inconnue")
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(
            unknown.get_json()["error_type"],
            "endpoint_not_found",
        )

        wrong_method = self.client.get("/api/dialogue")
        self.assertEqual(wrong_method.status_code, 405)
        self.assertEqual(
            wrong_method.get_json()["error_type"],
            "method_not_allowed",
        )


if __name__ == "__main__":
    unittest.main()
