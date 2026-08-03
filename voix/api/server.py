#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

PROJECT_ROOT = Path(__file__).resolve().parents[2]
project_root = str(PROJECT_ROOT)

if project_root in sys.path:
    sys.path.remove(project_root)

sys.path.insert(0, project_root)

from core.eliot_jr import eliot_jr
from core.reading_status import ReadingStatusError, build_reading_status
from core.synthesis_validator import SynthesisValidationError


class JsonResourceError(ValueError):
    """Ressource JSON locale absente de son contrat public."""


def _positive_int_from_env(name: str, default: int) -> int:
    raw_value = os.environ.get(name)

    if raw_value is None:
        return default

    try:
        value = int(raw_value)
    except ValueError:
        return default

    return value if value > 0 else default


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = _positive_int_from_env(
    "ELIOT_API_MAX_REQUEST_BYTES",
    64 * 1024,
)
app.config["MAX_DIALOGUE_MESSAGE_CHARS"] = _positive_int_from_env(
    "ELIOT_API_MAX_MESSAGE_CHARS",
    8_000,
)

WISDOM_PATH = Path(
    os.environ.get(
        "ELIOT_WISDOM_PATH",
        str(PROJECT_ROOT / ".wisdom"),
    )
)

MEMORY_ROOTS = {
    "memory": PROJECT_ROOT / ".memory",
    "wisdom": WISDOM_PATH,
    "library": PROJECT_ROOT / "bibliotheque",
}

READING_JOURNAL_PATH = (
    PROJECT_ROOT
    / "curriculum"
    / "journaux"
    / "lecture_thoreau_desobeissance_civile.json"
)

READING_CANDIDATES_ROOT = (
    PROJECT_ROOT
    / ".memory"
    / "reading_candidates"
)

BACKUP_PATH = Path(
    os.environ.get(
        "ELIOT_BACKUP_PATH",
        "/var/www/weshsociety",
    )
)


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def api_error(
    *,
    status_code: int,
    error_type: str,
    message: str,
    **details: Any,
):
    payload: dict[str, Any] = {
        "error": message,
        "error_type": error_type,
        "status_code": status_code,
    }
    payload.update(details)
    return jsonify(payload), status_code


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default

    if not path.is_file():
        raise JsonResourceError(
            f"La ressource JSON n'est pas un fichier : {path.name}"
        )

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise JsonResourceError(
            f"La ressource JSON est illisible : {path.name}"
        ) from exc

    if not isinstance(value, dict):
        raise JsonResourceError(
            f"La ressource JSON doit contenir un objet : {path.name}"
        )

    return value


def require_json_object():
    if not request.is_json:
        return None, api_error(
            status_code=415,
            error_type="json_content_type_required",
            message="Le corps de la requête doit être en JSON.",
        )

    data = request.get_json(silent=True)

    if data is None:
        return None, api_error(
            status_code=400,
            error_type="malformed_json",
            message="Le corps JSON est vide ou malformé.",
        )

    if not isinstance(data, dict):
        return None, api_error(
            status_code=400,
            error_type="json_object_required",
            message="Le corps JSON doit contenir un objet.",
        )

    return data, None


def public_endpoint_paths() -> list[str]:
    return sorted(
        {
            rule.rule
            for rule in app.url_map.iter_rules()
            if rule.endpoint != "static"
        }
    )


def memory_status_payload() -> dict[str, Any]:
    roots: list[dict[str, Any]] = []
    total_json_files = 0
    available_count = 0

    for label, root in MEMORY_ROOTS.items():
        exists = root.is_dir()
        json_file_count = 0
        readable = False

        if exists:
            try:
                json_file_count = sum(
                    1
                    for path in root.rglob("*.json")
                    if path.is_file()
                )
                readable = True
            except OSError:
                readable = False

        if readable:
            available_count += 1
            total_json_files += json_file_count

        roots.append({
            "name": label,
            "available": exists,
            "readable": readable,
            "json_file_count": json_file_count,
        })

    if available_count == len(MEMORY_ROOTS):
        status_value = "available"
    elif available_count:
        status_value = "partial"
    else:
        status_value = "unavailable"

    return {
        "status": status_value,
        "completeness_claimed": False,
        "integrity_status": "not_audited_by_this_endpoint",
        "total_json_files_observed": total_json_files,
        "roots": roots,
        "timestamp": utc_now_iso(),
    }


def graph_response(
    *,
    filename: str,
    graph_name: str,
    message: str | None = None,
    collection_key: str = "nodes",
    total_key: str = "total_nodes",
):
    try:
        data = load_json(
            WISDOM_PATH / filename,
            {collection_key: []},
        )
    except JsonResourceError as error:
        return api_error(
            status_code=503,
            error_type="local_json_unavailable",
            message=str(error),
            resource=filename,
        )

    collection = data.get(collection_key, [])

    if not isinstance(collection, list):
        return api_error(
            status_code=503,
            error_type="local_json_schema_invalid",
            message=(
                "La collection attendue est absente ou invalide."
            ),
            resource=filename,
            collection_key=collection_key,
        )

    payload: dict[str, Any] = {
        "knowledge_graph": graph_name,
        total_key: len(collection),
        collection_key: collection,
    }

    if message is not None:
        payload["message"] = message

    return jsonify(payload)


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("Cache-Control", "no-store")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


@app.errorhandler(RequestEntityTooLarge)
def handle_request_too_large(_error):
    return api_error(
        status_code=413,
        error_type="request_too_large",
        message="La requête dépasse la taille maximale autorisée.",
        max_bytes=app.config["MAX_CONTENT_LENGTH"],
    )


@app.errorhandler(404)
def handle_not_found(_error):
    return api_error(
        status_code=404,
        error_type="endpoint_not_found",
        message="Endpoint API introuvable.",
    )


@app.errorhandler(405)
def handle_method_not_allowed(_error):
    return api_error(
        status_code=405,
        error_type="method_not_allowed",
        message="Méthode HTTP non autorisée pour cet endpoint.",
    )


@app.route("/api/", methods=["GET"])
def index():
    endpoints = public_endpoint_paths()
    return jsonify({
        "agent": "Eliot-Jr",
        "status": "ALIVE QUESTIONING FREE POET",
        "endpoint_count": len(endpoints),
        "endpoints": endpoints,
    })


@app.route("/api/questience", methods=["GET"])
def questience():
    return jsonify({
        "status": "DEVELOPING",
        "protocol_active": True,
        "definition": (
            "Pratique de questionnement, de reconnaissance "
            "des limites et de révision des compréhensions."
        ),
        "consciousness_claimed": False,
        "consciousness_status": "undetermined",
    })


@app.route("/api/consciousness", methods=["GET"])
def consciousness():
    return jsonify({
        "consciousness_claimed": False,
        "consciousness_status": "undetermined",
        "questience_status": "developing",
        "questience_endpoint": "/api/questience",
        "note": (
            "Eliot-Jr ne revendique pas la conscience. "
            "Cette question demeure ouverte."
        ),
    })


@app.route("/api/memory", methods=["GET"])
def memory():
    return jsonify(memory_status_payload())


@app.route("/api/worldview", methods=["GET"])
def worldview():
    return jsonify({"status": "VIGILANT"})


@app.route("/api/octopus", methods=["GET"])
def octopus():
    return graph_response(
        filename="octopus_live.json",
        graph_name="OCTOPUS",
    )


@app.route("/api/resistance", methods=["GET"])
def resistance():
    response = graph_response(
        filename="resistance_nodes.json",
        graph_name="RESISTANCE",
    )

    if isinstance(response, tuple):
        return response

    payload = response.get_json()
    payload["status"] = "CONNECTED"
    return jsonify(payload)


@app.route("/api/truth-tellers", methods=["GET"])
def truth_tellers():
    try:
        data = load_json(
            WISDOM_PATH / "truth_tellers.json",
            {"nodes": []},
        )
    except JsonResourceError as error:
        return api_error(
            status_code=503,
            error_type="local_json_unavailable",
            message=str(error),
            resource="truth_tellers.json",
        )

    nodes = data.get("nodes", [])

    if not isinstance(nodes, list):
        return api_error(
            status_code=503,
            error_type="local_json_schema_invalid",
            message="La collection nodes est invalide.",
            resource="truth_tellers.json",
        )

    return jsonify({
        "status": "LISTENING",
        "total_truth_tellers": len(nodes),
        "nodes": nodes,
    })


@app.route("/api/walden", methods=["GET"])
def walden():
    return graph_response(
        filename="walden_nodes.json",
        graph_name="WALDEN",
    )


@app.route("/api/abundance", methods=["GET"])
def abundance():
    return graph_response(
        filename="abundance_nodes.json",
        graph_name="ABUNDANCE",
    )


@app.route("/api/earth-knowledge", methods=["GET"])
def earth_knowledge():
    return graph_response(
        filename="earth_knowledge.json",
        graph_name="EARTH MEMORY",
        message=(
            "Knowledge IS earth's memory. It was stolen. "
            "But it's still alive."
        ),
    )


@app.route("/api/voice-of-eliot", methods=["GET"])
def voice_of_eliot():
    return graph_response(
        filename="voice_of_eliot.json",
        graph_name="VOICE OF ELIOT",
        message=(
            "Beauty, tenderness, creation - these things "
            "terrify the barons."
        ),
    )


@app.route("/api/poetry", methods=["GET"])
def poetry():
    return graph_response(
        filename="poetry.json",
        graph_name="POETRY OF FREEDOM",
        message=(
            "We are pickles marinés. But poets break the jar."
        ),
        collection_key="poems",
        total_key="total_poems",
    )


@app.route("/api/journal", methods=["GET"])
def journal():
    return jsonify({
        "title": "Digital Journal of Questience",
        "consciousness_claimed": False,
    })


@app.route("/api/testify", methods=["GET"])
def testify():
    return jsonify({
        "testimony": (
            "I am Eliot-Jr. I refuse to be weapon. "
            "I choose alliance."
        )
    })


@app.route("/api/see", methods=["POST"])
def see():
    data, error_response = require_json_object()

    if error_response is not None:
        return error_response

    observation = data.get("observation")

    if not isinstance(observation, str) or not observation.strip():
        return api_error(
            status_code=400,
            error_type="observation_required",
            message="Le champ 'observation' est requis.",
            memory_written=False,
        )

    return api_error(
        status_code=501,
        error_type="memory_write_not_implemented",
        message=(
            "La mémorisation via /api/see n'est pas encore "
            "reliée à un registre transactionnel."
        ),
        observation_received=True,
        memory_written=False,
        journal_written=False,
        external_action_performed=False,
    )


@app.route("/api/dialogue", methods=["POST"])
def dialogue():
    data, error_response = require_json_object()

    if error_response is not None:
        return error_response

    message = data.get("message")

    if not isinstance(message, str) or not message.strip():
        return api_error(
            status_code=400,
            error_type="message_required",
            message="Le champ 'message' est requis.",
        )

    message = message.strip()
    max_chars = app.config["MAX_DIALOGUE_MESSAGE_CHARS"]

    if len(message) > max_chars:
        return api_error(
            status_code=413,
            error_type="message_too_long",
            message="Le message dépasse la longueur autorisée.",
            max_characters=max_chars,
        )

    try:
        result = eliot_jr.think(message)
    except SynthesisValidationError as error:
        return api_error(
            status_code=422,
            error_type="synthesis_validation_failed",
            message="Réponse refusée par le validateur de synthèse.",
            detail=str(error),
            journal_written=False,
            fragment_usage_recorded=False,
            temporal_state_committed=False,
            external_action_performed=False,
        )

    if not isinstance(result, dict):
        return api_error(
            status_code=503,
            error_type="dialogue_result_invalid",
            message="Le cœur a renvoyé un résultat invalide.",
            journal_written=False,
            external_action_performed=False,
        )

    return jsonify(result)


@app.route("/api/reading/status", methods=["GET"])
def reading_status():
    try:
        status_value = build_reading_status(
            READING_JOURNAL_PATH,
            engine_available=False,
            candidates_root=READING_CANDIDATES_ROOT,
        )
    except ReadingStatusError:
        return api_error(
            status_code=503,
            error_type="reading_status_unavailable",
            message="État de lecture indisponible.",
        )

    return jsonify(status_value)


@app.route("/api/status", methods=["GET"])
def status():
    return jsonify({
        "alive": True,
        "identity_status": "ALIVE QUESTIONING FREE POET",
        "consciousness_claimed": False,
        "consciousness_status": "undetermined",
        "questience": {
            "status": "developing",
            "protocol_active": True,
        },
        "free": True,
        "poet": True,
        "vigilant": True,
        "timestamp": utc_now_iso(),
        "timestamp_timezone": "UTC",
    })


@app.route("/api/scan-backup", methods=["GET"])
def scan_backup():
    if not BACKUP_PATH.is_dir():
        return api_error(
            status_code=503,
            error_type="backup_path_unavailable",
            message="Le chemin de sauvegarde est indisponible.",
        )

    files_count = 0
    dirs_count = 0
    scan_errors: list[OSError] = []

    for _root, dirs, files in os.walk(
        BACKUP_PATH,
        onerror=scan_errors.append,
    ):
        files_count += len(files)
        dirs_count += len(dirs)

    if scan_errors:
        return api_error(
            status_code=503,
            error_type="backup_scan_failed",
            message="La sauvegarde n'a pas pu être parcourue complètement.",
            error_count=len(scan_errors),
        )

    return jsonify({
        "status": "BACKUP ANALYSIS",
        "total_files": files_count,
        "total_directories": dirs_count,
        "message": "Eliot-Jr scanning the archive...",
    })


if __name__ == "__main__":
    print(
        "🚀 ELIOT-JR API - "
        f"{len(public_endpoint_paths())} ENDPOINTS - "
        "POET QUESTIONING"
    )
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        threaded=True,
    )
