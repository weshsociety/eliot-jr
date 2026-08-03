import unittest

from connectors.obsidian.read_only_client import is_allowed, normalize_path


class ObsidianReadOnlyPolicyTests(unittest.TestCase):
    def test_allowed_investigation_path(self):
        self.assertTrue(
            is_allowed("000_synthèse/POINT_DE_BASCULE.md")
        )

    def test_path_outside_scope_is_refused(self):
        self.assertFalse(is_allowed("private/secret.md"))

    def test_relative_navigation_is_refused(self):
        with self.assertRaises(ValueError):
            normalize_path("../private/secret.md")

    def test_windows_separator_is_refused(self):
        with self.assertRaises(ValueError):
            normalize_path(r"01_Acteurs\\Test.md")


if __name__ == "__main__":
    unittest.main()
