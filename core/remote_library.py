from __future__ import annotations

import json
import re
import shutil
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


CATALOG_URL = (
    "https://library.wikicrypto.xyz/"
    "library-api/v1/catalog.json"
)

BOOK_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _download_json(url: str, timeout: float = 10.0) -> Any:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Eliot-Jr/1.0 WikiCrypto-Library",
        },
    )

    with urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get_content_type()

        if content_type not in {
            "application/json",
            "text/json",
            "text/plain",
        }:
            raise ValueError(
                f"Type inattendu pour {url}: {content_type}"
            )

        raw = response.read().decode("utf-8")

    return json.loads(raw)


def _safe_relative_json_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)

    if (
        path.is_absolute()
        or ".." in path.parts
        or path.suffix.lower() != ".json"
    ):
        raise ValueError(f"Chemin JSON non autorisé : {value}")

    return path


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _cache_is_fresh(catalog_path: Path, ttl_seconds: int) -> bool:
    if not catalog_path.is_file():
        return False

    age = time.time() - catalog_path.stat().st_mtime
    return age < ttl_seconds


def sync_remote_library(
    cache_root: Path,
    catalog_url: str = CATALOG_URL,
    ttl_seconds: int = 900,
) -> tuple[Path | None, list[str]]:
    """
    Synchronise WikiCrypto dans un cache local.

    Retourne le dossier cache/books ainsi que les erreurs non fatales.
    En cas de panne distante, le dernier cache valide reste utilisable.
    """
    cache_root = cache_root.resolve()
    books_root = cache_root / "books"
    catalog_path = cache_root / "catalog.json"
    errors: list[str] = []

    if _cache_is_fresh(catalog_path, ttl_seconds):
        return (
            books_root if books_root.is_dir() else None,
            errors,
        )

    cache_root.parent.mkdir(parents=True, exist_ok=True)

    staging = Path(
        tempfile.mkdtemp(
            prefix="library-staging-",
            dir=cache_root.parent,
        )
    )

    try:
        catalog = _download_json(catalog_url)

        if not isinstance(catalog, dict):
            raise ValueError("Le catalogue distant n'est pas un objet JSON.")

        books = catalog.get("books")

        if not isinstance(books, list):
            raise ValueError(
                "Le catalogue distant ne contient pas de liste books."
            )

        _write_json(staging / "catalog.json", catalog)

        for book in books:
            if not isinstance(book, dict):
                raise ValueError(
                    "Une entrée du catalogue n'est pas un objet JSON."
                )

            book_id = str(book.get("id", "")).strip()

            if not BOOK_ID_PATTERN.fullmatch(book_id):
                raise ValueError(
                    f"Identifiant de livre non autorisé : {book_id!r}"
                )

            manifest_ref = str(book.get("manifest", "")).strip()
            toc_ref = str(book.get("table_of_contents", "")).strip()

            if not manifest_ref or not toc_ref:
                raise ValueError(
                    f"Métadonnées incomplètes pour le livre {book_id}."
                )

            manifest_path = _safe_relative_json_path(manifest_ref)
            toc_path = _safe_relative_json_path(toc_ref)

            manifest_url = urljoin(catalog_url, manifest_ref)
            toc_url = urljoin(catalog_url, toc_ref)

            manifest = _download_json(manifest_url)
            toc = _download_json(toc_url)

            destination = staging / "books" / book_id

            _write_json(destination / "manifest.json", manifest)
            _write_json(
                destination / "table_des_matieres.json",
                toc,
            )

            if not isinstance(toc, dict):
                raise ValueError(
                    f"Sommaire invalide pour le livre {book_id}."
                )

            chapters = toc.get("chapters", [])

            if not isinstance(chapters, list):
                raise ValueError(
                    f"Liste de chapitres invalide pour {book_id}."
                )

            for chapter in chapters:
                if not isinstance(chapter, dict):
                    continue

                memory_file = chapter.get("memory_file")

                if not memory_file:
                    continue

                relative_chapter = _safe_relative_json_path(
                    str(memory_file)
                )

                chapter_url = urljoin(
                    toc_url,
                    str(relative_chapter),
                )

                # Le sommaire est dans le dossier du livre.
                chapter_url = urljoin(
                    toc_url.rsplit("/", 1)[0] + "/",
                    str(relative_chapter),
                )

                chapter_data = _download_json(chapter_url)

                _write_json(
                    destination / Path(*relative_chapter.parts),
                    chapter_data,
                )

        old_cache = cache_root.with_name(
            cache_root.name + ".previous"
        )

        if old_cache.exists():
            shutil.rmtree(old_cache)

        if cache_root.exists():
            cache_root.replace(old_cache)

        staging.replace(cache_root)

        if old_cache.exists():
            shutil.rmtree(old_cache)

        return cache_root / "books", errors

    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        HTTPError,
        URLError,
    ) as exc:
        errors.append(f"Bibliothèque distante : {exc}")
        shutil.rmtree(staging, ignore_errors=True)

        if books_root.is_dir():
            errors.append(
                "Bibliothèque distante indisponible : "
                "utilisation du dernier cache valide."
            )
            return books_root, errors

        return None, errors
