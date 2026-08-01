#!/usr/bin/env python3

import argparse
import hashlib
import itertools
import json
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "connectors/obsidian/read_only_client.py"
INVENTORY = ROOT / "laboratory/index/obsidian_inventory.json"


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold())
    return "".join(
        char for char in text
        if not unicodedata.combining(char)
    )


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


    payload = json.loads(result.stdout)
    return payload.get("content", "")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recherche lexicale de proximité dans Obsidian"
    )
    parser.add_argument("terms", nargs="+")
    parser.add_argument(
        "--span",
        type=int,
        default=4,
        help="Écart maximal entre les lignes contenant les termes",
    )
    parser.add_argument(
        "--context",
        type=int,
        default=1,
        help="Lignes de contexte autour de la fenêtre",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Nombre maximal de documents",
    )
    args = parser.parse_args()

    inventory = json.loads(
        INVENTORY.read_text(encoding="utf-8")
    )

    terms = [normalize(term) for term in args.terms]
    results = []
    errors = []

    for document in inventory["documents"]:
        path = document["path"]

        try:
            content = read_note(path)
        except Exception as exc:
            errors.append({"path": path, "error": str(exc)})
            continue

        lines = content.splitlines()
        normalized_lines = [normalize(line) for line in lines]

        occurrence_lists = [
            [
                index
                for index, line in enumerate(normalized_lines)
                if term in line
            ]
            for term in terms
        ]

        if any(not occurrences for occurrences in occurrence_lists):
            continue

        ranges = set()

        for combination in itertools.product(*occurrence_lists):
            first = min(combination)
            last = max(combination)

            if last - first <= args.span:
                ranges.add((first, last))

            if len(ranges) >= 5:
                break

        if not ranges:
            continue

        windows = []

        for first, last in sorted(ranges):
            excerpt_start = max(0, first - args.context)
            excerpt_end = min(
                len(lines),
                last + args.context + 1,
            )

            windows.append({
                "first_match_line": first + 1,
                "last_match_line": last + 1,
                "line_distance": last - first,
                "excerpt_start": excerpt_start + 1,
                "excerpt_end": excerpt_end,
                "excerpt": "\n".join(
                    lines[excerpt_start:excerpt_end]
                ),
            })

        current_sha = hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()

        results.append({
            "path": path,
            "classification": document.get(
                "path_classification"
            ),
            "inventory_state": (
                "unchanged"
                if current_sha == document.get("sha256")
                else "changed_since_inventory"
            ),
            "windows": windows,
        })

        if len(results) >= args.limit:
            break

    print("===== RECHERCHE DE PROXIMITÉ =====")
    print("Termes           :", ", ".join(args.terms))
    print("Écart maximal    :", args.span, "lignes")
    print("Documents trouvés:", len(results))
    print("LLM utilisé      : non")

    for number, result in enumerate(results, start=1):
        print()
        print(f"[{number}] {result['path']}")
        print("    classification :", result["classification"])
        print("    inventaire     :", result["inventory_state"])

        for window in result["windows"]:
            print(
                "    fenêtre        : lignes "
                f"{window['first_match_line']}–"
                f"{window['last_match_line']} "
                f"(distance {window['line_distance']})"
            )
            print(
                "        "
                + window["excerpt"].replace(
                    "\n",
                    "\n        ",
                )
            )

    if errors:
        print()
        print("Erreurs :", len(errors))
        for error in errors:
            print(f"- {error['path']}: {error['error']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
