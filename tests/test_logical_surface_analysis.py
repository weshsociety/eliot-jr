from __future__ import annotations

from pathlib import Path
import hashlib
import json

from core.logical_reading_context import (
    build_logical_reading_context,
)
from core.logical_surface_analysis import (
    LogicalSurfaceAnalysisError,
    analyse_logical_surface,
)


ROOT = Path("/home/eliot-jr")

JOURNAL_ID = (
    "lecture_thoreau_desobeissance_civile"
)

SOURCE = (
    ROOT
    / "curriculum"
    / "sources"
    / "thoreau_desobeissance_civile_extrait_en.txt"
)

JOURNAL = (
    ROOT
    / "curriculum"
    / "journaux"
    / f"{JOURNAL_ID}.json"
)

CANDIDATES = (
    ROOT
    / ".memory"
    / "reading_candidates"
)


def digest(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def live_hashes() -> dict[str, str]:
    paths = [
        SOURCE,
        JOURNAL,
        *sorted(
            CANDIDATES.glob("*.json")
        ),
    ]

    return {
        str(path): digest(path)
        for path in paths
    }


before = live_hashes()
analyses = {}

for number in range(1, 5):
    passage_id = (
        f"passage_{number:04d}"
    )

    context = (
        build_logical_reading_context(
            project_root=ROOT,
            journal_id=JOURNAL_ID,
            passage_id=passage_id,
        )
    )

    first = analyse_logical_surface(
        context
    )
    second = analyse_logical_surface(
        context
    )

    assert first == second
    assert (
        first["analysis_sha256"]
        == second["analysis_sha256"]
    )
    assert first["llm_used"] is False
    assert (
        first["processing_mode"]
        == "deterministic_non_llm"
    )
    assert (
        first["claims"][
            "journal_modified"
        ]
        is False
    )
    assert (
        first["claims"][
            "learning_state_modified"
        ]
        is False
    )
    assert (
        first["source_limits"][
            "source_declares_partial_corpus"
        ]
        is True
    )
    assert (
        first["source_limits"][
            "whole_work_claimed"
        ]
        is False
    )

    analyses[passage_id] = first


def canonicals(
    passage_id: str,
    group: str,
) -> list[str]:
    return [
        marker["canonical"]
        for marker in analyses[
            passage_id
        ]["logical_markers"][group]
    ]


assert (
    canonicals(
        "passage_0001",
        "cause_or_explanation",
    )
    == []
)

assert (
    canonicals(
        "passage_0003",
        "cause_or_explanation",
    )
    == ["for"]
)

assert (
    canonicals(
        "passage_0002",
        "comparison_or_degree",
    ).count("at best")
    == 1
)

assert (
    "best"
    not in canonicals(
        "passage_0002",
        "comparison_or_degree",
    )
)

assert (
    canonicals(
        "passage_0003",
        "negation",
    )
    == ["has not"]
)

assert (
    canonicals(
        "passage_0004",
        "negation",
    )
    == [
        "does not",
        "does not",
        "does not",
        "had not",
    ]
)

assert (
    analyses["passage_0003"][
        "surface_units"
    ]["sentences"][0][
        "is_question"
    ]
    is True
)

assert (
    len(
        analyses["passage_0003"][
            "candidate_relations"
        ]
    )
    >= 1
)

for analysis in analyses.values():
    serialised = json.dumps(
        analysis,
        ensure_ascii=False,
        sort_keys=True,
    )

    assert "external_reading_note" not in (
        serialised
    )
    assert "collective_review" not in (
        serialised
    )
    assert "provisional_understanding" not in (
        serialised
    )


bad_context = (
    build_logical_reading_context(
        project_root=ROOT,
        journal_id=JOURNAL_ID,
        passage_id="passage_0001",
    )
)

bad_context[
    "external_reading_note"
] = {
    "poison": "MUST_NOT_BE_ACCEPTED"
}

try:
    analyse_logical_surface(
        bad_context
    )
except LogicalSurfaceAnalysisError as error:
    forbidden_error = str(error)
else:
    raise AssertionError(
        "Un contexte interdit a été accepté."
    )


after = live_hashes()

assert before == after

print(
    "===== ANALYSE LOGIQUE DE SURFACE ====="
)
print(
    "Analyses déterministes :",
    len(analyses),
)
print(
    "Passage 0001 faux positif 'for' :",
    canonicals(
        "passage_0001",
        "cause_or_explanation",
    ),
)
print(
    "Passage 0002 comparaison :",
    canonicals(
        "passage_0002",
        "comparison_or_degree",
    ),
)
print(
    "Passage 0003 négation :",
    canonicals(
        "passage_0003",
        "negation",
    ),
)
print(
    "Passage 0004 négations :",
    canonicals(
        "passage_0004",
        "negation",
    ),
)
print(
    "Contexte interdit refusé :",
    forbidden_error,
)
print(
    "États vivants inchangés :",
    before == after,
)
print("Appel LLM : non")
print("Journal écrit : non")
print("Apprentissage produit : non")
