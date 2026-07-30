from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any
import hashlib
import json
import re
import sys

from core.reading_status import (
    build_reading_status,
)


ROOT = Path("/home/eliot-jr")
JOURNAL = (
    ROOT
    / "curriculum"
    / "journaux"
    / "lecture_thoreau_desobeissance_civile.json"
)
CANDIDATES_ROOT = (
    ROOT
    / ".memory"
    / "reading_candidates"
)

SHA256_PATTERN = re.compile(
    r"^[0-9a-f]{64}$"
)

LEARNING_CONTENT_STATE_KEYS = {
    "status",
    "processed_at_utc",
    "revisions",
    "learning_content_sha256",
    "learning_state_sha256",
}

LEARNING_LIST_FIELDS = (
    "terms",
    "relations",
    "reference_forms",
    "ambiguities",
    "claims",
    "questions",
    "hypotheses",
    "contradictions",
    "revisions",
)


def fail(
    message: str,
) -> None:
    raise AssertionError(
        message
    )


def canonical_hash(
    value: Any,
) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(
        payload
    ).hexdigest()


def require_dict(
    value: Any,
    *,
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(
            f"{label} doit être un objet."
        )

    return value


def require_list(
    value: Any,
    *,
    label: str,
) -> list[Any]:
    if not isinstance(value, list):
        fail(
            f"{label} doit être une liste."
        )

    return value


def require_sha256(
    value: Any,
    *,
    label: str,
) -> str:
    if (
        not isinstance(value, str)
        or not SHA256_PATTERN.fullmatch(
            value
        )
    ):
        fail(
            f"{label} n'est pas une "
            "empreinte SHA-256 valide."
        )

    return value


def passage_id_of(
    encounter: dict[str, Any],
) -> str:
    direct = str(
        encounter.get(
            "passage_id",
            "",
        )
    ).strip()

    layer = encounter.get(
        "passage_encounter"
    )

    nested = ""

    if isinstance(layer, dict):
        nested = str(
            layer.get(
                "passage_id",
                "",
            )
        ).strip()

    if direct and nested and direct != nested:
        fail(
            "Les identifiants direct et "
            "imbriqué d'une rencontre "
            "diffèrent."
        )

    passage_id = direct or nested

    if not passage_id:
        fail(
            "Une rencontre ne possède pas "
            "d'identifiant de passage."
        )

    return passage_id


def index_queue(
    queue_list: list[Any],
) -> dict[str, dict[str, Any]]:
    queue: dict[
        str,
        dict[str, Any],
    ] = {}

    for expected_order, raw in enumerate(
        queue_list,
        1,
    ):
        item = require_dict(
            raw,
            label=(
                "Entrée de file "
                f"{expected_order}"
            ),
        )

        passage_id = str(
            item.get(
                "passage_id",
                "",
            )
        ).strip()

        if not passage_id:
            fail(
                "Une entrée de file ne "
                "possède pas de passage_id."
            )

        if passage_id in queue:
            fail(
                "Passage dupliqué dans "
                f"la file : {passage_id}"
            )

        if (
            item.get("order")
            != expected_order
        ):
            fail(
                "Ordre de file incohérent "
                f"pour {passage_id}."
            )

        require_sha256(
            item.get(
                "passage_sha256"
            ),
            label=(
                "Empreinte du passage "
                f"{passage_id}"
            ),
        )

        status = item.get(
            "status"
        )

        if status not in (
            "queued",
            "encountered",
        ):
            fail(
                "Statut de file inconnu "
                f"pour {passage_id} : "
                f"{status!r}"
            )

        queue[passage_id] = item

    return queue


def index_encounters(
    encounters_list: list[Any],
    queue: dict[
        str,
        dict[str, Any],
    ],
) -> dict[str, dict[str, Any]]:
    encounters: dict[
        str,
        dict[str, Any],
    ] = {}
    encounter_ids = set()
    encounter_numbers = []

    for raw in encounters_list:
        encounter = require_dict(
            raw,
            label="Rencontre",
        )
        passage_id = passage_id_of(
            encounter
        )

        if passage_id in encounters:
            fail(
                "Rencontre dupliquée pour "
                f"{passage_id}."
            )

        queue_item = queue.get(
            passage_id
        )

        if not isinstance(
            queue_item,
            dict,
        ):
            fail(
                "Rencontre sans entrée de "
                f"file : {passage_id}"
            )

        if (
            queue_item.get("status")
            != "encountered"
        ):
            fail(
                "Une rencontre existe pour "
                "un passage qui n'est pas "
                f"encountered : {passage_id}"
            )

        if (
            encounter.get(
                "schema_version"
            )
            != 2
        ):
            fail(
                "Schéma de rencontre invalide "
                f"pour {passage_id}."
            )

        passage_layer = require_dict(
            encounter.get(
                "passage_encounter"
            ),
            label=(
                "Couche passage_encounter "
                f"de {passage_id}"
            ),
        )
        require_dict(
            encounter.get(
                "external_reading_note"
            ),
            label=(
                "Couche external_reading_note "
                f"de {passage_id}"
            ),
        )
        require_dict(
            encounter.get(
                "collective_review"
            ),
            label=(
                "Couche collective_review "
                f"de {passage_id}"
            ),
        )
        require_dict(
            encounter.get(
                "eliot_learning_state"
            ),
            label=(
                "Couche eliot_learning_state "
                f"de {passage_id}"
            ),
        )

        if (
            passage_layer.get(
                "status"
            )
            != "recorded"
        ):
            fail(
                "La rencontre n'est pas "
                f"recorded : {passage_id}"
            )

        passage_order = (
            passage_layer.get(
                "passage_order"
            )
        )
        passage_sha = (
            passage_layer.get(
                "passage_sha256"
            )
        )

        if (
            passage_order
            != queue_item.get("order")
        ):
            fail(
                "Ordre de rencontre "
                f"incohérent : {passage_id}"
            )

        if (
            passage_sha
            != queue_item.get(
                "passage_sha256"
            )
        ):
            fail(
                "Empreinte de rencontre "
                f"incohérente : {passage_id}"
            )

        for field in (
            "passage_order",
            "passage_sha256",
        ):
            direct = encounter.get(
                field
            )
            nested = passage_layer.get(
                field
            )

            if (
                direct is not None
                and direct != nested
            ):
                fail(
                    "Projection directe "
                    f"incohérente ({field}) "
                    f"pour {passage_id}."
                )

        encounter_id = str(
            passage_layer.get(
                "encounter_id",
                encounter.get(
                    "encounter_id",
                    "",
                ),
            )
        ).strip()

        if not encounter_id:
            fail(
                "Identifiant de rencontre "
                f"absent : {passage_id}"
            )

        if encounter_id in encounter_ids:
            fail(
                "Identifiant de rencontre "
                f"dupliqué : {encounter_id}"
            )

        direct_encounter_id = (
            encounter.get(
                "encounter_id"
            )
        )

        if (
            direct_encounter_id
            is not None
            and direct_encounter_id
            != encounter_id
        ):
            fail(
                "Projection encounter_id "
                f"incohérente : {passage_id}"
            )

        encounter_number = (
            passage_layer.get(
                "encounter_number",
                encounter.get(
                    "encounter_number"
                ),
            )
        )

        if (
            not isinstance(
                encounter_number,
                int,
            )
            or encounter_number < 1
        ):
            fail(
                "Numéro de rencontre "
                f"invalide : {passage_id}"
            )

        direct_number = encounter.get(
            "encounter_number"
        )

        if (
            direct_number is not None
            and direct_number
            != encounter_number
        ):
            fail(
                "Projection du numéro "
                f"incohérente : {passage_id}"
            )

        if (
            encounter_number
            != passage_order
        ):
            fail(
                "La chronologie et l'ordre "
                f"du passage diffèrent : "
                f"{passage_id}"
            )

        encounter_ids.add(
            encounter_id
        )
        encounter_numbers.append(
            encounter_number
        )
        encounters[
            passage_id
        ] = encounter

    if sorted(
        encounter_numbers
    ) != list(
        range(
            1,
            len(encounters) + 1,
        )
    ):
        fail(
            "Les numéros de rencontre ne "
            "forment pas une chronologie "
            "continue."
        )

    return encounters


def learning_content_payload(
    state: dict[str, Any],
) -> dict[str, Any]:
    return {
        key: deepcopy(value)
        for key, value in state.items()
        if key
        not in LEARNING_CONTENT_STATE_KEYS
    }


def verify_processed_learning(
    *,
    passage_id: str,
    state: dict[str, Any],
    queue_item: dict[str, Any],
    passage_sha256: str,
    learning_events: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    if (
        state.get(
            "processing_mode"
        )
        != "deterministic_non_llm"
    ):
        fail(
            "Mode d'apprentissage invalide "
            f"pour {passage_id}."
        )

    if state.get(
        "llm_used"
    ) is not False:
        fail(
            "Attribution LLM invalide "
            f"pour {passage_id}."
        )

    if (
        state.get(
            "human_approval_required_to_exist"
        )
        is not False
    ):
        fail(
            "Dépendance à une approbation "
            f"humaine pour {passage_id}."
        )

    if (
        state.get("passage_id")
        != passage_id
    ):
        fail(
            "Identité d'apprentissage "
            f"incohérente : {passage_id}"
        )

    if (
        state.get(
            "passage_sha256"
        )
        != passage_sha256
    ):
        fail(
            "Empreinte de passage "
            "incohérente dans "
            f"l'apprentissage : {passage_id}"
        )

    for field in LEARNING_LIST_FIELDS:
        require_list(
            state.get(field),
            label=(
                f"{field} de {passage_id}"
            ),
        )

    require_dict(
        state.get("rule_set"),
        label=(
            f"rule_set de {passage_id}"
        ),
    )
    require_dict(
        state.get("source_limits"),
        label=(
            f"source_limits de {passage_id}"
        ),
    )

    analysis_sha = require_sha256(
        state.get(
            "analysis_sha256"
        ),
        label=(
            "Empreinte d'analyse de "
            f"{passage_id}"
        ),
    )
    content_sha = require_sha256(
        state.get(
            "learning_content_sha256"
        ),
        label=(
            "Empreinte de contenu de "
            f"{passage_id}"
        ),
    )
    state_sha = require_sha256(
        state.get(
            "learning_state_sha256"
        ),
        label=(
            "Empreinte d'état de "
            f"{passage_id}"
        ),
    )

    calculated_content_sha = (
        canonical_hash(
            learning_content_payload(
                state
            )
        )
    )

    if (
        calculated_content_sha
        != content_sha
    ):
        fail(
            "Empreinte du contenu logique "
            f"invalide : {passage_id}"
        )

    state_payload = deepcopy(
        state
    )
    state_payload.pop(
        "learning_state_sha256",
        None,
    )

    calculated_state_sha = (
        canonical_hash(
            state_payload
        )
    )

    if calculated_state_sha != state_sha:
        fail(
            "Empreinte de l'état logique "
            f"invalide : {passage_id}"
        )

    if (
        queue_item.get(
            "eliot_learning_status"
        )
        != "processed"
    ):
        fail(
            "Statut logique de file "
            f"invalide : {passage_id}"
        )

    queue_hashes = {
        "analysis": queue_item.get(
            "eliot_learning_analysis_sha256"
        ),
        "content": queue_item.get(
            "eliot_learning_content_sha256"
        ),
        "state": queue_item.get(
            "eliot_learning_state_sha256"
        ),
    }
    expected_hashes = {
        "analysis": analysis_sha,
        "content": content_sha,
        "state": state_sha,
    }

    if queue_hashes != expected_hashes:
        fail(
            "Empreintes de file "
            "désynchronisées pour "
            f"{passage_id}."
        )

    matching_events = [
        event
        for event in learning_events
        if (
            event.get(
                "passage_id"
            )
            == passage_id
            and event.get(
                "learning_state_sha256"
            )
            == state_sha
        )
    ]

    if len(matching_events) != 1:
        fail(
            "L'état courant doit avoir "
            "exactement un événement durable "
            f"correspondant : {passage_id}"
        )

    event = matching_events[0]

    if event.get("event") not in (
        "logical_learning_recorded",
        "logical_learning_revised",
    ):
        fail(
            "Type d'événement logique "
            f"invalide : {passage_id}"
        )

    if (
        event.get(
            "analysis_sha256"
        )
        != analysis_sha
        or event.get(
            "learning_content_sha256"
        )
        != content_sha
        or event.get(
            "llm_used"
        )
        is not False
        or event.get(
            "human_approval_required"
        )
        is not False
    ):
        fail(
            "Événement logique "
            f"désynchronisé : {passage_id}"
        )

    return {
        "status": "processed",
        "terms": len(
            state["terms"]
        ),
        "relations": len(
            state["relations"]
        ),
        "references": len(
            state[
                "reference_forms"
            ]
        ),
        "ambiguities": len(
            state["ambiguities"]
        ),
        "claims": len(
            state["claims"]
        ),
        "questions": len(
            state["questions"]
        ),
        "hypotheses": len(
            state["hypotheses"]
        ),
        "contradictions": len(
            state[
                "contradictions"
            ]
        ),
        "content_sha": (
            content_sha[:16]
        ),
        "state_sha": (
            state_sha[:16]
        ),
    }


def verify_pending_learning(
    *,
    passage_id: str,
    state: dict[str, Any],
    queue_item: dict[str, Any],
) -> dict[str, Any]:
    if (
        state.get(
            "processing_mode"
        )
        != "deterministic_non_llm"
        or state.get("llm_used")
        is not False
        or state.get(
            "human_approval_required_to_exist"
        )
        is not False
    ):
        fail(
            "État logique initial invalide "
            f"pour {passage_id}."
        )

    if (
        queue_item.get(
            "eliot_learning_status"
        )
        != "not_yet_processed"
    ):
        fail(
            "État logique de file "
            "désynchronisé pour "
            f"{passage_id}."
        )

    for field in (
        "claims",
        "terms",
        "relations",
        "reference_forms",
        "ambiguities",
        "questions",
        "hypotheses",
        "contradictions",
        "revisions",
    ):
        value = state.get(
            field,
            [],
        )

        if not isinstance(
            value,
            list,
        ):
            fail(
                f"{field} initial invalide "
                f"pour {passage_id}."
            )

        if value:
            fail(
                "Un apprentissage en attente "
                "contient déjà des données "
                f"dans {field} : {passage_id}"
            )

    return {
        "status": "not_yet_processed",
        "terms": 0,
        "relations": 0,
        "references": 0,
        "ambiguities": 0,
        "claims": 0,
        "questions": 0,
        "hypotheses": 0,
        "contradictions": 0,
        "content_sha": None,
        "state_sha": None,
    }


def main() -> int:
    before = JOURNAL.read_bytes()
    document = json.loads(
        before.decode("utf-8")
    )

    if not isinstance(
        document,
        dict,
    ):
        fail(
            "Le journal n'est pas "
            "un objet JSON."
        )

    if (
        document.get(
            "schema_version"
        )
        != 2
    ):
        fail(
            "Le journal n'est pas en "
            "schéma v2."
        )

    queue_list = require_list(
        document.get(
            "reading_queue"
        ),
        label="reading_queue",
    )
    encounters_list = require_list(
        document.get(
            "encounters"
        ),
        label="encounters",
    )
    history = require_list(
        document.get(
            "change_history"
        ),
        label="change_history",
    )

    queue = index_queue(
        queue_list
    )
    encounters = (
        index_encounters(
            encounters_list,
            queue,
        )
    )

    declared_count = document.get(
        "encounter_count"
    )

    if declared_count != len(
        encounters
    ):
        fail(
            "Compteur des rencontres "
            "incohérent."
        )

    encountered_queue_ids = {
        passage_id
        for passage_id, item
        in queue.items()
        if item.get("status")
        == "encountered"
    }

    if encountered_queue_ids != set(
        encounters
    ):
        fail(
            "La file et les rencontres "
            "ne désignent pas exactement "
            "les mêmes passages."
        )

    encounter_count = len(
        encounters
    )
    ordered_queue = list(
        queue.values()
    )

    for index, item in enumerate(
        ordered_queue
    ):
        expected_status = (
            "encountered"
            if index < encounter_count
            else "queued"
        )

        if (
            item.get("status")
            != expected_status
        ):
            fail(
                "La file n'est pas un "
                "préfixe chronologique : "
                f"{item['passage_id']}"
            )

        if (
            expected_status == "queued"
            and item.get(
                "eliot_learning_status"
            )
            not in (
                None,
                "",
            )
        ):
            fail(
                "Un passage non rencontré "
                "possède déjà un état logique : "
                f"{item['passage_id']}"
            )

    learning_events = [
        require_dict(
            event,
            label=(
                "Événement de change_history"
            ),
        )
        for event in history
        if (
            isinstance(event, dict)
            and event.get("event")
            in (
                "logical_learning_recorded",
                "logical_learning_revised",
            )
        )
    ]

    processed_count = 0
    pending_count = 0
    external_note_count = 0
    collective_review_count = 0
    reviewed_external_passages = set()
    external_note_passages = set()
    summaries = []

    for passage_id in sorted(
        encounters,
        key=lambda current: (
            queue[current]["order"]
        ),
    ):
        encounter = encounters[
            passage_id
        ]
        queue_item = queue[
            passage_id
        ]

        note = require_dict(
            encounter.get(
                "external_reading_note"
            ),
            label=(
                "Note externe de "
                f"{passage_id}"
            ),
        )
        review = require_dict(
            encounter.get(
                "collective_review"
            ),
            label=(
                "Revue collective de "
                f"{passage_id}"
            ),
        )
        state = require_dict(
            encounter.get(
                "eliot_learning_state"
            ),
            label=(
                "Apprentissage logique de "
                f"{passage_id}"
            ),
        )

        note_status = note.get(
            "status"
        )
        review_status = review.get(
            "status"
        )

        if note_status == "recorded":
            external_note_count += 1
            external_note_passages.add(
                passage_id
            )
        elif note_status not in (
            None,
            "",
            "not_recorded",
        ):
            fail(
                "Statut de note externe "
                f"inconnu pour {passage_id}: "
                f"{note_status!r}"
            )

        if review_status not in (
            None,
            "",
            "not_recorded",
        ):
            collective_review_count += 1
            reviewed_external_passages.add(
                passage_id
            )

        learning_status = state.get(
            "status"
        )

        if learning_status == "processed":
            summary = (
                verify_processed_learning(
                    passage_id=passage_id,
                    state=state,
                    queue_item=queue_item,
                    passage_sha256=(
                        queue_item[
                            "passage_sha256"
                        ]
                    ),
                    learning_events=(
                        learning_events
                    ),
                )
            )
            processed_count += 1

        elif (
            learning_status
            == "not_yet_processed"
        ):
            summary = (
                verify_pending_learning(
                    passage_id=passage_id,
                    state=state,
                    queue_item=queue_item,
                )
            )
            pending_count += 1

        else:
            fail(
                "Statut d'apprentissage "
                f"inconnu pour {passage_id}: "
                f"{learning_status!r}"
            )

        summaries.append(
            (
                passage_id,
                summary,
            )
        )

    if (
        processed_count
        + pending_count
        != encounter_count
    ):
        fail(
            "Comptage des apprentissages "
            "incohérent."
        )

    public_status = (
        build_reading_status(
            journal_path=JOURNAL,
            candidates_root=(
                CANDIDATES_ROOT
            ),
            engine_available=False,
        )
    )

    expected_public = {
        "passages_total": len(
            queue
        ),
        "passages_encountered": (
            encounter_count
        ),
        "encounter_count": (
            encounter_count
        ),
        "external_reading_note_count": (
            external_note_count
        ),
        "collective_review_count": len(
            reviewed_external_passages
            & external_note_passages
        ),
        "logical_learning_count": (
            processed_count
        ),
        "logical_learning_pending_count": (
            pending_count
        ),
        "reading_complete": (
            bool(queue)
            and encounter_count
            == len(queue)
        ),
        "logical_learning_complete": (
            bool(queue)
            and processed_count
            == len(queue)
        ),
    }

    for key, expected in (
        expected_public.items()
    ):
        actual = public_status.get(
            key
        )

        if actual != expected:
            fail(
                "État public incohérent "
                f"pour {key}: "
                f"{actual!r} au lieu "
                f"de {expected!r}"
            )

    after = JOURNAL.read_bytes()

    if before != after:
        fail(
            "Le journal a changé pendant "
            "l'audit en lecture seule."
        )

    print(
        "===== AUDIT DYNAMIQUE DES APPRENTISSAGES ====="
    )
    print(
        "Journal SHA-256 :",
        hashlib.sha256(
            before
        ).hexdigest(),
    )
    print(
        "Schéma du journal :",
        document[
            "schema_version"
        ],
    )
    print(
        "Passages du corpus :",
        len(queue),
    )
    print(
        "Rencontres :",
        encounter_count,
    )
    print()

    for passage_id, summary in summaries:
        print(
            passage_id,
            summary,
        )

    next_queued = next(
        (
            item["passage_id"]
            for item in ordered_queue
            if item.get("status")
            == "queued"
        ),
        None,
    )

    print()
    print(
        "===== SÉPARATION DES COUCHES ====="
    )
    print(
        "Notes externes enregistrées :",
        external_note_count,
    )
    print(
        "Revues collectives enregistrées :",
        collective_review_count,
    )
    print(
        "Apprentissages logiques traités :",
        processed_count,
    )
    print(
        "Apprentissages logiques en attente :",
        pending_count,
    )
    print(
        "Événements logiques durables :",
        len(learning_events),
    )
    print(
        "Appel LLM pour ces apprentissages :",
        "non",
    )
    print(
        "Validation humaine requise "
        "pour exister :",
        "non",
    )

    print()
    print(
        "===== PROGRESSION ====="
    )
    print(
        "Passages rencontrés :",
        f"{encounter_count}/{len(queue)}",
    )
    print(
        "Toutes les rencontres traitées :",
        (
            pending_count == 0
        ),
    )
    print(
        "Lecture complète :",
        public_status[
            "reading_complete"
        ],
    )
    print(
        "Curriculum logique complet :",
        public_status[
            "logical_learning_complete"
        ],
    )
    print(
        "Prochain passage en file :",
        next_queued,
    )

    print()
    print(
        "Journal inchangé pendant "
        "l'audit :",
        True,
    )
    print(
        "Audit dynamique : OK"
    )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(
            main()
        )
    except Exception as exc:
        print(
            "Audit dynamique : "
            f"ÉCHEC — {exc}",
            file=sys.stderr,
        )
        raise
