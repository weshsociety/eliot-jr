#!/usr/bin/env python3

import argparse
import hashlib
import json
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "connectors/obsidian/read_only_client.py"
INVENTORY = ROOT / "laboratory/index/obsidian_inventory.json"


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())

    return "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )


def load_inventory() -> dict:
    try:
        data = json.loads(INVENTORY.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Inventaire introuvable : {INVENTORY}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Inventaire JSON invalide : {exc}"
        ) from exc

    documents = data.get("documents")

    if not isinstance(documents, list):
        raise RuntimeError("Champ documents absent ou invalide")

    return data


def read_note(path: str) -> str:
    result = subprocess.run(
        [
            sys.executable,
            str(CLIENT),
            "read",
            path,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            f"Lecture impossible pour {path}: {message}"
        )

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Réponse invalide pour {path}: {exc}"
        ) from exc

    return payload.get("content", "")


def extract_matches(
    content: str,
    normalized_terms: list[str],
    context: int,
    maximum: int = 5,
) -> list[dict]:
    lines = content.splitlines()
    matches = []

    for index, line in enumerate(lines):
        normalized_line = normalize(line)

        if not any(term in normalized_line for term in normalized_terms):
            continue

        start = max(0, index - context)
        end = min(len(lines), index + context + 1)

        matches.append({
            "line": index + 1,
            "excerpt_start": start + 1,
            "excerpt_end": end,
            "excerpt": "\n".join(lines[start:end]),
        })

        if len(matches) >= maximum:
            break

    return matches


def search_documents(args: argparse.Namespace) -> int:
    inventory = load_inventory()
    documents = inventory["documents"]

    terms = [term.strip() for term in args.terms if term.strip()]

    if not terms:
        raise RuntimeError("Aucun terme de recherche fourni")

    normalized_terms = [normalize(term) for term in terms]

    results = []
    scanned = 0
    errors = []

    for document in documents:
        classification = document.get(
            "path_classification",
            "non_classe",
        )

        if (
            args.classification
            and classification != args.classification
        ):
            continue

        path = document["path"]

        try:
            content = read_note(path)
        except RuntimeError as exc:
            errors.append({
                "path": path,
                "error": str(exc),
            })
            continue

        scanned += 1
        normalized_content = normalize(content)

        if args.any:
            matched = any(
                term in normalized_content
                for term in normalized_terms
            )
        else:
            matched = all(
                term in normalized_content
                for term in normalized_terms
            )

        if not matched:
            continue

        current_sha = hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()

        inventory_sha = document.get("sha256", "")

        results.append({
            "document_id": document.get("document_id"),
            "path": path,
            "classification": classification,
            "classification_status": document.get(
                "classification_status"
            ),
            "inventory_sha256": inventory_sha,
            "current_sha256": current_sha,
            "inventory_state": (
                "unchanged"
                if current_sha == inventory_sha
                else "changed_since_inventory"
            ),
            "matches": extract_matches(
                content,
                normalized_terms,
                args.context,
            ),
        })

        if len(results) >= args.limit:
            break

    report = {
        "schema": "eliot-jr.obsidian-query.v1",
        "query": {
            "terms": terms,
            "mode": "any" if args.any else "all",
            "classification": args.classification,
        },
        "vault": inventory.get("vault"),
        "access_mode": "read_only",
        "llm_used": False,
        "documents_scanned": scanned,
        "result_count": len(results),
        "results": results,
        "errors": errors,
    }

    if args.json:
        print(
            json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print("===== RECHERCHE DOCUMENTAIRE =====")
    print("Termes             :", ", ".join(terms))
    print("Mode               :", report["query"]["mode"])
    print("Documents parcourus:", scanned)
    print("Résultats          :", len(results))
    print("LLM utilisé        : non")

    for number, result in enumerate(results, start=1):
        print()
        print(
            f"[{number}] {result['path']}"
        )
        print(
            "    classification :",
            result["classification"],
        )
        print(
            "    inventaire     :",
            result["inventory_state"],
        )

        for match in result["matches"]:
            excerpt = match["excerpt"].replace("\n", "\n        ")

            print(
                f"    ligne {match['line']} "
                f"(extrait {match['excerpt_start']}"
                f"–{match['excerpt_end']})"
            )
            print("        " + excerpt)

    if errors:
        print()
        print("Erreurs de lecture :", len(errors))

        for error in errors:
            print(
                f"  - {error['path']}: {error['error']}"
            )

    return 0


def detect_changes(args: argparse.Namespace) -> int:
    inventory = load_inventory()
    changed = []
    unchanged = 0
    errors = []

    for document in inventory["documents"]:
        path = document["path"]

        try:
            content = read_note(path)
        except RuntimeError as exc:
            errors.append({
                "path": path,
                "error": str(exc),
            })
            continue

        current_sha = hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()

        if current_sha == document.get("sha256"):
            unchanged += 1
            continue

        changed.append({
            "path": path,
            "inventory_sha256": document.get("sha256"),
            "current_sha256": current_sha,
        })

    report = {
        "schema": "eliot-jr.obsidian-change-report.v1",
        "vault": inventory.get("vault"),
        "unchanged": unchanged,
        "changed_count": len(changed),
        "changed": changed,
        "errors": errors,
        "llm_used": False,
    }

    print(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Interrogation documentaire en lecture seule "
            "du coffre Obsidian plan_mondial"
        )
    )

    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    search = commands.add_parser(
        "search",
        help="Chercher des termes dans les notes",
    )

    search.add_argument(
        "terms",
        nargs="+",
        help="Termes recherchés",
    )

    search.add_argument(
        "--any",
        action="store_true",
        help="Accepter un seul des termes au lieu de tous",
    )

    search.add_argument(
        "--classification",
        help="Limiter à une classification de l’inventaire",
    )

    search.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Nombre maximal de documents retournés",
    )

    search.add_argument(
        "--context",
        type=int,
        default=1,
        help="Nombre de lignes de contexte autour du résultat",
    )

    search.add_argument(
        "--json",
        action="store_true",
        help="Retourner du JSON structuré",
    )

    search.set_defaults(handler=search_documents)

    changes = commands.add_parser(
        "changes",
        help="Comparer le coffre vivant à l’inventaire",
    )

    changes.set_defaults(handler=detect_changes)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        return args.handler(args)
    except RuntimeError as exc:
        print(f"ERREUR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
