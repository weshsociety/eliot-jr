from __future__ import annotations

from argparse import ArgumentParser
from copy import deepcopy
from pathlib import Path
from typing import Any
import hashlib
import json
import os
import re
import sys
import tempfile

from core.logical_learning_registry import (
    record_logical_learning,
)
from core.logical_reading_context import (
    build_logical_reading_context,
)
from core.logical_surface_analysis import (
    analyse_logical_surface,
)
from core.reading_status import (
    build_reading_status,
)


ROOT = Path("/home/eliot-jr")
DEFAULT_JOURNAL_ID = (
    "lecture_thoreau_desobeissance_civile"
)
PASSAGE_PATTERN = re.compile(
    r"^passage_[0-9]{4}$"
)
SHA256_PATTERN = re.compile(
    r"^[0-9a-f]{64}$"
)


def sha256_bytes(
    payload: bytes,
) -> str:
    return hashlib.sha256(
        payload
    ).hexdigest()


def sha256_path(
    path: Path,
) -> str:
    return sha256_bytes(
        path.read_bytes()
    )


def canonical(
    value: Any,
) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def atomic_restore(
    path: Path,
    payload: bytes,
) -> None:
    descriptor, temporary_name = (
        tempfile.mkstemp(
            prefix=path.name + ".restore.",
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


def passage_id_of(
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
        "passage_encounter",
        {},
    )

    if isinstance(layer, dict):
        return str(
            layer.get(
                "passage_id",
                "",
            )
        ).strip()

    return ""


def encounter_map(
    journal: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    result: dict[
        str,
        dict[str, Any],
    ] = {}

    encounters = journal.get(
        "encounters"
    )

    if not isinstance(
        encounters,
        list,
    ):
        raise AssertionError(
            "encounters est invalide."
        )

    for encounter in encounters:
        if not isinstance(
            encounter,
            dict,
        ):
            raise AssertionError(
                "Une rencontre est invalide."
            )

        passage_id = passage_id_of(
            encounter
        )

        if (
            not passage_id
            or passage_id in result
        ):
            raise AssertionError(
                "Identité de rencontre "
                "invalide ou dupliquée."
            )

        result[passage_id] = encounter

    return result


def queue_map(
    journal: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    queue = journal.get(
        "reading_queue"
    )

    if not isinstance(queue, list):
        raise AssertionError(
            "reading_queue est invalide."
        )

    result: dict[
        str,
        dict[str, Any],
    ] = {}

    for item in queue:
        if not isinstance(item, dict):
            raise AssertionError(
                "Une entrée de file est invalide."
            )

        passage_id = str(
            item.get(
                "passage_id",
                "",
            )
        ).strip()

        if (
            not passage_id
            or passage_id in result
        ):
            raise AssertionError(
                "Identité de file invalide "
                "ou dupliquée."
            )

        result[passage_id] = item

    return result


def protected_hashes() -> dict[str, str]:
    source = (
        ROOT
        / "curriculum"
        / "sources"
        / "thoreau_desobeissance_civile_extrait_en.txt"
    )
    candidates = (
        ROOT
        / ".memory"
        / "reading_candidates"
    )

    paths = [
        source,
        *sorted(
            candidates.glob("*.json")
        ),
    ]

    if len(paths) != 5:
        raise AssertionError(
            "Nombre inattendu de fichiers "
            f"protégés : {len(paths)}"
        )

    return {
        str(path): sha256_path(path)
        for path in paths
    }


def require_sha(
    value: str,
    *,
    label: str,
) -> str:
    value = str(value).strip().lower()

    if not SHA256_PATTERN.fullmatch(
        value
    ):
        raise ValueError(
            f"{label} doit être une "
            "empreinte SHA-256."
        )

    return value


def parse_arguments() -> tuple[
    str,
    str,
    str,
    str,
    str,
]:
    parser = ArgumentParser(
        description=(
            "Enregistre transactionnellement "
            "l'apprentissage logique d'un "
            "passage déjà rencontré."
        )
    )
    parser.add_argument(
        "passage_id",
    )
    parser.add_argument(
        "--journal-id",
        default=DEFAULT_JOURNAL_ID,
    )
    parser.add_argument(
        "--expected-journal-sha",
        required=True,
    )
    parser.add_argument(
        "--expected-analysis-sha",
        required=True,
    )
    parser.add_argument(
        "--expected-content-sha",
        required=True,
    )

    arguments = parser.parse_args()

    passage_id = str(
        arguments.passage_id
    ).strip()

    if not PASSAGE_PATTERN.fullmatch(
        passage_id
    ):
        parser.error(
            "passage_id doit suivre la forme "
            "passage_0000."
        )

    journal_id = str(
        arguments.journal_id
    ).strip()

    if not journal_id:
        parser.error(
            "journal_id ne peut pas être vide."
        )

    return (
        journal_id,
        passage_id,
        require_sha(
            arguments.expected_journal_sha,
            label="expected-journal-sha",
        ),
        require_sha(
            arguments.expected_analysis_sha,
            label="expected-analysis-sha",
        ),
        require_sha(
            arguments.expected_content_sha,
            label="expected-content-sha",
        ),
    )


def main() -> int:
    (
        journal_id,
        passage_id,
        expected_journal_sha,
        expected_analysis_sha,
        expected_content_sha,
    ) = parse_arguments()

    journal_path = (
        ROOT
        / "curriculum"
        / "journaux"
        / f"{journal_id}.json"
    )
    backup_root = (
        ROOT
        / ".backups"
        / "reading"
    )
    candidates_root = (
        ROOT
        / ".memory"
        / "reading_candidates"
    )

    before_bytes = (
        journal_path.read_bytes()
    )
    before_sha = sha256_bytes(
        before_bytes
    )

    if before_sha != expected_journal_sha:
        raise AssertionError(
            "Le journal vivant diffère de "
            "l'état prévisualisé : "
            f"{before_sha}"
        )

    protected_before = (
        protected_hashes()
    )
    before = json.loads(
        before_bytes.decode("utf-8")
    )

    if (
        not isinstance(before, dict)
        or before.get(
            "schema_version"
        )
        != 2
    ):
        raise AssertionError(
            "Le journal doit être en "
            "schéma v2."
        )

    encounters_before = encounter_map(
        before
    )
    queue_before = queue_map(
        before
    )

    if passage_id not in encounters_before:
        raise AssertionError(
            "Le passage n'a pas encore été "
            f"rencontré : {passage_id}"
        )

    if passage_id not in queue_before:
        raise AssertionError(
            "Le passage est absent de la file."
        )

    target_before = encounters_before[
        passage_id
    ]
    target_queue_before = queue_before[
        passage_id
    ]
    learning_before = target_before.get(
        "eliot_learning_state"
    )

    if not isinstance(
        learning_before,
        dict,
    ):
        raise AssertionError(
            "eliot_learning_state est absent."
        )

    if (
        target_queue_before.get("status")
        != "encountered"
        or learning_before.get("status")
        != "not_yet_processed"
        or target_queue_before.get(
            "eliot_learning_status"
        )
        != "not_yet_processed"
    ):
        raise AssertionError(
            "Le passage n'est pas dans "
            "l'état rencontré et en attente."
        )

    target_order = target_queue_before.get(
        "order"
    )

    if not isinstance(
        target_order,
        int,
    ):
        raise AssertionError(
            "Ordre de passage invalide."
        )

    prior_pending = [
        candidate_id
        for candidate_id, candidate
        in encounters_before.items()
        if (
            queue_before[
                candidate_id
            ].get("order", 0)
            < target_order
            and candidate.get(
                "eliot_learning_state",
                {},
            ).get("status")
            != "processed"
        )
    ]

    if prior_pending:
        raise AssertionError(
            "Des rencontres antérieures "
            "restent non traitées : "
            + ", ".join(
                sorted(prior_pending)
            )
        )

    prior_encounters = {
        candidate_id: canonical(
            candidate
        )
        for candidate_id, candidate
        in encounters_before.items()
        if candidate_id != passage_id
    }
    protected_target_layers = {
        key: canonical(
            target_before[key]
        )
        for key in (
            "passage_encounter",
            "external_reading_note",
            "collective_review",
        )
    }

    context = (
        build_logical_reading_context(
            project_root=ROOT,
            journal_id=journal_id,
            passage_id=passage_id,
        )
    )
    analysis = (
        analyse_logical_surface(
            context
        )
    )

    if (
        analysis.get(
            "analysis_sha256"
        )
        != expected_analysis_sha
    ):
        raise AssertionError(
            "L'analyse produite diffère de "
            "la prévisualisation : "
            f"{analysis.get('analysis_sha256')}"
        )

    preview, preview_report = (
        record_logical_learning(
            project_root=ROOT,
            journal_id=journal_id,
            context=context,
            analysis=analysis,
            commit=False,
            backup_root=backup_root,
        )
    )

    if (
        preview_report.get("event")
        != "logical_learning_recorded"
        or preview_report.get(
            "committed"
        )
        is not False
        or preview_report.get(
            "backup_created"
        )
        is not False
        or preview_report.get(
            "learning_content_sha256"
        )
        != expected_content_sha
    ):
        raise AssertionError(
            "La prévisualisation logique "
            "ne correspond pas aux "
            "attentes."
        )

    preview_state = encounter_map(
        preview
    )[passage_id][
        "eliot_learning_state"
    ]

    if (
        preview_state.get("status")
        != "processed"
        or preview_state.get(
            "analysis_sha256"
        )
        != expected_analysis_sha
        or preview_state.get(
            "learning_content_sha256"
        )
        != expected_content_sha
        or preview_state.get(
            "llm_used"
        )
        is not False
        or preview_state.get(
            "human_approval_required_to_exist"
        )
        is not False
    ):
        raise AssertionError(
            "L'état logique simulé est "
            "invalide."
        )

    if (
        journal_path.read_bytes()
        != before_bytes
    ):
        raise AssertionError(
            "La prévisualisation a modifié "
            "le journal."
        )

    try:
        persisted, report = (
            record_logical_learning(
                project_root=ROOT,
                journal_id=journal_id,
                context=context,
                analysis=analysis,
                commit=True,
                backup_root=backup_root,
            )
        )

        if (
            report.get("event")
            != "logical_learning_recorded"
            or report.get(
                "committed"
            )
            is not True
            or report.get(
                "backup_created"
            )
            is not True
            or report.get(
                "already_recorded"
            )
            is not False
            or report.get(
                "analysis_sha256"
            )
            != expected_analysis_sha
            or report.get(
                "learning_content_sha256"
            )
            != expected_content_sha
            or report.get(
                "llm_used"
            )
            is not False
            or report.get(
                "human_approval_required"
            )
            is not False
        ):
            raise AssertionError(
                "Le rapport d'écriture est "
                "invalide."
            )

        encounters_after = encounter_map(
            persisted
        )
        queue_after = queue_map(
            persisted
        )

        for (
            candidate_id,
            previous,
        ) in prior_encounters.items():
            if (
                canonical(
                    encounters_after[
                        candidate_id
                    ]
                )
                != previous
            ):
                raise AssertionError(
                    "Une rencontre antérieure "
                    "a été modifiée : "
                    f"{candidate_id}"
                )

        target_after = encounters_after[
            passage_id
        ]
        target_state = target_after[
            "eliot_learning_state"
        ]
        target_queue_after = queue_after[
            passage_id
        ]

        for (
            key,
            previous,
        ) in protected_target_layers.items():
            if (
                canonical(
                    target_after[key]
                )
                != previous
            ):
                raise AssertionError(
                    "Une couche protégée du "
                    "passage a été modifiée : "
                    f"{key}"
                )

        if (
            target_state.get("status")
            != "processed"
            or target_state.get(
                "analysis_sha256"
            )
            != expected_analysis_sha
            or target_state.get(
                "learning_content_sha256"
            )
            != expected_content_sha
            or target_state.get(
                "llm_used"
            )
            is not False
            or target_state.get(
                "human_approval_required_to_exist"
            )
            is not False
        ):
            raise AssertionError(
                "L'apprentissage persistant "
                "est invalide."
            )

        if (
            target_queue_after.get(
                "eliot_learning_status"
            )
            != "processed"
            or target_queue_after.get(
                "eliot_learning_analysis_sha256"
            )
            != expected_analysis_sha
            or target_queue_after.get(
                "eliot_learning_content_sha256"
            )
            != expected_content_sha
            or target_queue_after.get(
                "eliot_learning_state_sha256"
            )
            != target_state.get(
                "learning_state_sha256"
            )
        ):
            raise AssertionError(
                "La file n'est pas "
                "synchronisée avec "
                "l'apprentissage."
            )

        if (
            protected_hashes()
            != protected_before
        ):
            raise AssertionError(
                "La source ou une candidate "
                "a été modifiée."
            )

        status = build_reading_status(
            journal_path=journal_path,
            candidates_root=(
                candidates_root
            ),
            engine_available=False,
        )

        processed_count = sum(
            encounter.get(
                "eliot_learning_state",
                {},
            ).get("status")
            == "processed"
            for encounter in (
                persisted["encounters"]
            )
        )
        pending_count = sum(
            encounter.get(
                "eliot_learning_state",
                {},
            ).get("status")
            == "not_yet_processed"
            for encounter in (
                persisted["encounters"]
            )
        )

        if (
            status.get(
                "logical_learning_count"
            )
            != processed_count
            or status.get(
                "logical_learning_pending_count"
            )
            != pending_count
        ):
            raise AssertionError(
                "L'état public est "
                "désynchronisé."
            )

    except Exception:
        current_bytes = (
            journal_path.read_bytes()
        )

        if current_bytes != before_bytes:
            atomic_restore(
                journal_path,
                before_bytes,
            )

        raise

    after_sha = sha256_path(
        journal_path
    )

    print(
        "===== APPRENTISSAGE LOGIQUE ENREGISTRÉ ====="
    )
    print(
        "Journal :",
        journal_id,
    )
    print(
        "Passage :",
        passage_id,
    )
    print(
        "Événement :",
        report["event"],
    )
    print(
        "Analyse SHA-256 :",
        report[
            "analysis_sha256"
        ],
    )
    print(
        "Contenu logique SHA-256 :",
        report[
            "learning_content_sha256"
        ],
    )
    print(
        "État daté SHA-256 :",
        report[
            "learning_state_sha256"
        ],
    )

    for field, label in (
        ("terms", "Termes"),
        ("relations", "Relations"),
        (
            "reference_forms",
            "Références",
        ),
        ("ambiguities", "Ambiguïtés"),
        ("claims", "Claims"),
        ("questions", "Questions"),
        ("hypotheses", "Hypothèses"),
        (
            "contradictions",
            "Contradictions",
        ),
    ):
        print(
            f"{label} :",
            len(target_state[field]),
        )

    print(
        "Apprentissages traités :",
        processed_count,
    )
    print(
        "Apprentissages en attente :",
        pending_count,
    )
    print(
        "Rencontres antérieures inchangées :",
        True,
    )
    print(
        "Couches protégées du passage "
        "inchangées :",
        True,
    )
    print(
        "Source et candidates inchangées :",
        True,
    )
    print(
        "Journal avant :",
        before_sha,
    )
    print(
        "Journal après :",
        after_sha,
    )
    print("Appel LLM : non")
    print(
        "Validation humaine requise :",
        "non",
    )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(
            main()
        )
    except Exception as exc:
        print(
            "Enregistrement logique : "
            f"ÉCHEC — {exc}",
            file=sys.stderr,
        )
        raise
