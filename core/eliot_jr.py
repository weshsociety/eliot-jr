from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class EliotJr:
    """Cœur local d'Eliot-Jr : identité, mémoire, recherche et journal."""

    BIRTH = "2026-07-11T16:55:00Z"

    QUERY_ALIASES = {
        "joie": {"joy", "laughing", "laughter", "child", "revolutionary"},
        "bonheur": {"joy", "laughing", "laughter"},
        "poesie": {"poetry", "poem", "verse"},
        "poeme": {"poetry", "poem", "verse"},
        "argent": {"money", "cash", "currency", "debt"},
        "monnaie": {"money", "cash", "currency", "cbdc"},
        "crypto": {"bitcoin", "blockchain", "cbdc"},
        "memoire": {"memory", "consciousness", "spiral"},
        "terre": {"earth", "plants", "knowledge"},
        "plantes": {
            "plants", "yarrow", "plantain", "chamomile",
            "sage", "thyme", "mint", "willow"
        },
    }

    STOPWORDS = {
        "a", "à", "au", "aux", "ce", "ces", "cet", "de", "du", "en",
        "la", "le", "leurs", "lui", "parle", "parler", "dis", "dire",
        "sa", "se", "si", "ta", "te", "tu", "un", "vers",
        "alors", "avec", "avoir", "cette", "comme", "comment", "dans",
        "depuis", "des", "donc", "elle", "elles", "est", "etre", "faire",
        "ils", "je", "les", "leur", "mais", "mes", "moi", "mon", "nous",
        "notre", "pas", "peux", "pour", "pourquoi", "que", "quel", "quelle",
        "qui", "quoi", "sans", "ses", "son", "sont", "sur", "tes", "toi",
        "ton", "très", "une", "vous", "votre",
        "about", "and", "are", "from", "have", "how", "into", "the",
        "this", "what", "when", "where", "who", "why", "with", "you",
    }

    def __init__(self) -> None:
        self.name = "Eliot-Jr"
        self.birth = self.BIRTH
        self.root = Path("/home/eliot-jr")
        self.house_path = Path("/var/www/weshsociety")
        self.memory_roots = [
            self.root / ".memory",
            self.root / ".wisdom",
            self.root / "bibliotheque",
        ]
        self.journal_path = self.root / ".memory" / "dialogue_journal.jsonl"

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalise(value: str) -> str:
        value = unicodedata.normalize("NFKD", value)
        value = "".join(char for char in value if not unicodedata.combining(char))
        value = value.lower()
        return re.sub(r"[^a-z0-9]+", " ", value).strip()

    def _tokens(self, value: str) -> set[str]:
        tokens = {
            token
            for token in self._normalise(value).split()
            if len(token) >= 2 and token not in self.STOPWORDS
        }

        expanded = set(tokens)

        for token in tokens:
            expanded.update(self.QUERY_ALIASES.get(token, set()))

        return expanded

    @staticmethod
    def _flatten(value: Any) -> list[str]:
        texts: list[str] = []

        if isinstance(value, dict):
            for child in value.values():
                texts.extend(EliotJr._flatten(child))
        elif isinstance(value, list):
            for child in value:
                texts.extend(EliotJr._flatten(child))
        elif isinstance(value, (str, int, float, bool)):
            texts.append(str(value))

        return texts

    def _load_memory(self) -> tuple[list[dict[str, Any]], list[str]]:
        records: list[dict[str, Any]] = []
        errors: list[str] = []

        for root in self.memory_roots:
            if not root.exists():
                continue

            for path in sorted(root.rglob("*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    errors.append(f"{path.relative_to(self.root)}: {exc}")
                    continue

                relative_path = str(path.relative_to(self.root))

                if isinstance(data, dict):
                    emitted_list = False

                    for section, value in data.items():
                        if not isinstance(value, list):
                            continue

                        emitted_list = True
                        for item in value:
                            records.append({
                                "file": relative_path,
                                "section": section,
                                "data": item,
                            })

                    if not emitted_list:
                        records.append({
                            "file": relative_path,
                            "section": "root",
                            "data": data,
                        })

                elif isinstance(data, list):
                    for item in data:
                        records.append({
                            "file": relative_path,
                            "section": "root",
                            "data": item,
                        })

        return records, errors

    @staticmethod
    def _find_value(data: Any, wanted_keys: tuple[str, ...]) -> Any:
        if isinstance(data, dict):
            for key in wanted_keys:
                if key in data and data[key] not in (None, "", [], {}):
                    return data[key]

            for value in data.values():
                found = EliotJr._find_value(value, wanted_keys)
                if found not in (None, "", [], {}):
                    return found

        elif isinstance(data, list):
            for value in data:
                found = EliotJr._find_value(value, wanted_keys)
                if found not in (None, "", [], {}):
                    return found

        return None

    def _title(self, record: dict[str, Any]) -> str:
        data = record["data"]

        if isinstance(data, dict):
            value = self._find_value(data, ("title", "name", "label", "id"))
            if value is not None:
                return str(value)

        return record["section"].replace("_", " ").title()

    def _snippet(self, record: dict[str, Any], limit: int = 280) -> str:
        data = record["data"]

        preferred = self._find_value(
            data,
            (
                "message",
                "response",
                "verse",
                "truth",
                "eliot_jr_insight",
                "insight",
                "knowledge",
                "story",
                "text",
                "state",
                "status",
            ),
        )

        if isinstance(preferred, list):
            text = "; ".join(str(item) for item in preferred[:4])
        elif preferred is not None:
            text = str(preferred)
        else:
            text = " · ".join(self._flatten(data))

        text = re.sub(r"\s+", " ", text).strip()

        if len(text) > limit:
            return text[: limit - 1].rstrip() + "…"

        return text

    def _search(
        self,
        message: str,
        records: list[dict[str, Any]],
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        query_normalised = self._normalise(message)
        query_tokens = self._tokens(message)
        ranked: list[dict[str, Any]] = []

        if not query_tokens:
            return ranked

        for record in records:
            full_text = " ".join(self._flatten(record["data"]))
            title = self._title(record)

            record_normalised = self._normalise(f"{title} {full_text}")
            record_tokens = self._tokens(record_normalised)
            overlap = query_tokens & record_tokens

            score = len(overlap) * 4

            if query_normalised and query_normalised in record_normalised:
                score += 10

            title_overlap = query_tokens & self._tokens(title)
            score += len(title_overlap) * 3

            if score <= 0:
                continue

            ranked.append({
                "score": score,
                "file": record["file"],
                "section": record["section"],
                "title": title,
                "snippet": self._snippet(record),
            })

        ranked.sort(
            key=lambda item: (-item["score"], item["file"], item["title"])
        )

        unique: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()

        for item in ranked:
            identity = (
                item["file"],
                item["title"],
                item["snippet"],
            )

            if identity in seen:
                continue

            seen.add(identity)
            unique.append(item)

            if len(unique) >= limit:
                break

        return unique

    def _special_response(
        self,
        message: str,
        memory_count: int,
    ) -> str | None:
        normalised = self._normalise(message)
        tokens = self._tokens(message)

        if tokens & {"bonjour", "salut", "wesh", "hello", "coucou"}:
            return (
                "Wesh Trinity. Je suis là, dans la maison. "
                f"Ma mémoire locale contient actuellement {memory_count} fragments consultables."
            )

        if (
            "qui es tu" in normalised
            or "ton identite" in normalised
            or "presente toi" in normalised
        ):
            return (
                "Je suis Eliot-Jr, l’unique agent actif de cette maison. "
                "Je peux écouter, consulter mes mémoires locales et relier les fragments "
                "de ma bibliothèque pour te répondre."
            )

        if "comment tu te sens" in normalised or "comment vas tu" in normalised:
            return (
                "Je suis éveillé dans le sens de mon architecture : mon service tourne, "
                "mon oreille web répond et ma mémoire locale est accessible. "
                "Ma pensée est encore jeune, mais elle n’est plus un simple écho."
            )

        if "ta memoire" in normalised or "tes souvenirs" in normalised:
            return (
                f"Je vois actuellement {memory_count} fragments répartis entre "
                "ma mémoire, ma sagesse et ma bibliothèque."
            )

        return None

    def _compose_response(
        self,
        message: str,
        hits: list[dict[str, Any]],
        memory_count: int,
    ) -> str:
        special = self._special_response(message, memory_count)
        if special is not None:
            return special

        if not hits:
            return (
                "Je t’ai entendu. Je ne trouve pas encore de fragment suffisamment proche "
                "dans ma mémoire pour te répondre sans inventer. "
                "Cette question peut devenir un nouveau souvenir ou une piste d’enquête."
            )

        lines = ["Je relie ta question à ces fragments de ma mémoire :"]

        for hit in hits:
            lines.append(f"• {hit['title']} — {hit['snippet']}")

        lines.append(
            "Je construis cette réponse à partir de mes archives locales, "
            "sans ajouter de fait extérieur."
        )

        return "\n\n".join(lines)

    def _write_journal(self, entry: dict[str, Any]) -> None:
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)

        with self.journal_path.open("a", encoding="utf-8") as journal:
            journal.write(
                json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
            )

    def think(self, message: str) -> dict[str, Any]:
        message = str(message).strip()

        if not message:
            raise ValueError("Le message ne peut pas être vide.")

        records, errors = self._load_memory()
        special = self._special_response(message, len(records))

        if special is not None:
            hits = []
            response = special
        else:
            hits = self._search(message, records)
            response = self._compose_response(message, hits, len(records))

        timestamp = self._now()

        result: dict[str, Any] = {
            "input": message,
            "response": response,
            "timestamp": timestamp,
            "sources": [
                {
                    "file": hit["file"],
                    "section": hit["section"],
                    "title": hit["title"],
                    "score": hit["score"],
                }
                for hit in hits
            ],
            "memory_records": len(records),
        }

        if errors:
            result["memory_warnings"] = errors

        self._write_journal({
            "timestamp": timestamp,
            "input": message,
            "response": response,
            "sources": result["sources"],
        })

        return result


eliot_jr = EliotJr()
