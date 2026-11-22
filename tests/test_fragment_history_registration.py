import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from core.fragment_history import (
    attach_fragment_metadata,
    register_missing_fragments,
)


class FragmentHistoryRegistrationTests(unittest.TestCase):
    def test_registers_only_missing_fragments(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "fragment_history.json"

            records = attach_fragment_metadata([
                {
                    "file": ".memory/example.json",
                    "section": "items",
                    "data": {"name": "alpha"},
                }
            ])

            memory_id = records[0]["memory_id"]

            registry, report, warnings = register_missing_fragments(
                records=records,
                registry_path=registry_path,
                now=datetime(
                    2026, 10, 9, 12, 0,
                    tzinfo=timezone.utc,
                ),
                commit=True,
            )

            self.assertEqual(warnings, [])
            self.assertEqual(report["new_memories"], 1)
            self.assertIn(memory_id, registry["memories"])
            self.assertEqual(
                registry["memories"][memory_id]["observation_count"],
                1,
            )

            first = json.loads(
                registry_path.read_text(encoding="utf-8")
            )

            registry, report, warnings = register_missing_fragments(
                records=records,
                registry_path=registry_path,
                now=datetime(
                    2026, 10, 9, 13, 0,
                    tzinfo=timezone.utc,
                ),
                commit=True,
            )

            second = json.loads(
                registry_path.read_text(encoding="utf-8")
            )

            self.assertEqual(warnings, [])
            self.assertEqual(report["new_memories"], 0)
            self.assertEqual(first, second)
            self.assertEqual(
                registry["memories"][memory_id]["observation_count"],
                1,
            )


    def test_does_not_overwrite_unreadable_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "fragment_history.json"
            original = "{broken-json"
            registry_path.write_text(
                original,
                encoding="utf-8",
            )

            records = attach_fragment_metadata([
                {
                    "file": ".memory/example.json",
                    "section": "items",
                    "data": {"name": "alpha"},
                }
            ])

            _, report, warnings = register_missing_fragments(
                records=records,
                registry_path=registry_path,
                now=datetime(
                    2026, 10, 9, 12, 0,
                    tzinfo=timezone.utc,
                ),
                commit=True,
            )

            self.assertEqual(report["new_memories"], 0)
            self.assertFalse(report["committed"])
            self.assertTrue(warnings)
            self.assertEqual(
                registry_path.read_text(encoding="utf-8"),
                original,
            )

    def test_does_not_overwrite_invalid_memories_collection(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "fragment_history.json"

            original = {
                "version": 1,
                "memories": [],
            }
            registry_path.write_text(
                json.dumps(original),
                encoding="utf-8",
            )

            records = attach_fragment_metadata([
                {
                    "file": ".memory/example.json",
                    "section": "items",
                    "data": {"name": "alpha"},
                }
            ])

            _, report, warnings = register_missing_fragments(
                records=records,
                registry_path=registry_path,
                now=datetime(
                    2026, 10, 9, 12, 0,
                    tzinfo=timezone.utc,
                ),
                commit=True,
            )

            self.assertEqual(report["new_memories"], 0)
            self.assertFalse(report["committed"])
            self.assertTrue(warnings)
            self.assertEqual(
                json.loads(
                    registry_path.read_text(encoding="utf-8")
                ),
                original,
            )


if __name__ == "__main__":
    unittest.main()
