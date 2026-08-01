#!/usr/bin/env python3

import argparse
import json
import os
import ssl
import sys
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


BASE_URL = os.environ.get(
    "ELIOT_OBSIDIAN_URL",
    "https://127.0.0.1:37124",
).rstrip("/")

KEY_FILE = Path(
    os.environ.get(
        "ELIOT_OBSIDIAN_KEY_FILE",
        "~/.config/eliot-jr/secrets/obsidian_api_key",
    )
).expanduser()

ALLOWED_DIRECTORIES = (
    "000_synthèse",
    "00_Méthode",
    "01_Acteurs",
    "02_Flux",
    "03_Chronologie",
    "04_Patterns",
    "05_Cartes",
    "06_Hypothèses",
    "07_Sources",
    "08_Résistances",
    "09_Livre",
)

ALLOWED_FILES = (
    "ENQUÊTE_RÉSEAUX_EPSTEIN.MD.md",
)


def load_api_key() -> str:
    try:
        key = KEY_FILE.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(
            f"Impossible de lire la clé API : {KEY_FILE}: {exc}"
        ) from exc

    if not key:
        raise RuntimeError(f"Clé API vide : {KEY_FILE}")

    return key


def normalize_path(raw_path: str) -> str:
    path = raw_path.strip().strip("/")

    if not path:
        return ""

    if "\\" in path or "\x00" in path:
        raise ValueError("Chemin invalide")

    parts = PurePosixPath(path).parts

    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("Navigation relative interdite")

    return "/".join(parts)


def is_allowed(path: str) -> bool:
    if not path:
        return True

    if path in ALLOWED_FILES:
        return True

    return any(
        path == root or path.startswith(root + "/")
        for root in ALLOWED_DIRECTORIES
    )


def tls_context() -> ssl.SSLContext:
    ca_file = os.environ.get("ELIOT_OBSIDIAN_CA_FILE")

    if ca_file:
        return ssl.create_default_context(cafile=ca_file)

    # Temporaire : certificat Obsidian auto-signé.
    # Une copie vérifiée du certificat sera installée ensuite sur le VPS.
    return ssl._create_unverified_context()


def get(endpoint: str):
    request = Request(
        BASE_URL + endpoint,
        method="GET",
        headers={
            "Authorization": f"Bearer {load_api_key()}",
            "Accept": "application/json, text/markdown, text/plain",
            "User-Agent": "Eliot-Jr-Obsidian-ReadOnly/1.0",
        },
    )

    try:
        with urlopen(
            request,
            context=tls_context(),
            timeout=15,
        ) as response:
            content_type = response.headers.get("Content-Type", "")
            body = response.read().decode("utf-8")

    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Obsidian HTTP {exc.code}: {error_body}"
        ) from exc

    except URLError as exc:
        raise RuntimeError(
            f"Connexion Obsidian impossible : {exc.reason}"
        ) from exc

    if "application/json" in content_type:
        return json.loads(body)

    return {
        "content_type": content_type,
        "content": body,
    }


def vault_endpoint(path: str, directory: bool = False) -> str:
    encoded = quote(path, safe="/")

    if not encoded:
        return "/vault/"

    endpoint = "/vault/" + encoded

    if directory and not endpoint.endswith("/"):
        endpoint += "/"

    return endpoint


def command_status() -> None:
    data = get("/")
    print(json.dumps(data, ensure_ascii=False, indent=2))


def command_list(raw_path: str) -> None:
    path = normalize_path(raw_path)

    if not is_allowed(path):
        raise PermissionError(
            f"Chemin hors liste blanche : {path}"
        )

    data = get(vault_endpoint(path, directory=True))

    if not path and isinstance(data, dict):
        files = data.get("files", [])

        allowed_entries = [
            entry
            for entry in files
            if entry.rstrip("/") in ALLOWED_DIRECTORIES
            or entry in ALLOWED_FILES
        ]

        data = {
            "scope": "epstein_investigation",
            "read_only": True,
            "files": allowed_entries,
        }

    print(json.dumps(data, ensure_ascii=False, indent=2))


def command_read(raw_path: str) -> None:
    path = normalize_path(raw_path)

    if not path:
        raise ValueError("Un fichier doit être indiqué")

    if not is_allowed(path):
        raise PermissionError(
            f"Chemin hors liste blanche : {path}"
        )

    data = get(vault_endpoint(path))
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Connecteur Obsidian en lecture seule pour Eliot-Jr"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status")

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("path", nargs="?", default="")

    read_parser = subparsers.add_parser("read")
    read_parser.add_argument("path")

    args = parser.parse_args()

    try:
        if args.command == "status":
            command_status()
        elif args.command == "list":
            command_list(args.path)
        elif args.command == "read":
            command_read(args.path)

    except (RuntimeError, ValueError, PermissionError, json.JSONDecodeError) as exc:
        print(f"ERREUR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
