import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from gardien.backup_reading_state import (
    create_backup,
)


class ReadingBackupMemoryBoundaryTests(
    unittest.TestCase
):
    def test_external_memory_keeps_legacy_backup_names(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)

            project = base / "project"
            memory = base / "private-memory"
            backup = base / "backup"

            journal = (
                project
                / "curriculum"
                / "journaux"
                / "synthetic.json"
            )

            candidate = (
                memory
                / "reading_candidates"
                / "candidate.json"
            )

            journal.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            candidate.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            journal.write_text(
                '{"journal": true}\n',
                encoding="utf-8",
            )

            candidate.write_text(
                '{"candidate": true}\n',
                encoding="utf-8",
            )

            report = create_backup(
                project_root=project,
                memory_root=memory,
                backup_root=backup,
            )

            self.assertTrue(report["verified"])

            manifest_path = Path(
                report["manifest_path"]
            )

            archive_path = Path(
                report["archive_path"]
            )

            manifest = json.loads(
                manifest_path.read_text(
                    encoding="utf-8"
                )
            )

            logical_paths = {
                entry["path"]
                for entry in manifest["files"]
            }

            self.assertEqual(
                logical_paths,
                {
                    "curriculum/journaux/synthetic.json",
                    ".memory/reading_candidates/candidate.json",
                },
            )

            manifest_text = json.dumps(
                manifest,
                sort_keys=True,
            )

            self.assertNotIn(
                str(memory.resolve()),
                manifest_text,
            )

            with tarfile.open(
                archive_path,
                mode="r:gz",
            ) as archive:
                names = set(
                    archive.getnames()
                )

            self.assertIn(
                ".memory/reading_candidates/candidate.json",
                names,
            )

            self.assertNotIn(
                str(memory.resolve()),
                names,
            )


if __name__ == "__main__":
    unittest.main()
