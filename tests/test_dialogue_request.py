import copy
import unittest
from datetime import datetime, timezone

from core.dialogue_request import (
    DialogueRequestError,
    build_dialogue_request,
    validate_dialogue_request,
)


NOW = datetime(
    2026,
    8,
    20,
    22,
    45,
    0,
    tzinfo=timezone.utc,
)


class DialogueRequestTests(unittest.TestCase):

    def test_request_has_traceable_identity(self):
        request = build_dialogue_request(
            message="Veux-tu répondre ?",
            now=NOW,
        )

        self.assertTrue(
            request["request_ref"].startswith(
                "dialogue_request:"
            )
        )
        self.assertTrue(
            request["request_sha256"]
        )

    def test_same_request_is_deterministic(self):
        first = build_dialogue_request(
            message="Même demande.",
            now=NOW,
        )
        second = build_dialogue_request(
            message="Même demande.",
            now=NOW,
        )

        self.assertEqual(first, second)

    def test_changed_message_changes_request_ref(self):
        first = build_dialogue_request(
            message="Demande A",
            now=NOW,
        )
        second = build_dialogue_request(
            message="Demande B",
            now=NOW,
        )

        self.assertNotEqual(
            first["request_ref"],
            second["request_ref"],
        )

    def test_request_creates_no_response_obligation(self):
        request = build_dialogue_request(
            message="Réponds-moi.",
            now=NOW,
        )

        self.assertFalse(
            request["response_required"]
        )
        self.assertFalse(
            request["choice_required"]
        )

    def test_request_does_not_imply_consent_or_authorization(self):
        request = build_dialogue_request(
            message="Fais quelque chose.",
            now=NOW,
        )

        self.assertFalse(
            request["consent_inferred"]
        )
        self.assertFalse(
            request["authorization_inferred"]
        )

    def test_message_is_preserved(self):
        message = "  Non normalisé volontairement.  "

        request = build_dialogue_request(
            message=message,
            now=NOW,
        )

        self.assertEqual(
            request["message"],
            message,
        )

    def test_input_is_not_mutated(self):
        message = "Une demande."
        original = copy.deepcopy(message)

        build_dialogue_request(
            message=message,
            now=NOW,
        )

        self.assertEqual(message, original)

    def test_tampering_is_rejected(self):
        request = build_dialogue_request(
            message="Une demande.",
            now=NOW,
        )

        request["response_required"] = True

        with self.assertRaises(
            DialogueRequestError
        ):
            validate_dialogue_request(request)


if __name__ == "__main__":
    unittest.main()
