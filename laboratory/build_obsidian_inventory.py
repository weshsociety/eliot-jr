#!/usr/bin/env python3

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "connectors/obsidian/read_only_client.py"
OUTPUT = ROOT / "laboratory/index/obsidian_inventory.json"

DIRECTORIES = (
    "000_synthèse",
    "00_Méthode",
    "01_Acteurs",
    "02_Flux",
    "03_Chronologie",
    "04_Patterns",
    "05_Cartes",
    "06_Hypothèses",
    "07_Sources",
    "08_Résistances",
    "09_Livre",
)


def call_client(*args: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(CLIENT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Erreur du connecteur Obsidian")

    return json.loads(result.stdout)


def list_notes(directory: str) -> list[str]:
    try:
        data = call_client("list", directory)
    except RuntimeError as exc:
        # Les dossiers vides peuvent ne pas être exposés par l’API.
        if "404" in str(exc):
            return []
        raise

    entries = data.get("files", [])
    notes: list[str] = []

    for entry in entries:
        path = f"{directory}/{entry}".replace("//", "/")

        if entry.endswith("/"):
            notes.extend(list_notes(path.rstrip("/")))
        elif entry.lower().endswith(".md"):
            notes.append(path)

    return notes


def read_note(path: str) -> str:
    data = call_client("read", path)
    return data.get("content", "")


def classify_path(path: str) -> str:
    root = path.split("/", 1)[0]

    return {
        "000_synthèse": "synthese",
        "00_Méthode": "methode",
        "01_Acteurs": "acteur",
        "02_Flux": "flux",
        "03_Chronologie": "chronologie",
        "04_Patterns": "pattern",
        "05_Cartes": "carte",
        "06_Hypothèses": "hypothese",
        "07_Sources": "source_presumee",
        "08_Résistances": "resistance",
        "09_Livre": "manuscrit",
    }.get(root, "non_classe")


def main() -> int:
    notes: list[str] = []

    for directory in DIRECTORIES:
        notes.extend(list_notes(directory))

    notes = sorted(set(notes))
    documents = []

    for index, path in enumerate(notes, start=1):
        content = read_note(path)
        encoded = content.encode("utf-8")

        documents.append(
            {
                "document_id": f"obsidian_{index:04d}",
                "path": path,
                "path_classification": classify_path(path),
                "classification_status": "presumee_par_emplacement",
                "size_bytes": len(encoded),
                "characters": len(content),
                "lines": len(content.splitlines()),
                "sha256": hashlib.sha256(encoded).hexdigest(),
                "source_system": "obsidian_plan_mondial",
                "content_stored_in_inventory": False,
            }
        )

        print(f"[{index:03d}/{len(notes):03d}] {path}", file=sys.stderr)

    inventory = {
        "schema": "eliot-jr.obsidian-inventory.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "vault": "plan mondial",
        "access_mode": "read_only",
        "llm_used": False,
        "document_count": len(documents),
        "documents": documents,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(OUTPUT)

    print(json.dumps({
        "status": "inventory_created",
        "document_count": len(documents),
        "output": str(OUTPUT),
        "sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
    }, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
