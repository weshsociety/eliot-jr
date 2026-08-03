#!/usr/bin/env python3

import argparse
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "connectors/obsidian/read_only_client.py"
INVENTORY = ROOT / "laboratory/index/obsidian_inventory.json"
OUTPUT = (
    ROOT
    / "investigations/epstein_trou_de_souris"
    / "extractions/pilot_claim_candidates.json"
)

DEFAULT_PATHS = (
    "01_Acteurs/Bill_Gates.md",
    "04_Patterns/CHAIN_OF_CAPTURE_1.md",
    "000_synthèse/POINT_DE_BASCULE.md",
)


def normalize(text: str) -> str:
    text = text.casefold().replace("’", "'")
    text = unicodedata.normalize("NFKD", text)

    return "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )


RULES = {
    "research_instruction": (
        r"\bcreuser\b",
        r"\bdocumenter\b",
        r"\bverifier\b",
        r"\bchercher\b",
        r"\bretrouver\b",
        r"\bcomparer\b",
        r"\bidentifier\b",
        r"\bcartographier\b",
        r"\bexaminer\b",
        r"\binvestiguer\b",
        r"\bconfirmer\b",
    ),
    "negation_marker": (
        r"\bpas de preuve\b",
        r"\baucune preuve\b",
        r"\bsans preuve\b",
        r"\babsence d['e]\b",
        r"\bn['a-z]+ jamais\b",
        r"\bne\b.{0,100}\bpas\b",
        r"\bn['a-z]+\b.{0,100}\bpas\b",
    ),
    "hypothesis": (
        r"\bpeut-etre\b",
        r"\bpourrait\b",
        r"\bserait\b",
        r"\bprobablement\b",
        r"\bhypothese\b",
        r"\bpossible\b",
        r"\bsemble\b",
        r"\bsuggere\b",
        r"\bcoincidence\b",
    ),
    "attribution_marker": (
        r"\bselon\b",
        r"\bd'apres\b",
        r"\ba declare\b",
        r"\bont declare\b",
        r"\brapporte\b",
        r"\bindique\b",
        r"\baffirme\b",
        r"\ba confirme\b",
        r"\bont confirme\b",
        r"\bsous serment\b",
        r"\bpubliquement\b",
    ),
    # « publiquement » établit une attribution publique, pas une
    # observation directe par la personne qui écrit la note.
    "direct_observation_marker": (
        r"\bj'ai vu\b",
        r"\bj'y etais\b",
        r"\bnous avons vu\b",
        r"\bsous mes yeux\b",
    ),
    "structural_interpretation": (
        r"\ble systeme\b",
        r"\bcela montre\b",
        r"\bcela revele\b",
        r"\bconsequence\b",
        r"\bpattern\b",
        r"\barchitecture\b",
        r"\bradiographie\b",
        r"\bbascule\b",
        r"\bretrait du consentement\b",
    ),
    "source_reference": (
        r"\bdoj files\b",
        r"\brapports? publics?\b",
        r"\bdeclarations? publiques?\b",
        r"\barchives?\b",
        r"\bsource\b",
    ),
}


def load_inventory() -> dict:
    try:
        return json.loads(
            INVENTORY.read_text(encoding="utf-8")
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Inventaire introuvable : {INVENTORY}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Inventaire JSON invalide : {exc}"
        ) from exc


def read_note(path: str) -> str:
    result = subprocess.run(
        [sys.executable, str(CLIENT), "read", path],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"{path}: {message}")

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Réponse invalide pour {path}: {exc}"
        ) from exc

    return payload.get("content", "")


def is_ignored_line(line: str, in_frontmatter: bool) -> bool:
    stripped = line.strip()

    if not stripped:
        return True

    if stripped == "---":
        return True

    if in_frontmatter:
        return True

    if stripped.startswith("#"):
        return True

    if re.fullmatch(r"\|?[\s:|-]+\|?", stripped):
        return True

    return False


def classify_line(line: str) -> tuple[list[str], list[str]]:
    normalized = normalize(line)
    categories = []
    markers = []

    if "?" in line:
        categories.append("question")
        markers.append("question_mark")

    if (
        re.search(r"\b(?:18|19|20)\d{2}\b", normalized)
        and line.lstrip().startswith("|")
    ):
        categories.append("chronology_entry")
        markers.append("year_in_table_row")

    if line.lstrip().startswith(">"):
        categories.append("quoted_statement")
        markers.append("markdown_blockquote")

    for category, patterns in RULES.items():
        matched_patterns = [
            pattern
            for pattern in patterns
            if re.search(pattern, normalized)
        ]

        if matched_patterns:
            categories.append(category)
            markers.extend(
                f"{category}:{pattern}"
                for pattern in matched_patterns
            )

    if not categories:
        visible = re.sub(
            r"^[\s>*+-]+|^\s*\|",
            "",
            line,
        ).strip()

        if len(visible) >= 20:
            categories.append("surface_statement")
            markers.append("non_empty_declarative_surface")

    return list(dict.fromkeys(categories)), markers


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Extraction mécanique d’affirmations candidates "
            "depuis Obsidian"
        )
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=DEFAULT_PATHS,
    )
    args = parser.parse_args()

    inventory = load_inventory()
    indexed = {
        document["path"]: document
        for document in inventory["documents"]
    }

    candidates = []
    documents = []
    errors = []

    for path in args.paths:
        try:
            content = read_note(path)
        except RuntimeError as exc:
            errors.append({
                "path": path,
                "error": str(exc),
            })
            continue

        encoded = content.encode("utf-8")
        current_sha = hashlib.sha256(encoded).hexdigest()
        inventory_document = indexed.get(path)
        inventory_sha = (
            inventory_document.get("sha256")
            if inventory_document
            else None
        )

        documents.append({
            "path": path,
            "current_sha256": current_sha,
            "inventory_sha256": inventory_sha,
            "inventory_state": (
                "unchanged"
                if inventory_sha == current_sha
                else "changed_or_not_indexed"
            ),
            "lines": len(content.splitlines()),
        })

        in_frontmatter = False

        for line_number, line in enumerate(
            content.splitlines(),
            start=1,
        ):
            if line.strip() == "---":
                in_frontmatter = not in_frontmatter
                continue

            if is_ignored_line(line, in_frontmatter):
                continue

            categories, markers = classify_line(line)

            if not categories:
                continue

            candidate_number = len(candidates) + 1

            candidates.append({
                "candidate_id": f"claim_{candidate_number:05d}",
                "source_path": path,
                "source_sha256": current_sha,
                "line_start": line_number,
                "line_end": line_number,
                "verbatim_excerpt": line,
                "surface_categories": categories,
                "matched_markers": markers,
                "classification_basis": (
                    "deterministic_surface_rules_v3"
                ),
                "truth_status": "not_assessed",
                "relation_created": False,
                "llm_used": False,
            })

    category_counts = Counter(
        category
        for candidate in candidates
        for category in candidate["surface_categories"]
    )

    report = {
        "schema": "eliot-jr.claim-candidates.v2",
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "vault": inventory.get("vault"),
        "scope": "pilot_three_documents",
        "access_mode": "read_only",
        "classification_method": (
            "deterministic_surface_rules_v3"
        ),
        "llm_used": False,
        "core_modified": False,
        "relations_created": 0,
        "documents": documents,
        "candidate_count": len(candidates),
        "category_counts": dict(
            sorted(category_counts.items())
        ),
        "candidates": candidates,
        "errors": errors,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".json.tmp")

    temporary.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    temporary.replace(OUTPUT)

    print(json.dumps({
        "status": "pilot_created",
        "documents_processed": len(documents),
        "candidate_count": len(candidates),
        "category_counts": report["category_counts"],
        "errors": errors,
        "output": str(OUTPUT),
        "output_sha256": hashlib.sha256(
            OUTPUT.read_bytes()
        ).hexdigest(),
        "llm_used": False,
        "core_modified": False,
        "relations_created": 0,
    }, ensure_ascii=False, indent=2))

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
