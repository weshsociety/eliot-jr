from __future__ import annotations

from copy import deepcopy
from typing import Any
import hashlib
import json
import re


ANALYSIS_SCHEMA_VERSION = 2

TOKEN_PATTERN = re.compile(
    r"[A-Za-z]+(?:[’'][A-Za-z]+)?"
)

SENTENCE_TERMINATORS = frozenset(
    ".?!"
)

CLAUSE_BOUNDARIES = frozenset(
    ";:?!—–"
)

FORBIDDEN_CONTEXT_KEYS = frozenset({
    "external_reading_note",
    "collective_review",
    "validated_result",
    "review",
    "review_history",
    "request",
    "engine_attribution",
    "authorship_status",
    "provisional_understanding",
    "what_passage_says",
})

MARKER_GROUPS: dict[
    str,
    tuple[str, ...],
] = {
    "negation": (
        "does not",
        "do not",
        "did not",
        "has not",
        "have not",
        "had not",
        "is not",
        "are not",
        "was not",
        "were not",
        "will not",
        "would not",
        "should not",
        "must not",
        "cannot",
        "can't",
        "not",
        "no",
        "never",
        "neither",
        "nor",
        "without",
    ),
    "modality_or_capacity": (
        "should",
        "will",
        "would",
        "can",
        "cannot",
        "could",
        "may",
        "might",
        "must",
        "ought",
    ),
    "condition_or_time": (
        "if",
        "when",
        "unless",
        "until",
        "while",
    ),
    "contrast_or_concession": (
        "although",
        "however",
        "unlike",
        "though",
        "but",
        "yet",
    ),
    "cause_or_explanation": (
        "therefore",
        "because",
        "since",
        "for",
    ),
    "comparison_or_degree": (
        "at best",
        "best",
        "better",
        "least",
        "more",
        "most",
        "less",
        "than",
    ),
    "quantification_or_frequency": (
        "all",
        "most",
        "some",
        "usually",
        "sometimes",
        "always",
        "never",
    ),
}

RELATION_GROUPS = frozenset({
    "condition_or_time",
    "contrast_or_concession",
    "cause_or_explanation",
})

REFERENCE_TOKENS = frozenset({
    "it",
    "this",
    "that",
    "which",
    "they",
    "them",
    "their",
    "those",
    "these",
})

STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at",
    "be", "been", "being", "but", "by",
    "do", "does", "did", "for", "from",
    "had", "has", "have", "he", "her",
    "him", "his", "i", "if", "in", "is",
    "it", "its", "me", "my", "no", "not",
    "of", "on", "or", "our", "she", "so",
    "that", "the", "their", "them", "there",
    "they", "this", "to", "was", "we",
    "were", "what", "when", "which", "who",
    "will", "with", "would", "you",
})


class LogicalSurfaceAnalysisError(
    ValueError
):
    """Erreur contrôlée d’analyse logique de surface."""


def _canonical_json_bytes(
    value: Any,
) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(
    payload: bytes,
) -> str:
    return hashlib.sha256(
        payload
    ).hexdigest()


def _assert_no_forbidden_keys(
    value: Any,
    *,
    location: str = "$",
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_CONTEXT_KEYS:
                raise LogicalSurfaceAnalysisError(
                    "Namespace interdit reçu par "
                    "l’analyseur logique : "
                    f"{location}.{key}"
                )

            _assert_no_forbidden_keys(
                child,
                location=f"{location}.{key}",
            )

    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_forbidden_keys(
                child,
                location=(
                    f"{location}[{index}]"
                ),
            )


def _validate_context(
    context: dict[str, Any],
) -> tuple[
    dict[str, Any],
    str,
]:
    if not isinstance(context, dict):
        raise LogicalSurfaceAnalysisError(
            "Le contexte doit être un objet."
        )

    _assert_no_forbidden_keys(
        context
    )

    if (
        context.get("context_kind")
        != (
            "deterministic_logical_"
            "reading_context"
        )
    ):
        raise LogicalSurfaceAnalysisError(
            "Type de contexte logique invalide."
        )

    if context.get("llm_used") is not False:
        raise LogicalSurfaceAnalysisError(
            "Le contexte doit déclarer "
            "llm_used=false."
        )

    passage = context.get("passage")

    if not isinstance(passage, dict):
        raise LogicalSurfaceAnalysisError(
            "Passage absent du contexte."
        )

    text = passage.get("text")

    if not isinstance(text, str):
        raise LogicalSurfaceAnalysisError(
            "Texte du passage invalide."
        )

    if not text.strip():
        raise LogicalSurfaceAnalysisError(
            "Texte du passage vide."
        )

    return passage, text


def _trim_span(
    text: str,
    start: int,
    end: int,
) -> tuple[int, int]:
    while (
        start < end
        and text[start].isspace()
    ):
        start += 1

    while (
        end > start
        and text[end - 1].isspace()
    ):
        end -= 1

    while (
        start < end
        and text[start]
        in "«»“”\"'"
    ):
        start += 1

    while (
        end > start
        and text[end - 1]
        in "«»“”\"'"
    ):
        end -= 1

    return start, end


def _sentence_units(
    text: str,
) -> list[dict[str, Any]]:
    units = []
    start = 0

    for index, character in enumerate(
        text
    ):
        if character not in (
            SENTENCE_TERMINATORS
        ):
            continue

        end = index + 1
        trimmed_start, trimmed_end = (
            _trim_span(
                text,
                start,
                end,
            )
        )

        if trimmed_start < trimmed_end:
            units.append({
                "unit_number": (
                    len(units) + 1
                ),
                "start": trimmed_start,
                "end": trimmed_end,
                "text": text[
                    trimmed_start:
                    trimmed_end
                ],
                "terminator": character,
                "is_question": (
                    character == "?"
                ),
            })

        start = end

    trimmed_start, trimmed_end = (
        _trim_span(
            text,
            start,
            len(text),
        )
    )

    if trimmed_start < trimmed_end:
        units.append({
            "unit_number": (
                len(units) + 1
            ),
            "start": trimmed_start,
            "end": trimmed_end,
            "text": text[
                trimmed_start:
                trimmed_end
            ],
            "terminator": None,
            "is_question": False,
        })

    return units


def _clause_units(
    text: str,
) -> list[dict[str, Any]]:
    units = []
    start = 0

    for index, character in enumerate(
        text
    ):
        if character not in CLAUSE_BOUNDARIES:
            continue

        end = index + 1
        trimmed_start, trimmed_end = (
            _trim_span(
                text,
                start,
                end,
            )
        )

        if trimmed_start < trimmed_end:
            units.append({
                "unit_number": (
                    len(units) + 1
                ),
                "start": trimmed_start,
                "end": trimmed_end,
                "text": text[
                    trimmed_start:
                    trimmed_end
                ],
                "boundary": character,
            })

        start = end

    trimmed_start, trimmed_end = (
        _trim_span(
            text,
            start,
            len(text),
        )
    )

    if trimmed_start < trimmed_end:
        units.append({
            "unit_number": (
                len(units) + 1
            ),
            "start": trimmed_start,
            "end": trimmed_end,
            "text": text[
                trimmed_start:
                trimmed_end
            ],
            "boundary": None,
        })

    return units


def _word_pattern(
    marker: str,
) -> re.Pattern[str]:
    return re.compile(
        r"(?<![A-Za-z])"
        + re.escape(marker)
        + r"(?![A-Za-z])",
        flags=re.IGNORECASE,
    )


def _for_is_conjunction(
    text: str,
    start: int,
) -> bool:
    prefix = text[:start].rstrip()

    if not prefix:
        return True

    return prefix[-1] in (
        ";:,.!?—–"
    )


def _raw_marker_matches(
    text: str,
) -> list[dict[str, Any]]:
    matches = []

    for group, vocabulary in (
        MARKER_GROUPS.items()
    ):
        for canonical in vocabulary:
            for match in _word_pattern(
                canonical
            ).finditer(text):
                if (
                    group
                    == "cause_or_explanation"
                    and canonical == "for"
                    and not _for_is_conjunction(
                        text,
                        match.start(),
                    )
                ):
                    continue

                matches.append({
                    "group": group,
                    "canonical": canonical,
                    "matched_text": (
                        match.group(0)
                    ),
                    "start": match.start(),
                    "end": match.end(),
                })

    return matches


def _deduplicate_marker_matches(
    matches: list[
        dict[str, Any]
    ],
) -> list[dict[str, Any]]:
    ordered = sorted(
        matches,
        key=lambda item: (
            item["start"],
            -(
                item["end"]
                - item["start"]
            ),
            item["group"],
            item["canonical"],
        ),
    )

    selected = []

    for candidate in ordered:
        overlapping = [
            existing
            for existing in selected
            if not (
                candidate["end"]
                <= existing["start"]
                or candidate["start"]
                >= existing["end"]
            )
        ]

        if not overlapping:
            selected.append(
                candidate
            )
            continue

        same_span = [
            existing
            for existing in overlapping
            if (
                existing["start"]
                == candidate["start"]
                and existing["end"]
                == candidate["end"]
            )
        ]

        if same_span:
            selected.append(
                candidate
            )

    selected.sort(
        key=lambda item: (
            item["start"],
            item["end"],
            item["group"],
            item["canonical"],
        )
    )

    return selected


def _markers(
    text: str,
) -> list[dict[str, Any]]:
    selected = (
        _deduplicate_marker_matches(
            _raw_marker_matches(text)
        )
    )

    return [
        {
            "marker_id": (
                f"marker_{index:04d}"
            ),
            **match,
        }
        for index, match in enumerate(
            selected,
            1,
        )
    ]


def _nearest_boundary_left(
    text: str,
    start: int,
) -> int:
    index = start - 1

    while index >= 0:
        if text[index] in (
            CLAUSE_BOUNDARIES
            | frozenset(".")
        ):
            return index + 1

        index -= 1

    return 0


def _nearest_boundary_right(
    text: str,
    end: int,
) -> int:
    index = end

    while index < len(text):
        if text[index] in (
            CLAUSE_BOUNDARIES
            | frozenset(".")
        ):
            return index + 1

        index += 1

    return len(text)


CONNECTOR_ONLY_TOKENS = frozenset({
    "and", "but", "for", "or", "so", "yet",
})


def _is_substantive_evidence(value: str) -> bool:
    tokens = [m.group(0).casefold() for m in TOKEN_PATTERN.finditer(value)]
    return len(tokens) >= 2 and not all(token in CONNECTOR_ONLY_TOKENS for token in tokens)


def _previous_clause_span(text: str, boundary_start: int) -> tuple[int, int]:
    index = boundary_start - 1
    while index >= 0 and (text[index].isspace() or text[index] in "«»“”\"';:,.?!—–"):
        index -= 1
    end = index + 1
    while index >= 0:
        if text[index] in (CLAUSE_BOUNDARIES | frozenset(".")):
            break
        index -= 1
    return _trim_span(text, index + 1, end)


def _relation_marker_allowed(text: str, marker: dict[str, Any]) -> bool:
    if marker["group"] != "contrast_or_concession" or marker["canonical"] != "but":
        return True
    prefix = text[max(0, marker["start"] - 80):marker["start"]].casefold()
    if re.search(r"\bat\s+best\s*$", prefix):
        return False
    clause_start = _nearest_boundary_left(text, marker["start"])
    clause_prefix = text[clause_start:marker["start"]].casefold()
    if re.search(r"\bwhat\s+is(?:\s+it)?\s*$", clause_prefix):
        return False
    return True


def _relation_candidates(
    text: str,
    markers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    relations = []
    for marker in markers:
        if marker["group"] not in RELATION_GROUPS:
            continue
        if not _relation_marker_allowed(text, marker):
            continue
        left_start = _nearest_boundary_left(text, marker["start"])
        left_end = marker["start"]
        right_start = marker["end"]
        right_end = _nearest_boundary_right(text, marker["end"])
        left_start, left_end = _trim_span(text, left_start, left_end)
        right_start, right_end = _trim_span(text, right_start, right_end)
        left_text = text[left_start:left_end]
        right_text = text[right_start:right_end]
        if not _is_substantive_evidence(left_text):
            previous_start, previous_end = _previous_clause_span(text, left_start)
            previous_text = text[previous_start:previous_end]
            if _is_substantive_evidence(previous_text):
                left_start, left_end, left_text = previous_start, previous_end, previous_text
        if not (_is_substantive_evidence(left_text) and _is_substantive_evidence(right_text)):
            continue
        relations.append({
            "relation_id": f"relation_{len(relations)+1:04d}",
            "relation_type": marker["group"],
            "status": "candidate_not_interpreted",
            "basis": "surface_marker_and_substantive_adjacent_spans",
            "marker": deepcopy(marker),
            "left_evidence": {"start": left_start, "end": left_end, "text": left_text},
            "right_evidence": {"start": right_start, "end": right_end, "text": right_text},
        })
    return relations


def _negation_candidates(
    text: str,
    markers: list[
        dict[str, Any]
    ],
) -> list[dict[str, Any]]:
    results = []

    for marker in markers:
        if marker["group"] != "negation":
            continue

        scope_start = marker["start"]
        scope_end = (
            _nearest_boundary_right(
                text,
                marker["end"],
            )
        )

        scope_start, scope_end = (
            _trim_span(
                text,
                scope_start,
                scope_end,
            )
        )

        results.append({
            "negation_id": (
                f"negation_"
                f"{len(results) + 1:04d}"
            ),
            "status": (
                "candidate_scope_not_"
                "syntactically_resolved"
            ),
            "marker": deepcopy(
                marker
            ),
            "candidate_scope": {
                "start": scope_start,
                "end": scope_end,
                "text": text[
                    scope_start:
                    scope_end
                ],
            },
        })

    return results


def _token_occurrences(
    text: str,
) -> list[dict[str, Any]]:
    occurrences = []

    for index, match in enumerate(
        TOKEN_PATTERN.finditer(text),
        1,
    ):
        occurrences.append({
            "token_id": (
                f"token_{index:04d}"
            ),
            "text": match.group(0),
            "normalised": (
                match.group(0).casefold()
            ),
            "start": match.start(),
            "end": match.end(),
        })

    return occurrences


def _recurring_terms(
    occurrences: list[
        dict[str, Any]
    ],
) -> list[dict[str, Any]]:
    grouped: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    for occurrence in occurrences:
        term = occurrence[
            "normalised"
        ]

        if term in STOPWORDS:
            continue

        grouped.setdefault(
            term,
            [],
        ).append(occurrence)

    recurring = []

    for term, items in sorted(
        grouped.items()
    ):
        if len(items) < 2:
            continue

        recurring.append({
            "term": term,
            "count": len(items),
            "occurrences": [
                {
                    "start": item["start"],
                    "end": item["end"],
                    "text": item["text"],
                }
                for item in items
            ],
        })

    recurring.sort(
        key=lambda item: (
            -item["count"],
            item["term"],
        )
    )

    return recurring


def _reference_form_occurrences(
    occurrences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    results = []
    for occurrence in occurrences:
        if occurrence["normalised"] not in REFERENCE_TOKENS:
            continue
        results.append({
            "reference_id": f"reference_{len(results)+1:04d}",
            "kind": "reference_form_occurrence",
            "status": "observed_not_resolved",
            "ambiguity_claimed": False,
            "evidence": {
                "start": occurrence["start"],
                "end": occurrence["end"],
                "text": occurrence["text"],
                "normalised": occurrence["normalised"],
            },
        })
    return results


def analyse_logical_surface(
    context: dict[str, Any],
) -> dict[str, Any]:
    """
    Produit une analyse de surface déterministe.

    Cette fonction ne lit aucun fichier, n’appelle aucun modèle
    et ne modifie aucun état. Elle opère uniquement sur le sas
    logique déjà construit.
    """
    passage, text = _validate_context(
        context
    )

    tokens = _token_occurrences(
        text
    )
    markers = _markers(
        text
    )
    sentences = _sentence_units(
        text
    )
    clauses = _clause_units(
        text
    )

    grouped_markers = {
        group: [
            deepcopy(marker)
            for marker in markers
            if marker["group"] == group
        ]
        for group in MARKER_GROUPS
    }

    analysis: dict[str, Any] = {
        "schema_version": (
            ANALYSIS_SCHEMA_VERSION
        ),
        "analysis_kind": (
            "deterministic_logical_"
            "surface_analysis"
        ),
        "producer": (
            "eliot_jr_logical_surface_"
            "analyser"
        ),
        "processing_mode": (
            "deterministic_non_llm"
        ),
        "llm_used": False,
        "context_id": context.get(
            "context_id"
        ),
        "context_sha256": context.get(
            "context_sha256"
        ),
        "passage_identity": {
            "passage_id": passage.get(
                "passage_id"
            ),
            "order": passage.get("order"),
            "passage_sha256": passage.get(
                "passage_sha256"
            ),
        },
        "source_limits": {
            "source_declares_partial_corpus": (
                context.get(
                    "source",
                    {},
                ).get(
                    "source_declares_partial_corpus"
                )
            ),
            "whole_work_claimed": False,
        },
        "surface_units": {
            "sentences": sentences,
            "clauses": clauses,
        },
        "logical_markers": (
            grouped_markers
        ),
        "term_occurrences": {
            "tokens": tokens,
            "recurring_content_terms": (
                _recurring_terms(
                    tokens
                )
            ),
        },
        "candidate_relations": (
            _relation_candidates(
                text,
                markers,
            )
        ),
        "candidate_negation_scopes": (
            _negation_candidates(
                text,
                markers,
            )
        ),
        "reference_form_occurrences": (
            _reference_form_occurrences(tokens)
        ),
        "potential_ambiguities": [],
        "evidence_policy": {
            "all_evidence_uses_character_spans": (
                True
            ),
            "relations_are_interpreted": False,
            "negation_scopes_are_final": False,
            "references_are_resolved": False,
            "reference_forms_are_ambiguities": False,
            "ambiguity_requires_multiple_plausible_referents": True,
        },
        "claims": {
            "journal_modified": False,
            "learning_state_modified": False,
            "external_action_performed": False,
            "human_approval_required_to_exist": (
                False
            ),
        },
    }

    _assert_no_forbidden_keys(
        analysis
    )

    analysis_hash = _sha256_bytes(
        _canonical_json_bytes(
            analysis
        )
    )

    analysis["analysis_sha256"] = (
        analysis_hash
    )
    analysis["analysis_id"] = (
        f"{passage.get('passage_id')}:"
        f"{analysis_hash[:16]}"
    )

    _assert_no_forbidden_keys(
        analysis
    )

    return analysis
