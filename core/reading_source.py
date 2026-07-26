from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any


METADATA_PATTERN = re.compile(r"^([^:]+?)\s*:\s*(.*)$")


class ReadingSourceError(ValueError):
    """Erreur contrôlée lors de l’analyse d’une source de lecture."""


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalise_block(value: str) -> str:
    lines = [
        line.strip()
        for line in value.splitlines()
        if line.strip()
    ]
    return " ".join(lines).strip()


def build_reading_manifest(
    project_root: Path,
    source_file: str,
) -> tuple[dict[str, Any], list[str]]:
    root = project_root.resolve()
    source_path = Path(source_file)

    if not source_path.is_absolute():
        source_path = root / source_path

    source_path = source_path.resolve()

    try:
        relative_path = source_path.relative_to(root)
    except ValueError as exc:
        raise ReadingSourceError(
            "La source doit appartenir à la maison d’Eliot."
        ) from exc

    if not source_path.is_file():
        raise ReadingSourceError(
            f"Source introuvable : {source_file}"
        )

    raw_text = source_path.read_text(encoding="utf-8")
    raw_bytes = source_path.read_bytes()

    if not raw_text.strip():
        raise ReadingSourceError("La source est vide.")

    header_text, separator, body_text = raw_text.partition("\n\n")

    if not separator:
        raise ReadingSourceError(
            "La source ne contient pas de séparation entre "
            "les métadonnées et le texte."
        )

    metadata: dict[str, str] = {}
    warnings: list[str] = []

    for line_number, line in enumerate(
        header_text.splitlines(),
        1,
    ):
        line = line.strip()

        if not line:
            continue

        match = METADATA_PATTERN.match(line)

        if not match:
            warnings.append(
                f"Métadonnée non reconnue à la ligne {line_number}."
            )
            continue

        key = match.group(1).strip().lower()
        value = match.group(2).strip()
        metadata[key] = value

    raw_blocks = re.split(r"\n\s*\n", body_text)
    passages: list[dict[str, Any]] = []

    for raw_block in raw_blocks:
        text = _normalise_block(raw_block)

        if not text:
            continue

        passage_number = len(passages) + 1

        if text.startswith("«") and not text.endswith("»"):
            warnings.append(
                f"Le passage {passage_number} commence par « "
                "mais ne se termine pas par »."
            )

        if text.endswith("»") and not text.startswith("«"):
            warnings.append(
                f"Le passage {passage_number} se termine par » "
                "sans commencer par «."
            )

        passages.append({
            "passage_id": f"passage_{passage_number:04d}",
            "order": passage_number,
            "sha256": _sha256_text(text),
            "character_count": len(text),
            "word_count": len(text.split()),
            "text": text,
        })

    if not passages:
        raise ReadingSourceError(
            "Aucun passage n’a été trouvé dans la source."
        )

    manifest = {
        "version": 1,
        "source_file": str(relative_path),
        "source_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "source_size_bytes": len(raw_bytes),
        "metadata": metadata,
        "passage_count": len(passages),
        "total_word_count": sum(
            passage["word_count"]
            for passage in passages
        ),
        "total_character_count": sum(
            passage["character_count"]
            for passage in passages
        ),
        "passages": passages,
    }

    return manifest, warnings
