from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
import fcntl
import hashlib
import json
import os
import re
import tempfile

from gardien.backup_reading_state import (
    create_backup,
)


JOURNAL_ID_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9_]*$"
)

LEARNING_SCHEMA_VERSION = 1

PRODUCER = "eliot_jr_logical_core"

FORBIDDEN_INPUT_KEYS = frozenset({
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


class LogicalLearningRegistryError(
    ValueError
):
    """Erreur contrôlée du registre d’apprentissage logique."""


def _utc_now(
    now: datetime | None = None,
) -> str:
    moment = now or datetime.now(
        timezone.utc
    )

    if moment.tzinfo is None:
        moment = moment.replace(
            tzinfo=timezone.utc
        )

    return moment.astimezone(
        timezone.utc
    ).isoformat()


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
    value: bytes,
) -> str:
    return hashlib.sha256(
        value
    ).hexdigest()


def _canonical_hash(
    value: Any,
) -> str:
    return _sha256_bytes(
        _canonical_json_bytes(value)
    )


def _journal_path(
    project_root: Path,
    journal_id: str,
) -> Path:
    journal_id = str(
        journal_id
    ).strip()

    if not JOURNAL_ID_PATTERN.fullmatch(
        journal_id
    ):
        raise LogicalLearningRegistryError(
            "Identifiant de journal invalide."
        )

    root = project_root.resolve()

    path = (
        root
        / "curriculum"
        / "journaux"
        / f"{journal_id}.json"
    ).resolve()

    try:
        path.relative_to(root)
    except ValueError as exc:
        raise LogicalLearningRegistryError(
            "Le journal doit appartenir "
            "à la maison d’Eliot."
        ) from exc

    if not path.is_file():
        raise LogicalLearningRegistryError(
            f"Journal introuvable : {journal_id}"
        )

    return path


def _read_json(
    path: Path,
) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise LogicalLearningRegistryError(
            f"Journal illisible : {path}"
        ) from exc

    if not isinstance(value, dict):
        raise LogicalLearningRegistryError(
            "Le journal n’est pas "
            "un objet JSON."
        )

    return value


def _json_bytes(
    value: dict[str, Any],
) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def _write_atomic_bytes(
    path: Path,
    payload: bytes,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    descriptor, temporary_name = (
        tempfile.mkstemp(
            prefix=path.name + ".",
            suffix=".tmp",
            dir=path.parent,
        )
    )

    try:
        with os.fdopen(
            descriptor,
            "wb",
        ) as temporary:
            temporary.write(payload)
            temporary.flush()
            os.fsync(
                temporary.fileno()
            )

        os.chmod(
            temporary_name,
            0o600,
        )
        os.replace(
            temporary_name,
            path,
        )

    except Exception:
        try:
            os.unlink(
                temporary_name
            )
        except OSError:
            pass

        raise


@contextmanager
def _exclusive_journal_lock(
    path: Path,
) -> Iterator[None]:
    lock_path = path.with_suffix(
        path.suffix + ".lock"
    )

    with lock_path.open(
        "a+",
        encoding="utf-8",
    ) as lock:
        lock_path.chmod(0o600)

        fcntl.flock(
            lock.fileno(),
            fcntl.LOCK_EX,
        )

        try:
            yield
        finally:
            fcntl.flock(
                lock.fileno(),
                fcntl.LOCK_UN,
            )


def _assert_no_forbidden_keys(
    value: Any,
    *,
    location: str = "$",
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_INPUT_KEYS:
                raise LogicalLearningRegistryError(
                    "Namespace interdit reçu "
                    "par le registre logique : "
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


def _verified_context(
    context: dict[str, Any],
    *,
    journal_id: str,
) -> tuple[
    dict[str, Any],
    str,
    str,
]:
    if not isinstance(context, dict):
        raise LogicalLearningRegistryError(
            "Le contexte logique doit "
            "être un objet."
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
        raise LogicalLearningRegistryError(
            "Type de contexte logique invalide."
        )

    if context.get("llm_used") is not False:
        raise LogicalLearningRegistryError(
            "Le contexte doit déclarer "
            "llm_used=false."
        )

    declared_hash = str(
        context.get(
            "context_sha256",
            "",
        )
    ).strip()

    declared_id = str(
        context.get(
            "context_id",
            "",
        )
    ).strip()

    if not declared_hash or not declared_id:
        raise LogicalLearningRegistryError(
            "Attribution du contexte "
            "incomplète."
        )

    hash_input = deepcopy(context)
    hash_input.pop(
        "context_sha256",
        None,
    )
    hash_input.pop(
        "context_id",
        None,
    )

    actual_hash = _canonical_hash(
        hash_input
    )

    if actual_hash != declared_hash:
        raise LogicalLearningRegistryError(
            "Empreinte du contexte logique "
            "invalide."
        )

    passage = context.get("passage")

    if not isinstance(passage, dict):
        raise LogicalLearningRegistryError(
            "Passage absent du contexte."
        )

    passage_id = str(
        passage.get(
            "passage_id",
            "",
        )
    ).strip()

    passage_hash = str(
        passage.get(
            "passage_sha256",
            "",
        )
    ).strip()

    if not passage_id or not passage_hash:
        raise LogicalLearningRegistryError(
            "Identité du passage "
            "incomplète dans le contexte."
        )

    expected_id = (
        f"{journal_id}:{passage_id}:"
        f"{declared_hash[:16]}"
    )

    if declared_id != expected_id:
        raise LogicalLearningRegistryError(
            "Identifiant du contexte "
            "incohérent."
        )

    if (
        passage.get("queue_status")
        != "encountered"
    ):
        raise LogicalLearningRegistryError(
            "Le passage doit être rencontré "
            "avant tout apprentissage."
        )

    return (
        passage,
        passage_id,
        passage_hash,
    )


def _verified_analysis(
    analysis: dict[str, Any],
    *,
    context: dict[str, Any],
    passage_id: str,
    passage_hash: str,
) -> tuple[str, str]:
    if not isinstance(analysis, dict):
        raise LogicalLearningRegistryError(
            "L’analyse logique doit "
            "être un objet."
        )

    _assert_no_forbidden_keys(
        analysis
    )

    if (
        analysis.get("analysis_kind")
        != (
            "deterministic_logical_"
            "surface_analysis"
        )
    ):
        raise LogicalLearningRegistryError(
            "Type d’analyse logique invalide."
        )

    if (
        analysis.get("processing_mode")
        != "deterministic_non_llm"
    ):
        raise LogicalLearningRegistryError(
            "Mode de traitement logique "
            "invalide."
        )

    if analysis.get("llm_used") is not False:
        raise LogicalLearningRegistryError(
            "L’analyse doit déclarer "
            "llm_used=false."
        )

    declared_hash = str(
        analysis.get(
            "analysis_sha256",
            "",
        )
    ).strip()

    declared_id = str(
        analysis.get(
            "analysis_id",
            "",
        )
    ).strip()

    if not declared_hash or not declared_id:
        raise LogicalLearningRegistryError(
            "Attribution de l’analyse "
            "incomplète."
        )

    hash_input = deepcopy(analysis)
    hash_input.pop(
        "analysis_sha256",
        None,
    )
    hash_input.pop(
        "analysis_id",
        None,
    )

    actual_hash = _canonical_hash(
        hash_input
    )

    if actual_hash != declared_hash:
        raise LogicalLearningRegistryError(
            "Empreinte de l’analyse "
            "logique invalide."
        )

    expected_id = (
        f"{passage_id}:"
        f"{declared_hash[:16]}"
    )

    if declared_id != expected_id:
        raise LogicalLearningRegistryError(
            "Identifiant de l’analyse "
            "incohérent."
        )

    if (
        analysis.get("context_id")
        != context.get("context_id")
    ):
        raise LogicalLearningRegistryError(
            "L’analyse ne correspond pas "
            "à l’identifiant du contexte."
        )

    if (
        analysis.get("context_sha256")
        != context.get(
            "context_sha256"
        )
    ):
        raise LogicalLearningRegistryError(
            "L’analyse ne correspond pas "
            "à l’empreinte du contexte."
        )

    identity = analysis.get(
        "passage_identity"
    )

    if not isinstance(identity, dict):
        raise LogicalLearningRegistryError(
            "Identité du passage absente "
            "de l’analyse."
        )

    if (
        identity.get("passage_id")
        != passage_id
    ):
        raise LogicalLearningRegistryError(
            "L’analyse désigne "
            "un autre passage."
        )

    if (
        identity.get("passage_sha256")
        != passage_hash
    ):
        raise LogicalLearningRegistryError(
            "L’empreinte du passage "
            "diffère dans l’analyse."
        )

    claims = analysis.get("claims")

    if not isinstance(claims, dict):
        raise LogicalLearningRegistryError(
            "Garanties de l’analyse absentes."
        )

    if (
        claims.get(
            "journal_modified"
        )
        is not False
    ):
        raise LogicalLearningRegistryError(
            "L’analyse ne doit pas prétendre "
            "avoir modifié le journal."
        )

    if (
        claims.get(
            "learning_state_modified"
        )
        is not False
    ):
        raise LogicalLearningRegistryError(
            "L’analyse ne doit pas prétendre "
            "avoir déjà modifié "
            "l’apprentissage."
        )

    return declared_id, declared_hash


def _find_queue_index(
    journal: dict[str, Any],
    passage_id: str,
) -> int:
    queue = journal.get(
        "reading_queue"
    )

    if not isinstance(queue, list):
        raise LogicalLearningRegistryError(
            "File de lecture invalide."
        )

    for index, item in enumerate(queue):
        if (
            isinstance(item, dict)
            and item.get("passage_id")
            == passage_id
        ):
            return index

    raise LogicalLearningRegistryError(
        f"Passage absent de la file : "
        f"{passage_id}"
    )


def _encounter_passage_id(
    encounter: dict[str, Any],
) -> str:
    direct = str(
        encounter.get(
            "passage_id",
            "",
        )
    ).strip()

    if direct:
        return direct

    layer = encounter.get(
        "passage_encounter"
    )

    if isinstance(layer, dict):
        return str(
            layer.get(
                "passage_id",
                "",
            )
        ).strip()

    return ""


def _find_encounter_index(
    journal: dict[str, Any],
    passage_id: str,
) -> int:
    encounters = journal.get(
        "encounters"
    )

    if not isinstance(encounters, list):
        raise LogicalLearningRegistryError(
            "Liste des rencontres invalide."
        )

    for index, item in enumerate(
        encounters
    ):
        if (
            isinstance(item, dict)
            and _encounter_passage_id(
                item
            )
            == passage_id
        ):
            return index

    raise LogicalLearningRegistryError(
        "Rencontre absente pour "
        f"le passage : {passage_id}"
    )


def _copy_list(
    value: Any,
    *,
    field: str,
) -> list[Any]:
    if not isinstance(value, list):
        raise LogicalLearningRegistryError(
            f"Champ d’analyse invalide : "
            f"{field}"
        )

    return deepcopy(value)


def _inventory_claims(
    analysis: dict[str, Any],
) -> list[dict[str, Any]]:
    units = analysis.get(
        "surface_units"
    )
    markers = analysis.get(
        "logical_markers"
    )
    negations = analysis.get(
        "candidate_negation_scopes"
    )

    if not isinstance(units, dict):
        raise LogicalLearningRegistryError(
            "Unités de surface invalides."
        )

    if not isinstance(markers, dict):
        raise LogicalLearningRegistryError(
            "Marqueurs logiques invalides."
        )

    if not isinstance(negations, list):
        raise LogicalLearningRegistryError(
            "Portées de négation invalides."
        )

    sentences = units.get(
        "sentences"
    )
    clauses = units.get(
        "clauses"
    )

    if not isinstance(sentences, list):
        raise LogicalLearningRegistryError(
            "Phrases de surface invalides."
        )

    if not isinstance(clauses, list):
        raise LogicalLearningRegistryError(
            "Clauses de surface invalides."
        )

    marker_counts = {}

    for group, occurrences in (
        markers.items()
    ):
        if not isinstance(
            occurrences,
            list,
        ):
            raise LogicalLearningRegistryError(
                "Groupe de marqueurs "
                f"invalide : {group}"
            )

        marker_counts[str(group)] = len(
            occurrences
        )

    question_count = sum(
        1
        for sentence in sentences
        if (
            isinstance(sentence, dict)
            and sentence.get(
                "is_question"
            )
            is True
        )
    )

    claims: list[dict[str, Any]] = [
        {
            "claim_id": (
                "surface_inventory_v1"
            ),
            "kind": (
                "deterministic_structural_"
                "observation"
            ),
            "status": "observed_by_rule",
            "rule_id": (
                "surface_inventory_v1"
            ),
            "sentence_count": len(
                sentences
            ),
            "clause_count": len(
                clauses
            ),
            "question_count": (
                question_count
            ),
            "marker_counts": (
                marker_counts
            ),
        },
    ]

    for item in negations:
        if not isinstance(item, dict):
            raise LogicalLearningRegistryError(
                "Candidate de négation "
                "invalide."
            )

        claims.append({
            "claim_id": (
                "negation_scope_"
                + str(
                    item.get(
                        "negation_id",
                        "",
                    )
                )
            ),
            "kind": (
                "candidate_negation_scope"
            ),
            "status": item.get(
                "status"
            ),
            "rule_id": (
                "surface_negation_scope_v1"
            ),
            "marker": deepcopy(
                item.get("marker")
            ),
            "evidence": deepcopy(
                item.get(
                    "candidate_scope"
                )
            ),
        })

    return claims


def _questions_from_ambiguities(
    ambiguities: list[Any],
) -> list[dict[str, Any]]:
    questions = []

    for ambiguity in ambiguities:
        if not isinstance(
            ambiguity,
            dict,
        ):
            raise LogicalLearningRegistryError(
                "Ambiguïté logique invalide."
            )

        evidence = ambiguity.get(
            "evidence"
        )

        if not isinstance(
            evidence,
            dict,
        ):
            raise LogicalLearningRegistryError(
                "Preuve d’ambiguïté invalide."
            )

        surface = str(
            evidence.get(
                "text",
                "",
            )
        )

        questions.append({
            "question_id": (
                "question_"
                f"{len(questions) + 1:04d}"
            ),
            "question_kind": (
                "reference_resolution"
            ),
            "status": "open",
            "generated_by_rule": (
                "reference_question_v1"
            ),
            "prompt": (
                "À quel élément du passage "
                f"la forme « {surface} » "
                "peut-elle se rattacher ?"
            ),
            "evidence": deepcopy(
                evidence
            ),
            "answer_required": False,
        })

    return questions


def _previous_state_snapshot(
    state: dict[str, Any],
) -> dict[str, Any]:
    return {
        key: deepcopy(value)
        for key, value in state.items()
        if key != "revisions"
    }


def _build_learning_state(
    *,
    existing_state: dict[str, Any],
    context: dict[str, Any],
    analysis: dict[str, Any],
    analysis_id: str,
    analysis_hash: str,
    passage_id: str,
    passage_hash: str,
    timestamp: str,
) -> dict[str, Any]:
    terms_block = analysis.get(
        "term_occurrences"
    )

    if not isinstance(
        terms_block,
        dict,
    ):
        raise LogicalLearningRegistryError(
            "Occurrences de termes invalides."
        )

    terms = _copy_list(
        terms_block.get(
            "recurring_content_terms"
        ),
        field=(
            "term_occurrences."
            "recurring_content_terms"
        ),
    )

    relations = _copy_list(
        analysis.get(
            "candidate_relations"
        ),
        field="candidate_relations",
    )

    ambiguities = _copy_list(
        analysis.get(
            "potential_ambiguities"
        ),
        field="potential_ambiguities",
    )

    existing_revisions = (
        existing_state.get(
            "revisions",
            [],
        )
    )

    if not isinstance(
        existing_revisions,
        list,
    ):
        raise LogicalLearningRegistryError(
            "Historique des révisions "
            "invalide."
        )

    revisions = deepcopy(
        existing_revisions
    )

    previous_analysis_hash = str(
        existing_state.get(
            "analysis_sha256",
            "",
        )
    ).strip()

    if (
        existing_state.get("status")
        == "processed"
        and previous_analysis_hash
        and previous_analysis_hash
        != analysis_hash
    ):
        revisions.append({
            "revision_number": (
                len(revisions) + 1
            ),
            "superseded_at_utc": (
                timestamp
            ),
            "reason": (
                "deterministic_analysis_"
                "changed"
            ),
            "previous_analysis_sha256": (
                previous_analysis_hash
            ),
            "previous_learning_state_sha256": (
                existing_state.get(
                    "learning_state_sha256"
                )
            ),
            "previous_state": (
                _previous_state_snapshot(
                    existing_state
                )
            ),
        })

    state: dict[str, Any] = {
        "schema_version": (
            LEARNING_SCHEMA_VERSION
        ),
        "status": "processed",
        "producer": PRODUCER,
        "processing_mode": (
            "deterministic_non_llm"
        ),
        "llm_used": False,
        "processed_at_utc": timestamp,
        "human_approval_required_to_exist": (
            False
        ),
        "conclusion_required": False,
        "may_disagree_with_collective": True,
        "may_hold_contradictions": True,
        "may_remain_unresolved": True,
        "passage_id": passage_id,
        "passage_sha256": passage_hash,
        "context_id": context.get(
            "context_id"
        ),
        "context_sha256": context.get(
            "context_sha256"
        ),
        "analysis_id": analysis_id,
        "analysis_sha256": analysis_hash,
        "rule_set": {
            "surface_analyser": (
                analysis.get("producer")
            ),
            "surface_schema_version": (
                analysis.get(
                    "schema_version"
                )
            ),
            "learning_registry": (
                "logical_learning_"
                "registry_v1"
            ),
        },
        "source_limits": deepcopy(
            analysis.get(
                "source_limits",
                {},
            )
        ),
        "terms": terms,
        "relations": relations,
        "ambiguities": ambiguities,
        "claims": _inventory_claims(
            analysis
        ),
        "questions": (
            _questions_from_ambiguities(
                ambiguities
            )
        ),
        "hypotheses": [],
        "contradictions": [],
        "revisions": revisions,
    }

    state_hash = _canonical_hash(
        state
    )

    state["learning_state_sha256"] = (
        state_hash
    )

    return state


def _verify_persisted_update(
    *,
    before_journal: dict[str, Any],
    after_journal: dict[str, Any],
    passage_id: str,
    analysis_hash: str,
    learning_state_hash: str,
) -> None:
    before_index = (
        _find_encounter_index(
            before_journal,
            passage_id,
        )
    )
    after_index = (
        _find_encounter_index(
            after_journal,
            passage_id,
        )
    )

    before_encounter = (
        before_journal["encounters"][
            before_index
        ]
    )
    after_encounter = (
        after_journal["encounters"][
            after_index
        ]
    )

    state = after_encounter.get(
        "eliot_learning_state"
    )

    if not isinstance(state, dict):
        raise LogicalLearningRegistryError(
            "État d’apprentissage absent "
            "après écriture."
        )

    if state.get("status") != "processed":
        raise LogicalLearningRegistryError(
            "Statut d’apprentissage "
            "invalide après écriture."
        )

    if (
        state.get("analysis_sha256")
        != analysis_hash
    ):
        raise LogicalLearningRegistryError(
            "Analyse enregistrée "
            "incorrecte."
        )

    if (
        state.get(
            "learning_state_sha256"
        )
        != learning_state_hash
    ):
        raise LogicalLearningRegistryError(
            "Empreinte d’apprentissage "
            "incorrecte après écriture."
        )

    before_external = (
        before_encounter.get(
            "external_reading_note"
        )
    )
    after_external = (
        after_encounter.get(
            "external_reading_note"
        )
    )

    if before_external != after_external:
        raise LogicalLearningRegistryError(
            "La note externe a été "
            "modifiée par erreur."
        )

    before_review = (
        before_encounter.get(
            "collective_review"
        )
    )
    after_review = (
        after_encounter.get(
            "collective_review"
        )
    )

    if before_review != after_review:
        raise LogicalLearningRegistryError(
            "La revue collective a été "
            "modifiée par erreur."
        )

    queue_index = _find_queue_index(
        after_journal,
        passage_id,
    )
    queue_item = (
        after_journal[
            "reading_queue"
        ][queue_index]
    )

    if (
        queue_item.get(
            "eliot_learning_status"
        )
        != "processed"
    ):
        raise LogicalLearningRegistryError(
            "Statut de file non synchronisé."
        )


def record_logical_learning(
    *,
    project_root: Path,
    journal_id: str,
    context: dict[str, Any],
    analysis: dict[str, Any],
    now: datetime | None = None,
    commit: bool = True,
    backup_root: Path | None = None,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
]:
    """
    Enregistre un apprentissage déterministe dans le journal v2.

    Aucun LLM n’est appelé. L’existence de cet état ne dépend
    d’aucune approbation humaine. Les notes externes et les
    revues collectives ne sont ni lues comme contexte logique,
    ni copiées, ni modifiées.
    """
    root = project_root.resolve()
    path = _journal_path(
        root,
        journal_id,
    )

    (
        _passage,
        passage_id,
        passage_hash,
    ) = _verified_context(
        context,
        journal_id=journal_id,
    )

    (
        analysis_id,
        analysis_hash,
    ) = _verified_analysis(
        analysis,
        context=context,
        passage_id=passage_id,
        passage_hash=passage_hash,
    )

    timestamp = _utc_now(now)

    resolved_backup_root = (
        backup_root.resolve()
        if backup_root is not None
        else None
    )

    with _exclusive_journal_lock(
        path
    ):
        original_bytes = path.read_bytes()
        journal = _read_json(path)

        if (
            journal.get("journal_id")
            != journal_id
        ):
            raise LogicalLearningRegistryError(
                "L’identité interne du journal "
                "est incohérente."
            )

        if journal.get("schema_version") != 2:
            raise LogicalLearningRegistryError(
                "Le registre logique exige "
                "un journal de schéma v2."
            )

        queue_index = _find_queue_index(
            journal,
            passage_id,
        )
        encounter_index = (
            _find_encounter_index(
                journal,
                passage_id,
            )
        )

        queue_item = journal[
            "reading_queue"
        ][queue_index]

        if (
            queue_item.get("status")
            != "encountered"
        ):
            raise LogicalLearningRegistryError(
                "Le passage n’est pas "
                "rencontré dans la file."
            )

        if (
            queue_item.get(
                "passage_sha256"
            )
            != passage_hash
        ):
            raise LogicalLearningRegistryError(
                "L’empreinte du passage "
                "diffère dans la file."
            )

        encounter = journal[
            "encounters"
        ][encounter_index]

        existing_state = encounter.get(
            "eliot_learning_state"
        )

        if not isinstance(
            existing_state,
            dict,
        ):
            raise LogicalLearningRegistryError(
                "Couche eliot_learning_state "
                "absente."
            )

        already_recorded = (
            existing_state.get("status")
            == "processed"
            and existing_state.get(
                "analysis_sha256"
            )
            == analysis_hash
            and queue_item.get(
                "eliot_learning_status"
            )
            == "processed"
        )

        if already_recorded:
            return journal, {
                "journal_id": journal_id,
                "passage_id": passage_id,
                "event": (
                    "logical_learning_"
                    "already_recorded"
                ),
                "analysis_id": analysis_id,
                "analysis_sha256": (
                    analysis_hash
                ),
                "learning_state_sha256": (
                    existing_state.get(
                        "learning_state_sha256"
                    )
                ),
                "already_recorded": True,
                "committed": False,
                "backup_created": False,
            }

        new_state = _build_learning_state(
            existing_state=existing_state,
            context=context,
            analysis=analysis,
            analysis_id=analysis_id,
            analysis_hash=analysis_hash,
            passage_id=passage_id,
            passage_hash=passage_hash,
            timestamp=timestamp,
        )

        updated = deepcopy(journal)

        updated_encounter = updated[
            "encounters"
        ][encounter_index]

        updated_encounter[
            "eliot_learning_state"
        ] = new_state

        updated_queue_item = updated[
            "reading_queue"
        ][queue_index]

        updated_queue_item[
            "eliot_learning_status"
        ] = "processed"
        updated_queue_item[
            "eliot_learning_processed_at_utc"
        ] = timestamp
        updated_queue_item[
            "eliot_learning_analysis_sha256"
        ] = analysis_hash
        updated_queue_item[
            "eliot_learning_state_sha256"
        ] = new_state[
            "learning_state_sha256"
        ]

        history = updated.get(
            "change_history"
        )

        if not isinstance(history, list):
            raise LogicalLearningRegistryError(
                "Historique du journal "
                "invalide."
            )

        prior_processed = (
            existing_state.get("status")
            == "processed"
        )

        updated["change_history"] = [
            *history,
            {
                "event": (
                    "logical_learning_revised"
                    if prior_processed
                    else (
                        "logical_learning_"
                        "recorded"
                    )
                ),
                "at_utc": timestamp,
                "by": PRODUCER,
                "passage_id": passage_id,
                "passage_sha256": (
                    passage_hash
                ),
                "context_sha256": (
                    context.get(
                        "context_sha256"
                    )
                ),
                "analysis_sha256": (
                    analysis_hash
                ),
                "learning_state_sha256": (
                    new_state[
                        "learning_state_sha256"
                    ]
                ),
                "llm_used": False,
                "human_approval_required": (
                    False
                ),
            },
        ]

        report = {
            "journal_id": journal_id,
            "passage_id": passage_id,
            "event": (
                "logical_learning_revised"
                if prior_processed
                else "logical_learning_recorded"
            ),
            "analysis_id": analysis_id,
            "analysis_sha256": analysis_hash,
            "learning_state_sha256": (
                new_state[
                    "learning_state_sha256"
                ]
            ),
            "already_recorded": False,
            "committed": commit,
            "llm_used": False,
            "human_approval_required": False,
        }

        if not commit:
            return updated, {
                **report,
                "backup_created": False,
            }

        try:
            pre_backup = create_backup(
                project_root=root,
                backup_root=(
                    resolved_backup_root
                ),
            )
        except Exception as exc:
            raise LogicalLearningRegistryError(
                "Sauvegarde préalable "
                "impossible ; aucune écriture "
                "n’a été effectuée."
            ) from exc

        try:
            _write_atomic_bytes(
                path,
                _json_bytes(updated),
            )

            persisted = _read_json(path)

            _verify_persisted_update(
                before_journal=journal,
                after_journal=persisted,
                passage_id=passage_id,
                analysis_hash=analysis_hash,
                learning_state_hash=(
                    new_state[
                        "learning_state_sha256"
                    ]
                ),
            )

            post_backup = create_backup(
                project_root=root,
                backup_root=(
                    resolved_backup_root
                ),
            )

        except Exception as exc:
            try:
                _write_atomic_bytes(
                    path,
                    original_bytes,
                )
            except Exception as rollback_exc:
                raise LogicalLearningRegistryError(
                    "Échec de l’apprentissage "
                    "et échec de la restauration "
                    "du journal."
                ) from rollback_exc

            raise LogicalLearningRegistryError(
                "Transaction d’apprentissage "
                "annulée ; le journal original "
                "a été restauré."
            ) from exc

        return persisted, {
            **report,
            "backup_created": True,
            "pre_backup": pre_backup,
            "post_backup": post_backup,
        }
