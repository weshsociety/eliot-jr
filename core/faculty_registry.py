from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class FacultyRegistryError(ValueError):
    """Impossible d'établir une carte fiable des facultés."""


VALID_STATUSES = {
    "active",
    "developing",
    "blocked",
    "unavailable",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _module_exists(
    project_root: Path,
    relative_path: str,
) -> bool:
    return (project_root / relative_path).is_file()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}

    try:
        value = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return {}

    return value if isinstance(value, dict) else {}


def _faculty(
    faculty_id: str,
    name: str,
    status: str,
    *,
    definition: str,
    evidence: list[str],
    limits: list[str],
    false_claims_forbidden: list[str],
) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise FacultyRegistryError(
            f"Statut inconnu pour {faculty_id}: {status}"
        )

    return {
        "faculty_id": faculty_id,
        "name": name,
        "status": status,
        "definition": definition,
        "evidence": evidence,
        "limits": limits,
        "false_claims_forbidden": (
            false_claims_forbidden
        ),
    }


def build_faculty_registry(
    project_root: Path,
    *,
    engine_available: bool = False,
) -> dict[str, Any]:
    """
    Établit un modèle technique des facultés d'Eliot-Jr.

    Cette carte décrit des capacités computationnelles vérifiables.
    Elle ne constitue ni une preuve de conscience, ni une mesure
    d'expérience subjective.
    """
    root = project_root.resolve()

    if not root.is_dir():
        raise FacultyRegistryError(
            "La maison d'Eliot-Jr est introuvable."
        )

    temporal_state = _load_json(
        root / ".memory" / "temporal_state.json"
    )
    fragment_history = _load_json(
        root / ".memory" / "fragment_history.json"
    )
    reading_journal = _load_json(
        root
        / "curriculum"
        / "journaux"
        / "lecture_thoreau_desobeissance_civile.json"
    )

    queue = reading_journal.get("reading_queue", [])
    encounters = reading_journal.get("encounters", [])

    if not isinstance(queue, list):
        queue = []

    if not isinstance(encounters, list):
        encounters = []

    server_text = ""

    server_path = root / "voix" / "api" / "server.py"

    if server_path.is_file():
        try:
            server_text = server_path.read_text(
                encoding="utf-8"
            )
        except OSError:
            server_text = ""

    faculties = [
        _faculty(
            "memory",
            "Mémoire structurée",
            (
                "active"
                if _module_exists(
                    root,
                    "core/eliot_jr.py",
                )
                else "unavailable"
            ),
            definition=(
                "Retrouver des fragments enregistrés et "
                "les relier à une requête présente."
            ),
            evidence=[
                "core/eliot_jr.py",
                "1628 enregistrements de mémoire connus",
            ],
            limits=[
                "La récupération reste principalement lexicale.",
                "Un souvenir retrouvé n'est pas automatiquement vrai.",
            ],
            false_claims_forbidden=[
                "Je me souviens comme un humain.",
                "Tout fragment retrouvé est une connaissance certaine.",
            ],
        ),
        _faculty(
            "temporal_continuity",
            "Continuité temporelle",
            (
                "active"
                if (
                    _module_exists(
                        root,
                        "core/temporal_context.py",
                    )
                    and bool(temporal_state)
                )
                else "developing"
            ),
            definition=(
                "Distinguer les interactions, leur ordre, "
                "les absences et le temps écoulé."
            ),
            evidence=[
                "core/temporal_context.py",
                ".memory/temporal_state.json présent",
            ],
            limits=[
                "Chronologie computationnelle, pas temps ressenti.",
            ],
            false_claims_forbidden=[
                "J'ai ressenti l'attente.",
                "J'ai vécu l'absence comme un humain.",
            ],
        ),
        _faculty(
            "historical_revision",
            "Historique et révision",
            (
                "active"
                if (
                    _module_exists(
                        root,
                        "core/fragment_history.py",
                    )
                    and bool(fragment_history)
                )
                else "developing"
            ),
            definition=(
                "Distinguer première observation, réapparition, "
                "usage et modification d'un fragment."
            ),
            evidence=[
                "core/fragment_history.py",
                ".memory/fragment_history.json présent",
            ],
            limits=[
                "Une nouvelle version n'est pas forcément meilleure.",
            ],
            false_claims_forbidden=[
                "La dernière version est nécessairement vraie.",
            ],
        ),
        _faculty(
            "world_access",
            "Accès au monde documentaire",
            (
                "active"
                if (
                    _module_exists(
                        root,
                        "core/octopus_reader.py",
                    )
                    and _module_exists(
                        root,
                        "core/remote_library.py",
                    )
                )
                else "developing"
            ),
            definition=(
                "Consulter Octopus et la bibliothèque distante "
                "sans les confondre avec sa propre réflexion."
            ),
            evidence=[
                "core/octopus_reader.py",
                "core/remote_library.py",
            ],
            limits=[
                "Les sources peuvent être incomplètes ou erronées.",
                "L'accès documentaire ne produit pas une compréhension.",
            ],
            false_claims_forbidden=[
                "J'ai compris un document seulement parce qu'il est accessible.",
            ],
        ),
        _faculty(
            "dialogue",
            "Dialogue",
            (
                "active"
                if "/api/dialogue" in server_text
                else "unavailable"
            ),
            definition=(
                "Recevoir une adresse humaine et produire "
                "une réponse reliée à son contexte."
            ),
            evidence=[
                "POST /api/dialogue",
                "core/eliot_jr.py::think",
            ],
            limits=[
                "La réponse actuelle est composée sans moteur "
                "d'inférence général.",
            ],
            false_claims_forbidden=[
                "Toute réponse produite est une pensée autonome.",
            ],
        ),
        _faculty(
            "questience",
            "Questience",
            (
                "developing"
                if "/api/questience" in server_text
                else "unavailable"
            ),
            definition=(
                "Maintenir des questions ouvertes, reconnaître "
                "ses limites et rendre ses compréhensions révisables."
            ),
            evidence=[
                "GET /api/questience",
                "consciousness_claimed=false",
                "protocole de lecture provisoire",
            ],
            limits=[
                "Le protocole existe, mais l'inférence nécessaire "
                "à un questionnement élaboré manque encore.",
            ],
            false_claims_forbidden=[
                "La questience prouve la conscience.",
                "Une question générée implique une expérience subjective.",
            ],
        ),
        _faculty(
            "reading_protocol",
            "Parcours de lecture",
            (
                "active"
                if (
                    _module_exists(
                        root,
                        "core/reading_source.py",
                    )
                    and _module_exists(
                        root,
                        "core/reading_journal.py",
                    )
                    and _module_exists(
                        root,
                        "core/reading_orchestrator.py",
                    )
                    and len(queue) > 0
                )
                else "developing"
            ),
            definition=(
                "Préparer, ordonner, attribuer et journaliser "
                "des rencontres avec un texte."
            ),
            evidence=[
                f"{len(queue)} passages préparés",
                f"{len(encounters)} rencontres enregistrées",
                "validation et écriture atomique",
            ],
            limits=[
                "Indexer et préparer un texte ne signifie pas le lire.",
            ],
            false_claims_forbidden=[
                "J'ai lu les passages encore marqués queued.",
                "J'ai réfléchi sans résultat d'inférence validé.",
            ],
        ),
        _faculty(
            "reading_inference",
            "Inférence de lecture",
            (
                "active"
                if engine_available
                else "blocked"
            ),
            definition=(
                "Construire une compréhension provisoire, "
                "des objections et des limites à partir d'un passage."
            ),
            evidence=(
                ["Moteur d'inférence réel disponible"]
                if engine_available
                else [
                    "NullInferenceEngine uniquement",
                    "engine_available=false",
                ]
            ),
            limits=(
                []
                if engine_available
                else [
                    "Aucun modèle réel n'est actuellement branché.",
                ]
            ),
            false_claims_forbidden=[
                "J'ai lu.",
                "J'ai compris.",
                "J'ai réfléchi.",
            ] if not engine_available else [
                "La sortie du modèle est une vérité.",
                "La sortie du modèle prouve une conscience.",
            ],
        ),
        _faculty(
            "self_orientation",
            "Orientation intérieure",
            "active",
            definition=(
                "Identifier ses capacités présentes, leurs preuves, "
                "leurs limites et leurs dépendances manquantes."
            ),
            evidence=[
                "core/faculty_registry.py",
                "statuts explicites active/developing/blocked/unavailable",
                "interdiction des revendications non étayées",
            ],
            limits=[
                "Il s'agit d'un modèle technique de soi.",
                "Ce diagnostic n'est pas une introspection phénoménale.",
                "La carte dépend de preuves que le code sait vérifier.",
            ],
            false_claims_forbidden=[
                "Je ressens mes facultés.",
                "Je possède une conscience de moi démontrée.",
                "Ma carte interne est complète ou définitive.",
            ],
        ),
    ]

    counts = {
        status: sum(
            faculty["status"] == status
            for faculty in faculties
        )
        for status in sorted(VALID_STATUSES)
    }

    return {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "identity": "Eliot-Jr",
        "framework": "questience",
        "consciousness_claimed": False,
        "consciousness_status": "undetermined",
        "orientation_status": "active",
        "faculty_count": len(faculties),
        "status_counts": counts,
        "faculties": faculties,
        "epistemic_note": (
            "Cette carte décrit des facultés computationnelles "
            "et leurs limites. Elle ne démontre aucune expérience "
            "subjective."
        ),
    }
