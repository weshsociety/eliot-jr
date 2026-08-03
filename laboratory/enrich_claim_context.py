#!/usr/bin/env python3

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

INPUT = (
    ROOT
    / "investigations/epstein_trou_de_souris"
    / "extractions/pilot_claim_candidates.json"
)

OUTPUT = (
    ROOT
    / "investigations/epstein_trou_de_souris"
    / "extractions/pilot_claim_candidates_context_v1.json"
)


def normalize(text: str) -> str:
    text = text.casefold().replace("’", "'")
    text = unicodedata.normalize("NFKD", text)

    return "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )


SECTION_RULES = {
    "source_section": (
        r"\bsources?\b",
        r"\breferences?\b",
        r"\bbibliograph",
        r"\barchives?\b",
        r"\bdocuments?\b",
    ),
    "chronology_section": (
        r"\bchronolog",
        r"\btimeline\b",
        r"\bdates?\b",
    ),
    "relationship_section": (
        r"\bliens?\b",
        r"\brelations?\b",
        r"\bconnexions?\b",
        r"\breseau\b",
    ),
    "research_section": (
        r"\ba creuser\b",
        r"\bpistes?\b",
        r"\bquestions?\b",
        r"\brecherches?\b",
        r"\ba verifier\b",
        r"\bprochaines? etapes?\b",
    ),
    "hypothesis_section": (
        r"\bhypothese",
        r"\bscenario",
        r"\bpossibilite",
    ),
    "method_section": (
        r"\bmethode\b",
        r"\bmethodologie\b",
        r"\btaxonomie\b",
        r"\bprotocole\b",
    ),
    "interpretive_section": (
        r"\bthese\b",
        r"\bsynthese\b",
        r"\bconclusion\b",
        r"\bpattern",
        r"\barchitecture\b",
        r"\bconsequence",
        r"\binterpretation\b",
    ),
    "biographical_section": (
        r"\bbiographie\b",
        r"\bparcours\b",
        r"\bprofil\b",
        r"\bidentite\b",
    ),
}


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Fichier introuvable : {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"JSON invalide dans {path}: {exc}") from exc


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
        raise RuntimeError(f"{path}: {message}")

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Réponse Obsidian invalide pour {path}: {exc}"
        ) from exc

    return payload.get("content", "")


def section_role_hints(section_path: list[str]) -> list[str]:
    normalized_path = normalize(" / ".join(section_path))
    hints = []

    for role, patterns in SECTION_RULES.items():
        if any(
            re.search(pattern, normalized_path)
            for pattern in patterns
        ):
            hints.append(role)

    return hints or ["unclassified_section"]


def surface_form(line: str) -> str:
    stripped = line.strip()

    if stripped.startswith("|"):
        return "table_row"

    if stripped.startswith(">"):
        return "blockquote"

    if re.match(r"^[-*+]\s+", stripped):
        return "bullet"

    if re.match(r"^\d+[.)]\s+", stripped):
        return "numbered_item"

    return "paragraph"


def extract_lead_label(line: str) -> str | None:
    match = re.match(
        r"^\s*(?:[-*+]|\d+[.)])?\s*"
        r"\*\*(.+?)\*\*\s*:?\s*",
        line,
    )

    if not match:
        return None

    return match.group(1).strip()


def extract_wikilinks(line: str) -> list[str]:
    return [
        match.strip()
        for match in re.findall(r"\[\[([^\]]+)\]\]", line)
        if match.strip()
    ]


def determine_source_state(
    extracted_sha256: str,
    current_sha256: str,
) -> str:
    """Compare the source seen at extraction with the current source."""
    if extracted_sha256 == current_sha256:
        return "unchanged"

    return "changed_since_candidate_extraction"


def build_line_contexts(content: str) -> dict[int, dict]:
    contexts = {}
    headings: list[tuple[int, str]] = []
    in_frontmatter = False

    for line_number, line in enumerate(
        content.splitlines(),
        start=1,
    ):
        stripped = line.strip()

        if stripped == "---":
            in_frontmatter = not in_frontmatter

            contexts[line_number] = {
                "section_path": [],
                "section_depth": 0,
                "section_role_hints": ["frontmatter"],
                "surface_form": "frontmatter_boundary",
                "lead_label": None,
                "wikilinks": [],
            }
            continue

        if in_frontmatter:
            contexts[line_number] = {
                "section_path": [],
                "section_depth": 0,
                "section_role_hints": ["frontmatter"],
                "surface_form": "frontmatter",
                "lead_label": None,
                "wikilinks": [],
            }
            continue

        heading_match = re.match(
            r"^(#{1,6})\s+(.+?)\s*$",
            line,
        )

        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()

            headings = [
                item
                for item in headings
                if item[0] < level
            ]
            headings.append((level, title))

        section_path = [
            title
            for _, title in headings
        ]

        contexts[line_number] = {
            "section_path": section_path,
            "section_depth": len(section_path),
            "section_role_hints": section_role_hints(
                section_path
            ),
            "surface_form": (
                "heading"
                if heading_match
                else surface_form(line)
            ),
            "lead_label": extract_lead_label(line),
            "wikilinks": extract_wikilinks(line),
        }

    return contexts


def main() -> int:
    source_report = load_json(INPUT)
    candidates = source_report.get("candidates", [])

    if not isinstance(candidates, list):
        raise RuntimeError("Champ candidates invalide")

    source_paths = sorted({
        candidate["source_path"]
        for candidate in candidates
    })

    documents = {}
    errors = []

    for source_path in source_paths:
        try:
            content = read_note(source_path)
        except RuntimeError as exc:
            errors.append({
                "source_path": source_path,
                "error": str(exc),
            })
            continue

        current_sha = hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()

        documents[source_path] = {
            "content": content,
            "current_sha256": current_sha,
            "line_contexts": build_line_contexts(content),
        }

    enriched_candidates = []
    blocked_candidates = []

    for candidate in candidates:
        source_path = candidate["source_path"]
        document = documents.get(source_path)

        if document is None:
            continue

        source_state = determine_source_state(
            candidate["source_sha256"],
            document["current_sha256"],
        )

        if source_state != "unchanged":
            blocked_candidates.append({
                "candidate_id": candidate.get("candidate_id"),
                "source_path": source_path,
                "source_state": source_state,
                "extracted_source_sha256": candidate[
                    "source_sha256"
                ],
                "current_source_sha256": document[
                    "current_sha256"
                ],
                "reason": (
                    "source_changed_before_context_enrichment"
                ),
            })
            continue

        line_number = candidate["line_start"]
        context = document["line_contexts"].get(
            line_number,
            {
                "section_path": [],
                "section_depth": 0,
                "section_role_hints": [
                    "line_context_missing"
                ],
                "surface_form": "unknown",
                "lead_label": None,
                "wikilinks": [],
            },
        )

        enriched = dict(candidate)

        enriched["source_current_sha256"] = (
            document["current_sha256"]
        )
        enriched["source_state"] = source_state
        enriched["section_context"] = context
        enriched["context_method"] = (
            "deterministic_markdown_structure_v1"
        )

        enriched_candidates.append(enriched)

    section_counts = Counter(
        hint
        for candidate in enriched_candidates
        for hint in candidate["section_context"][
            "section_role_hints"
        ]
    )

    form_counts = Counter(
        candidate["section_context"]["surface_form"]
        for candidate in enriched_candidates
    )

    changed_sources = sorted({
        candidate["source_path"]
        for candidate in blocked_candidates
    })

    report = {
        "schema": "eliot-jr.claim-context.v1",
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "input_schema": source_report.get("schema"),
        "input_sha256": hashlib.sha256(
            INPUT.read_bytes()
        ).hexdigest(),
        "context_method": (
            "deterministic_markdown_structure_v1"
        ),
        "llm_used": False,
        "core_modified": False,
        "relations_created": 0,
        "input_candidate_count": len(candidates),
        "candidate_count": len(enriched_candidates),
        "blocked_candidate_count": len(blocked_candidates),
        "blocked_candidates": blocked_candidates,
        "section_role_counts": dict(
            sorted(section_counts.items())
        ),
        "surface_form_counts": dict(
            sorted(form_counts.items())
        ),
        "changed_sources": changed_sources,
        "candidates": enriched_candidates,
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
        "status": (
            "context_enrichment_blocked"
            if changed_sources or errors
            else "context_enrichment_created"
        ),
        "input_candidate_count": len(candidates),
        "candidate_count": len(enriched_candidates),
        "blocked_candidate_count": len(blocked_candidates),
        "section_role_counts": report[
            "section_role_counts"
        ],
        "surface_form_counts": report[
            "surface_form_counts"
        ],
        "changed_sources": changed_sources,
        "errors": errors,
        "output": str(OUTPUT),
        "output_sha256": hashlib.sha256(
            OUTPUT.read_bytes()
        ).hexdigest(),
        "llm_used": False,
        "core_modified": False,
        "relations_created": 0,
    }, ensure_ascii=False, indent=2))

    return 0 if not errors and not changed_sources else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERREUR: {exc}", file=sys.stderr)
        raise SystemExit(1)
