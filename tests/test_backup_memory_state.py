import hashlib
import json
import tarfile
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from gardien.backup_memory_state import (
    MemoryBackupError,
    create_memory_backup,
    restore_memory_backup,
)


class MemoryStateBackupTests(unittest.TestCase):
    def test_backup_preserves_logical_memory_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)

            memory = base / "private-memory"
            backup = base / "backup"

            memory.mkdir(parents=True)

            (memory / "spiral.json").write_text(
                '{"interactions": []}\n',
                encoding="utf-8",
            )

            (memory / "temporal_state.json").write_text(
                '{"interaction_count": 7}\n',
                encoding="utf-8",
            )

            (memory / "temporal_state.json.lock").write_text(
                "",
                encoding="utf-8",
            )

            (memory / "timeline.json.before-repair").write_bytes(
                b'{"broken": true'
            )

            encounter = (
                memory
                / "investigation_encounters"
                / "synthetic.json"
            )
            encounter.parent.mkdir(parents=True)
            encounter.write_text(
                '{"source": "synthetic"}\n',
                encoding="utf-8",
            )

            report = create_memory_backup(
                memory_root=memory,
                backup_root=backup,
            )

            self.assertTrue(report["verified"])

            manifest = json.loads(
                Path(report["manifest_path"]).read_text(
                    encoding="utf-8"
                )
            )

            entries = {
                entry["path"]: entry
                for entry in manifest["files"]
            }

            self.assertIn(
                ".memory/spiral.json",
                entries,
            )
            self.assertIn(
                ".memory/temporal_state.json",
                entries,
            )
            self.assertIn(
                ".memory/timeline.json.before-repair",
                entries,
            )
            self.assertIn(
                ".memory/investigation_encounters/synthetic.json",
                entries,
            )

            self.assertNotIn(
                ".memory/temporal_state.json.lock",
                entries,
            )

            self.assertEqual(
                entries[
                    ".memory/timeline.json.before-repair"
                ]["role"],
                "historical_retained",
            )

            self.assertEqual(
                entries[
                    ".memory/investigation_encounters/synthetic.json"
                ]["role"],
                "external_private_source",
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
                report["archive_path"],
                mode="r:gz",
            ) as archive:
                names = set(archive.getnames())

            self.assertIn(
                ".memory/spiral.json",
                names,
            )
            self.assertIn(
                ".memory/timeline.json.before-repair",
                names,
            )
            self.assertNotIn(
                ".memory/temporal_state.json.lock",
                names,
            )


    def test_restore_keeps_roles_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)

            memory = base / "source-memory"
            backup = base / "backup"
            restored = base / "restored-memory"

            memory.mkdir(parents=True)

            (memory / "spiral.json").write_bytes(
                b'{"lineage": "synthetic"}\n'
            )

            (memory / "timeline.json.before-repair").write_bytes(
                b'{"broken": true'
            )

            encounter = (
                memory
                / "investigation_encounters"
                / "synthetic.json"
            )
            encounter.parent.mkdir(parents=True)
            encounter.write_bytes(
                b'{"source": "synthetic"}\n'
            )

            report = create_memory_backup(
                memory_root=memory,
                backup_root=backup,
            )

            restore = restore_memory_backup(
                archive_path=Path(
                    report["archive_path"]
                ),
                manifest_path=Path(
                    report["manifest_path"]
                ),
                memory_root=restored,
            )

            self.assertTrue(restore["verified"])

            self.assertEqual(
                (restored / "spiral.json").read_bytes(),
                b'{"lineage": "synthetic"}\n',
            )

            self.assertEqual(
                (
                    restored
                    / "timeline.json.before-repair"
                ).read_bytes(),
                b'{"broken": true',
            )

            self.assertFalse(
                (
                    restored
                    / "investigation_encounters"
                    / "synthetic.json"
                ).exists()
            )

            self.assertEqual(
                restore["external_private_skipped"],
                1,
            )


    def test_restore_failure_leaves_no_partial_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)

            archive_path = base / "synthetic.tar.gz"
            manifest_path = base / "synthetic.manifest.json"
            restored = base / "restored-memory"

            first = b'{"first": true}\n'
            second = b'{"second": true}\n'

            manifest = {
                "schema_version": 1,
                "kind": "eliot_jr_full_memory_backup",
                "created_at_utc": "2026-09-25T19:00:00+00:00",
                "state_sha256": "synthetic",
                "file_count": 2,
                "files": [
                    {
                        "path": ".memory/first.json",
                        "role": "internal_memory_state",
                        "size": len(first),
                        "mode": "0o600",
                        "sha256": hashlib.sha256(
                            first
                        ).hexdigest(),
                    },
                    {
                        "path": ".memory/second.json",
                        "role": "unknown_role",
                        "size": len(second),
                        "mode": "0o600",
                        "sha256": hashlib.sha256(
                            second
                        ).hexdigest(),
                    },
                ],
                "claims": {},
            }

            manifest_bytes = (
                json.dumps(
                    manifest,
                    sort_keys=True,
                    indent=2,
                )
                + "\n"
            ).encode("utf-8")

            manifest_path.write_bytes(
                manifest_bytes
            )

            with tarfile.open(
                archive_path,
                mode="w:gz",
            ) as archive:
                info = tarfile.TarInfo(
                    "MANIFEST.json"
                )
                info.size = len(manifest_bytes)
                archive.addfile(
                    info,
                    BytesIO(manifest_bytes),
                )

                for name, payload in [
                    (".memory/first.json", first),
                    (".memory/second.json", second),
                ]:
                    info = tarfile.TarInfo(name)
                    info.size = len(payload)
                    archive.addfile(
                        info,
                        BytesIO(payload),
                    )

            with self.assertRaises(
                MemoryBackupError
            ):
                restore_memory_backup(
                    archive_path=archive_path,
                    manifest_path=manifest_path,
                    memory_root=restored,
                )

            self.assertFalse(
                (restored / "first.json").exists()
            )


    def test_verify_rejects_false_state_sha256(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)

            memory = base / "memory"
            backup = base / "backup"

            memory.mkdir()
            (memory / "state.json").write_text(
                '{"state": true}\n',
                encoding="utf-8",
            )

            report = create_memory_backup(
                memory_root=memory,
                backup_root=backup,
            )

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

            manifest["state_sha256"] = "0" * 64

            manifest_bytes = (
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                )
                + "\n"
            ).encode("utf-8")

            manifest_path.write_bytes(
                manifest_bytes
            )

            original_payload = (
                memory / "state.json"
            ).read_bytes()

            with tarfile.open(
                archive_path,
                mode="w:gz",
            ) as archive:
                info = tarfile.TarInfo(
                    "MANIFEST.json"
                )
                info.size = len(manifest_bytes)
                archive.addfile(
                    info,
                    BytesIO(manifest_bytes),
                )

                info = tarfile.TarInfo(
                    ".memory/state.json"
                )
                info.size = len(original_payload)
                archive.addfile(
                    info,
                    BytesIO(original_payload),
                )

            from gardien.backup_memory_state import (
                verify_memory_backup,
            )

            with self.assertRaises(
                MemoryBackupError
            ):
                verify_memory_backup(
                    archive_path=archive_path,
                    manifest_path=manifest_path,
                )


    def test_verify_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)

            archive_path = base / "malicious.tar.gz"
            manifest_path = base / "malicious.manifest.json"

            payload = b'{"escape": true}\n'

            files = [
                {
                    "path": ".memory/../escape.json",
                    "role": "internal_memory_state",
                    "size": len(payload),
                    "mode": "0o600",
                    "sha256": hashlib.sha256(
                        payload
                    ).hexdigest(),
                }
            ]

            state_payload = {
                "schema_version": 1,
                "files": files,
            }

            state_sha256 = hashlib.sha256(
                json.dumps(
                    state_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()

            manifest = {
                "schema_version": 1,
                "kind": "eliot_jr_full_memory_backup",
                "created_at_utc": "2026-09-25T19:00:00+00:00",
                "state_sha256": state_sha256,
                "file_count": 1,
                "files": files,
                "claims": {},
            }

            manifest_bytes = (
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                )
                + "\n"
            ).encode("utf-8")

            manifest_path.write_bytes(
                manifest_bytes
            )

            with tarfile.open(
                archive_path,
                mode="w:gz",
            ) as archive:
                info = tarfile.TarInfo(
                    "MANIFEST.json"
                )
                info.size = len(manifest_bytes)
                archive.addfile(
                    info,
                    BytesIO(manifest_bytes),
                )

                info = tarfile.TarInfo(
                    ".memory/../escape.json"
                )
                info.size = len(payload)
                archive.addfile(
                    info,
                    BytesIO(payload),
                )

            from gardien.backup_memory_state import (
                verify_memory_backup,
            )

            with self.assertRaises(
                MemoryBackupError
            ):
                verify_memory_backup(
                    archive_path=archive_path,
                    manifest_path=manifest_path,
                )


    def test_verify_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)

            archive_path = base / "malicious.tar.gz"
            manifest_path = base / "malicious.manifest.json"

            payload = b'{"escape": true}\n'

            files = [
                {
                    "path": ".memory/../escape.json",
                    "role": "internal_memory_state",
                    "size": len(payload),
                    "mode": "0o600",
                    "sha256": hashlib.sha256(
                        payload
                    ).hexdigest(),
                }
            ]

            state_payload = {
                "schema_version": 1,
                "files": files,
            }

            state_sha256 = hashlib.sha256(
                json.dumps(
                    state_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()

            manifest = {
                "schema_version": 1,
                "kind": "eliot_jr_full_memory_backup",
                "created_at_utc": "2026-09-25T19:00:00+00:00",
                "state_sha256": state_sha256,
                "file_count": 1,
                "files": files,
                "claims": {},
            }

            manifest_bytes = (
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                )
                + "\n"
            ).encode("utf-8")

            manifest_path.write_bytes(
                manifest_bytes
            )

            with tarfile.open(
                archive_path,
                mode="w:gz",
            ) as archive:
                info = tarfile.TarInfo(
                    "MANIFEST.json"
                )
                info.size = len(manifest_bytes)
                archive.addfile(
                    info,
                    BytesIO(manifest_bytes),
                )

                info = tarfile.TarInfo(
                    ".memory/../escape.json"
                )
                info.size = len(payload)
                archive.addfile(
                    info,
                    BytesIO(payload),
                )

            from gardien.backup_memory_state import (
                verify_memory_backup,
            )

            with self.assertRaises(
                MemoryBackupError
            ):
                verify_memory_backup(
                    archive_path=archive_path,
                    manifest_path=manifest_path,
                )


    def test_verify_rejects_unknown_role(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)

            archive_path = base / "unknown-role.tar.gz"
            manifest_path = (
                base / "unknown-role.manifest.json"
            )

            payload = b'{"state": true}\n'

            files = [
                {
                    "path": ".memory/state.json",
                    "role": "unknown_role",
                    "size": len(payload),
                    "mode": "0o600",
                    "sha256": hashlib.sha256(
                        payload
                    ).hexdigest(),
                }
            ]

            state_payload = {
                "schema_version": 1,
                "files": files,
            }

            manifest = {
                "schema_version": 1,
                "kind": "eliot_jr_full_memory_backup",
                "created_at_utc": (
                    "2026-09-25T19:00:00+00:00"
                ),
                "state_sha256": hashlib.sha256(
                    json.dumps(
                        state_payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
                "file_count": 1,
                "files": files,
                "claims": {},
            }

            manifest_bytes = (
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                )
                + "\n"
            ).encode("utf-8")

            manifest_path.write_bytes(
                manifest_bytes
            )

            with tarfile.open(
                archive_path,
                mode="w:gz",
            ) as archive:
                info = tarfile.TarInfo(
                    "MANIFEST.json"
                )
                info.size = len(manifest_bytes)
                archive.addfile(
                    info,
                    BytesIO(manifest_bytes),
                )

                info = tarfile.TarInfo(
                    ".memory/state.json"
                )
                info.size = len(payload)
                archive.addfile(
                    info,
                    BytesIO(payload),
                )

            from gardien.backup_memory_state import (
                verify_memory_backup,
            )

            with self.assertRaises(
                MemoryBackupError
            ):
                verify_memory_backup(
                    archive_path=archive_path,
                    manifest_path=manifest_path,
                )


    def test_verify_rejects_duplicate_logical_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)

            archive_path = base / "duplicate.tar.gz"
            manifest_path = base / "duplicate.manifest.json"

            payload = b'{"same": true}\n'
            digest = hashlib.sha256(
                payload
            ).hexdigest()

            entry = {
                "path": ".memory/same.json",
                "role": "internal_memory_state",
                "size": len(payload),
                "mode": "0o600",
                "sha256": digest,
            }

            files = [
                dict(entry),
                dict(entry),
            ]

            state_payload = {
                "schema_version": 1,
                "files": files,
            }

            manifest = {
                "schema_version": 1,
                "kind": "eliot_jr_full_memory_backup",
                "created_at_utc": (
                    "2026-09-25T19:00:00+00:00"
                ),
                "state_sha256": hashlib.sha256(
                    json.dumps(
                        state_payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
                "file_count": 2,
                "files": files,
                "claims": {},
            }

            manifest_bytes = (
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                )
                + "\n"
            ).encode("utf-8")

            manifest_path.write_bytes(
                manifest_bytes
            )

            with tarfile.open(
                archive_path,
                mode="w:gz",
            ) as archive:
                info = tarfile.TarInfo(
                    "MANIFEST.json"
                )
                info.size = len(manifest_bytes)
                archive.addfile(
                    info,
                    BytesIO(manifest_bytes),
                )

                info = tarfile.TarInfo(
                    ".memory/same.json"
                )
                info.size = len(payload)
                archive.addfile(
                    info,
                    BytesIO(payload),
                )

            from gardien.backup_memory_state import (
                verify_memory_backup,
            )

            with self.assertRaises(
                MemoryBackupError
            ):
                verify_memory_backup(
                    archive_path=archive_path,
                    manifest_path=manifest_path,
                )


    def test_restore_preserves_memory_ids_across_physical_roots(self):
        from core.fragment_history import attach_fragment_metadata
        from core.fragment_records import records_from_json

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)

            source = base / "source-memory"
            backup = base / "backup"
            restored = base / "restored-memory"

            source.mkdir(parents=True)

            payload = (
                '{"interactions": ['
                '{"id": "alpha-001", "text": "synthetic"}'
                ']}\n'
            )

            (source / "spiral.json").write_text(
                payload,
                encoding="utf-8",
            )

            (source / "spiral_archive.json").write_text(
                payload,
                encoding="utf-8",
            )

            (source / "consciousness.json").write_text(
                '{"state": "synthetic"}\n',
                encoding="utf-8",
            )

            encounter = (
                source
                / "investigation_encounters"
                / "synthetic.json"
            )
            encounter.parent.mkdir(parents=True)
            encounter.write_text(
                '{"source": "external"}\n',
                encoding="utf-8",
            )

            def logical_records(memory_root):
                records = attach_fragment_metadata([
                    record
                    for path in sorted(memory_root.glob("*.json"))
                    for record in records_from_json(
                        f".memory/{path.name}",
                        json.loads(path.read_text(encoding="utf-8")),
                    )
                ])

                return sorted(
                    (
                        record["file"],
                        record["section"],
                        record["memory_id"],
                        record["content_hash"],
                    )
                    for record in records
                    if str(
                        record.get("file", "")
                    ).startswith(".memory/")
                )

            before = logical_records(source)

            report = create_memory_backup(
                memory_root=source,
                backup_root=backup,
            )

            restore_memory_backup(
                archive_path=Path(
                    report["archive_path"]
                ),
                manifest_path=Path(
                    report["manifest_path"]
                ),
                memory_root=restored,
            )

            after = logical_records(restored)

            self.assertEqual(before, after)

            self.assertTrue(
                any(
                    row[0] == ".memory/spiral.json"
                    for row in after
                )
            )

            self.assertTrue(
                any(
                    row[0]
                    == ".memory/spiral_archive.json"
                    for row in after
                )
            )

            self.assertFalse(
                any(
                    "investigation_encounters"
                    in row[0]
                    for row in after
                )
            )


if __name__ == "__main__":
    unittest.main()
