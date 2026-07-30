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

for number in range(1, 7):
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
    canonicals(
        "passage_0005",
        "negation",
    )
    == [
        "not",
        "no",
    ]
)

passage_0005_negations = analyses[
    "passage_0005"
]["candidate_negation_scopes"]

assert len(
    passage_0005_negations
) == 2

assert [
    item["marker"]["canonical"]
    for item in passage_0005_negations
] == [
    "not",
    "no",
]

assert [
    item[
        "candidate_scope"
    ]["text"]
    for item in passage_0005_negations
] == [
    (
        "not at once no government, "
        "but at once a better government."
    ),
    "no government",
]

assert (
    passage_0005_negations[0][
        "scope_relation"
    ]
    == "top_level_candidate"
)

assert (
    passage_0005_negations[1][
        "scope_relation"
    ]
    == "nested_candidate"
)

assert (
    passage_0005_negations[1][
        "nested_within_negation_ids"
    ]
    == ["negation_0001"]
)

assert all(
    not item[
        "candidate_scope"
    ]["text"].startswith(
        "no-government"
    )
    for item in passage_0005_negations
)


assert (
    canonicals(
        "passage_0006",
        "negation",
    )
    == [
        "not",
        "do not",
    ]
)

passage_0006_negations = analyses[
    "passage_0006"
]["candidate_negation_scopes"]

assert len(
    passage_0006_negations
) == 2

assert [
    item[
        "candidate_scope"
    ]["text"]
    for item in passage_0006_negations
] == [
    (
        "not be a government in which "
        "majorities do not virtually "
        "decide right and wrong, but "
        "conscience?"
    ),
    (
        "do not virtually decide right "
        "and wrong, but conscience?"
    ),
]

assert (
    passage_0006_negations[0][
        "scope_relation"
    ]
    == "top_level_candidate"
)

assert (
    passage_0006_negations[1][
        "scope_relation"
    ]
    == "nested_candidate"
)

assert (
    passage_0006_negations[1][
        "nested_within_negation_ids"
    ]
    == ["negation_0001"]
)

assert sum(
    sentence["is_question"]
    for sentence in analyses[
        "passage_0006"
    ][
        "surface_units"
    ]["sentences"]
) == 4

assert (
    analyses["passage_0003"][
        "surface_units"
    ]["sentences"][0][
        "is_question"
    ]
    is True
)

expected_relation_counts = {
    "passage_0001": 1,
    "passage_0002": 1,
    "passage_0003": 3,
    "passage_0004": 1,
    "passage_0005": 2,
    "passage_0006": 0,
}

expected_reference_counts = {
    "passage_0001": 12,
    "passage_0002": 0,
    "passage_0003": 4,
    "passage_0004": 5,
    "passage_0005": 3,
    "passage_0006": 4,
}

for passage_id, expected in expected_relation_counts.items():
    relations = analyses[passage_id]["candidate_relations"]
    assert len(relations) == expected
    for relation in relations:
        assert relation["left_evidence"]["text"].strip()
        assert relation["right_evidence"]["text"].strip()

for passage_id, expected in expected_reference_counts.items():
    analysis = analyses[passage_id]
    assert len(analysis["reference_form_occurrences"]) == expected
    assert analysis["potential_ambiguities"] == []

passage_0002_buts = [
    relation["marker"]["start"]
    for relation in analyses["passage_0002"]["candidate_relations"]
    if relation["marker"]["canonical"] == "but"
]
assert passage_0002_buts == [42]

passage_0003_buts = [
    relation["marker"]["start"]
    for relation in analyses["passage_0003"]["candidate_relations"]
    if relation["marker"]["canonical"] == "but"
]
assert passage_0003_buts == [132]

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
    "Passage 0005 marqueurs de négation :",
    canonicals(
        "passage_0005",
        "negation",
    ),
)
print(
    "Passage 0005 portées candidates :",
    [
        item[
            "candidate_scope"
        ]["text"]
        for item in analyses[
            "passage_0005"
        ][
            "candidate_negation_scopes"
        ]
    ],
)
print(
    "Passage 0006 marqueurs de négation :",
    canonicals(
        "passage_0006",
        "negation",
    ),
)
print(
    "Passage 0006 portées candidates :",
    [
        item[
            "candidate_scope"
        ]["text"]
        for item in analyses[
            "passage_0006"
        ][
            "candidate_negation_scopes"
        ]
    ],
)
print(
    "Relations par passage :",
    {
        passage_id: len(analysis["candidate_relations"])
        for passage_id, analysis in analyses.items()
    },
)
print(
    "Références observées :",
    {
        passage_id: len(analysis["reference_form_occurrences"])
        for passage_id, analysis in analyses.items()
    },
)
print(
    "Ambiguïtés produites :",
    {
        passage_id: len(analysis["potential_ambiguities"])
        for passage_id, analysis in analyses.items()
    },
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
