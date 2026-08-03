import unittest

from laboratory.extract_claim_candidates import classify_line


class ClaimClassificationTests(unittest.TestCase):
    def test_public_statement_is_attributed_not_direct_observation(self):
        categories, _ = classify_line(
            "La déclaration a été faite publiquement selon le rapport."
        )

        self.assertIn("attribution_marker", categories)
        self.assertNotIn("direct_observation_marker", categories)

    def test_first_person_observation_is_detected(self):
        categories, _ = classify_line(
            "J'ai vu la réunion se dérouler sous mes yeux."
        )

        self.assertIn("direct_observation_marker", categories)

    def test_question_remains_explicitly_a_question(self):
        categories, _ = classify_line(
            "Quelle source primaire documente cette rencontre ?"
        )

        self.assertIn("question", categories)

    def test_negation_marker_is_preserved(self):
        categories, _ = classify_line(
            "Il n'y a pas de preuve établissant cette causalité."
        )

        self.assertIn("negation_marker", categories)


if __name__ == "__main__":
    unittest.main()
