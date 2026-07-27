from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any


class OpenQuestionExtractionError(ValueError):
    """Extraction stricte des questions ouvertes impossible."""


STRICT_NO_HIT_PATTERNS = (
    re.compile(
        r"\bje\s+garde\s+donc\s+la\s+question\s+ouverte\b",
        re.IGNORECASE,
    ),
    re.compile(
        (
            r"\bje\s+ne\s+trouve\s+pas\b.*"
            r"\bsans\s+fabriquer\b"
        ),
        re.IGNORECASE | re.DOTALL,
    ),
)

QUESTION_KEYS = (
    "input",
    "question",
    "query",
    "prompt",
    "message",
    "initial_question",
)

RESPONSE_KEYS = (
    "response_verbatim",
    "response",
    "answer",
    "output",
)


def _normalise(value: Any) -> str:
    decomposed = unicodedata.normalize(
        "NFKD",
        str(value),
    )

    without_accents = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )

    return re.sub(
        r"\s+",
        " ",
        without_accents.lower(),
    ).strip()


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def _text_hash(value: str) -> str:
    return hashlib.sha256(
        _normalise(value).encode("utf-8")
    ).hexdigest()


def _is_strict_no_hit(value: Any) -> bool:
    if not isinstance(value, str):
        return False

    return any(
        pattern.search(value)
        for pattern in STRICT_NO_HIT_PATTERNS
    )


def _question_from_mapping(
    value: dict[str, Any],
) -> str | None:
    for key in QUESTION_KEYS:
        candidate = value.get(key)

        if (
            isinstance(candidate, str)
            and candidate.strip()
        ):
            return candidate.strip()

    return None


def _interaction_number(
    value: dict[str, Any],
) -> int | None:
    direct = value.get("interaction_number")

    if isinstance(direct, int):
        return direct

    temporal = value.get("temporal_context")

    if isinstance(temporal, dict):
        interaction = temporal.get(
            "interaction_number"
        )

        if isinstance(interaction, int):
            return interaction

    return None


def _timestamp(
    value: dict[str, Any],
) -> str | None:
    for key in (
        "timestamp",
        "created_at_utc",
        "reviewed_at_utc",
        "observed_at_utc",
    ):
        candidate = value.get(key)

        if (
            isinstance(candidate, str)
            and candidate.strip()
        ):
            return candidate.strip()

    return None


def _evidence(
    *,
    source: str,
    source_type: str,
    record_number: int | None,
    field_path: str,
    response: str,
    interaction_number: int | None,
    timestamp: str | None,
) -> dict[str, Any]:
    return {
        "source": source,
        "source_type": source_type,
        "record_number": record_number,
        "field_path": field_path,
        "rule": "strict_no_hit",
        "response_sha256": _text_hash(response),
        "interaction_number": interaction_number,
        "timestamp": timestamp,
        "response_excerpt": re.sub(
            r"\s+",
            " ",
            response,
        ).strip()[:500],
    }


def _dialogue_candidates(
    project_root: Path,
) -> list[dict[str, Any]]:
    path = (
        project_root
        / ".memory"
        / "dialogue_journal.jsonl"
    )

    if not path.is_file():
        return []

    candidates: list[dict[str, Any]] = []

    try:
        lines = path.read_text(
            encoding="utf-8"
        ).splitlines()
    except OSError as error:
        raise OpenQuestionExtractionError(
            "Le journal de dialogue est illisible."
        ) from error

    for line_number, line in enumerate(
        lines,
        1,
    ):
        if not line.strip():
            continue

        try:
            entry = json.loads(line)
        except json.JSONDecodeError as error:
            raise OpenQuestionExtractionError(
                "JSON invalide dans le journal de dialogue "
                f"à la ligne {line_number}."
            ) from error

        if not isinstance(entry, dict):
            continue

        response = entry.get("response")
        question = entry.get("input")

        if not _is_strict_no_hit(response):
            continue

        if (
            not isinstance(question, str)
            or not question.strip()
        ):
            continue

        response_text = str(response).strip()
        question_text = question.strip()

        candidates.append({
            "question": question_text,
            "question_normalised": _normalise(
                question_text
            ),
            "question_sha256": _text_hash(
                question_text
            ),
            "response_sha256": _text_hash(
                response_text
            ),
            "first_interaction": (
                _interaction_number(entry)
            ),
            "first_observed_at_utc": (
                _timestamp(entry)
            ),
            "evidence": [
                _evidence(
                    source=str(
                        path.relative_to(
                            project_root
                        )
                    ),
                    source_type=(
                        "dialogue_origin"
                    ),
                    record_number=line_number,
                    field_path="$.response",
                    response=response_text,
                    interaction_number=(
                        _interaction_number(entry)
                    ),
                    timestamp=_timestamp(entry),
                )
            ],
        })

    return candidates


def _walk_for_strict_responses(
    value: Any,
    *,
    source: str,
    field_path: str = "$",
    inherited_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    if isinstance(value, dict):
        context = (
            value
            if field_path == "$"
            else inherited_context
        )

        local_question = _question_from_mapping(
            value
        )

        for key, child in value.items():
            child_path = (
                f"{field_path}.{key}"
            )

            if (
                str(key) in RESPONSE_KEYS
                and _is_strict_no_hit(child)
            ):
                response_text = str(child).strip()

                results.append({
                    "question": local_question,
                    "response_sha256": _text_hash(
                        response_text
                    ),
                    "evidence": _evidence(
                        source=source,
                        source_type=(
                            "documentary_copy"
                        ),
                        record_number=None,
                        field_path=child_path,
                        response=response_text,
                        interaction_number=(
                            _interaction_number(
                                value
                            )
                        ),
                        timestamp=_timestamp(value),
                    ),
                })

            results.extend(
                _walk_for_strict_responses(
                    child,
                    source=source,
                    field_path=child_path,
                    inherited_context=(
                        value
                        if isinstance(value, dict)
                        else context
                    ),
                )
            )

        return results

    if isinstance(value, list):
        for index, child in enumerate(value):
            results.extend(
                _walk_for_strict_responses(
                    child,
                    source=source,
                    field_path=(
                        f"{field_path}[{index}]"
                    ),
                    inherited_context=(
                        inherited_context
                    ),
                )
            )

    return results


def _curriculum_evidence(
    project_root: Path,
) -> list[dict[str, Any]]:
    journal_root = (
        project_root
        / "curriculum"
        / "journaux"
    )

    if not journal_root.is_dir():
        return []

    results: list[dict[str, Any]] = []

    for path in sorted(
        journal_root.glob("*.json")
    ):
        try:
            value = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            json.JSONDecodeError,
        ) as error:
            raise OpenQuestionExtractionError(
                f"Journal de lecture illisible : {path.name}"
            ) from error

        results.extend(
            _walk_for_strict_responses(
                value,
                source=str(
                    path.relative_to(
                        project_root
                    )
                ),
            )
        )

    return results


def _merge_candidates(
    dialogue: list[dict[str, Any]],
    documentary: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_question: dict[
        str,
        dict[str, Any],
    ] = {}

    by_response: dict[
        str,
        dict[str, Any],
    ] = {}

    for candidate in dialogue:
        question_sha = candidate[
            "question_sha256"
        ]

        current = by_question.get(
            question_sha
        )

        if current is None:
            current = {
                "question_id": (
                    "openq_"
                    + question_sha[:16]
                ),
                "question": candidate[
                    "question"
                ],
                "question_normalised": (
                    candidate[
                        "question_normalised"
                    ]
                ),
                "question_sha256": (
                    question_sha
                ),
                "status": "open",
                "origin": (
                    "strict_no_hit_response"
                ),
                "first_interaction": (
                    candidate[
                        "first_interaction"
                    ]
                ),
                "first_observed_at_utc": (
                    candidate[
                        "first_observed_at_utc"
                    ]
                ),
                "last_observed_at_utc": (
                    candidate[
                        "first_observed_at_utc"
                    ]
                ),
                "observation_count": 0,
                "evidence": [],
                "resolution": None,
                "revisable": True,
            }

            by_question[
                question_sha
            ] = current

        current["evidence"].extend(
            candidate["evidence"]
        )
        current[
            "observation_count"
        ] += len(candidate["evidence"])

        by_response[
            candidate["response_sha256"]
        ] = current

    unresolved_documentary = 0

    for candidate in documentary:
        current = by_response.get(
            candidate[
                "response_sha256"
            ]
        )

        if current is None:
            question = candidate.get(
                "question"
            )

            if (
                isinstance(question, str)
                and question.strip()
            ):
                question_sha = _text_hash(
                    question
                )
                current = by_question.get(
                    question_sha
                )

        if current is None:
            unresolved_documentary += 1
            continue

        evidence = candidate[
            "evidence"
        ]

        identity = (
            evidence["source"],
            evidence["record_number"],
            evidence["field_path"],
            evidence["response_sha256"],
        )

        existing = {
            (
                item["source"],
                item["record_number"],
                item["field_path"],
                item["response_sha256"],
            )
            for item in current["evidence"]
        }

        if identity not in existing:
            current["evidence"].append(
                evidence
            )
            current[
                "observation_count"
            ] += 1

            timestamp = evidence.get(
                "timestamp"
            )

            if isinstance(timestamp, str):
                current[
                    "last_observed_at_utc"
                ] = timestamp

    questions = sorted(
        by_question.values(),
        key=lambda question: (
            question.get(
                "first_interaction"
            )
            is None,
            question.get(
                "first_interaction"
            )
            or 0,
            question["question_id"],
        ),
    )

    for question in questions:
        question["evidence"].sort(
            key=lambda evidence: (
                evidence.get(
                    "timestamp"
                )
                is None,
                evidence.get(
                    "timestamp"
                )
                or "",
                evidence["source"],
                evidence.get(
                    "record_number"
                )
                or 0,
            )
        )

    return questions


def extract_open_questions(
    project_root: Path,
) -> dict[str, Any]:
    """
    Extrait uniquement les questions associées à une
    réponse explicite de non-savoir.

    La simple présence des mots « question ouverte »
    n’est jamais suffisante.
    """
    root = project_root.resolve()

    if not root.is_dir():
        raise OpenQuestionExtractionError(
            "La maison d’Eliot-Jr est introuvable."
        )

    dialogue = _dialogue_candidates(root)
    documentary = _curriculum_evidence(
        root
    )
    questions = _merge_candidates(
        dialogue,
        documentary,
    )

    report = {
        "schema_version": 1,
        "identity": "Eliot-Jr",
        "framework": "questience",
        "mode": "strict_extraction_dry_run",
        "source_policy": {
            "accepted_origins": [
                (
                    "journal de dialogue avec "
                    "question originale"
                ),
                (
                    "copie documentaire rattachée "
                    "par empreinte de réponse"
                ),
            ],
            "simple_phrase_match_accepted": False,
            "desire_registry_scanned": False,
            "initiative_registry_scanned": False,
            "will_registry_scanned": False,
            "strict_no_hit_required": True,
        },
        "dialogue_candidate_count": len(
            dialogue
        ),
        "documentary_evidence_count": len(
            documentary
        ),
        "open_question_count": len(
            questions
        ),
        "questions": questions,
        "persistent_inventory_created": False,
        "chronology_advanced": False,
        "will_state_modified": False,
        "external_action_performed": False,
        "report_sha256": None,
    }

    hashable = dict(report)
    hashable.pop(
        "report_sha256",
        None,
    )

    report["report_sha256"] = (
        _canonical_hash(hashable)
    )

    return report
