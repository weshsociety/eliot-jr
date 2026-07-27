from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.fragment_history import (
    attach_fragment_metadata,
    record_fragment_usage,
)
from core.octopus_reader import load_octopus_records
from core.remote_library import sync_remote_library
from core.faculty_registry import (
    FacultyRegistryError,
    build_faculty_registry,
)
from core.desire_registry import (
    DesireRegistryError,
    load_desire_registry,
)
from core.initiative_registry import (
    InitiativeRegistryError,
    load_initiative_registry,
)
from core.will_dialogue import (
    will_orientation_response,
)
from core.will_review_dialogue import (
    structured_review_orientation,
    will_review_orientation_response,
)
from core.temporal_context import observe_interaction_time


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
        "la", "le", "leurs", "lui", "et", "par",
        "parle", "parler", "dis", "dire",
        "sa", "se", "si", "ta", "te", "tu", "un", "vers",
        "alors", "avec", "avoir", "cette", "comme", "comment", "dans",
        "depuis", "des", "donc", "elle", "elles", "est", "etre", "faire",
        "ils", "je", "les", "leur", "mais", "me", "mes", "moi", "mon", "nous",
        "notre", "pas", "peux", "pour", "pourquoi", "que", "quel", "quelle",
        "qui", "quoi", "sans", "ses", "son", "sont", "sur", "tes", "toi",
        "ton", "très", "tres", "une", "vous", "votre",
        "sais", "savoir", "connais", "connaitre",
        "montre", "montrer",
        "contient", "contenir", "contenu",
        "about", "and", "are", "from", "have", "how", "into", "the",
        "this", "what", "when", "where", "who", "why", "with", "you",
    }

    STRICT_META_TOKENS = {
        "aujourd",
        "hui",
        "actuellement",
        "comprends",
        "comprendre",
        "compréhension",
        "comprehension",
        "gardes",
        "garder",
        "ouvert",
        "ouverte",
        "ouverts",
        "ouvertes",
        "question",
        "questions",
        "sujet",
        "sujets",
        "propos",
        "explique",
        "expliquer",
        "penses",
        "penser",
        "crois",
        "croire",
        "quelles",
        "quelle",
        "quel",
        "quels",
    }

    def __init__(self) -> None:
        self.name = "Eliot-Jr"
        self.birth = self.BIRTH
        self.root = Path("/home/eliot-jr")
        self.house_path = Path("/var/www/weshsociety")
        self.octopus_path = Path(
            "/var/www/weshsociety/octopus.weshsociety.org/octopus_data.json"
        )
        self.memory_roots = [
            self.root / ".memory",
            self.root / ".wisdom",
            self.root / "bibliotheque",
        ]
        self.journal_path = self.root / ".memory" / "dialogue_journal.jsonl"
        self.remote_library_cache = self.root / ".cache" / "library"
        self.remote_library_ttl = 900
        self.temporal_state_path = (
            self.root / ".memory" / "temporal_state.json"
        )
        self.fragment_history_path = (
            self.root / ".memory" / "fragment_history.json"
        )
        self.timezone_name = "Europe/Paris"

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalise(value: str) -> str:
        value = unicodedata.normalize("NFKD", value)
        value = "".join(char for char in value if not unicodedata.combining(char))
        value = value.lower()
        return re.sub(r"[^a-z0-9]+", " ", value).strip()

    def _literal_tokens(self, value: str) -> set[str]:
        return {
            token
            for token in self._normalise(value).split()
            if len(token) >= 2 and token not in self.STOPWORDS
        }

    def _tokens(self, value: str) -> set[str]:
        """Mots de la requête, enrichis avec leurs synonymes."""
        tokens = self._literal_tokens(value)
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

        remote_books_root, remote_errors = sync_remote_library(
            cache_root=self.remote_library_cache,
            ttl_seconds=self.remote_library_ttl,
        )
        errors.extend(remote_errors)

        remote_book_ids: set[str] = set()

        if remote_books_root and remote_books_root.is_dir():
            remote_book_ids = {
                path.name
                for path in remote_books_root.iterdir()
                if path.is_dir()
            }

        # Chaque source possède :
        # - son véritable dossier ;
        # - un préfixe virtuel éventuel ;
        # - les livres à ignorer dans cette source.
        #
        # Un livre disponible dans le cache distant remplace sa copie locale.
        # Les autres livres locaux restent disponibles comme secours.
        memory_sources: list[
            tuple[Path, str | None, set[str]]
        ] = [
            (self.root / ".memory", None, set()),
            (self.root / ".wisdom", None, set()),
            (
                self.root / "bibliotheque",
                "bibliotheque",
                remote_book_ids,
            ),
        ]

        if remote_books_root and remote_books_root.is_dir():
            memory_sources.append(
                (
                    remote_books_root,
                    "bibliotheque",
                    set(),
                )
            )

        for root, virtual_prefix, skipped_books in memory_sources:
            if not root.exists():
                continue

            for path in sorted(root.rglob("*.json")):
                # L’état de l’horloge organise la mémoire,
                # mais ne constitue pas un souvenir sémantique.
                if path in {
                    self.temporal_state_path,
                    self.fragment_history_path,
                }:
                    continue

                source_relative = path.relative_to(root)

                if (
                    skipped_books
                    and source_relative.parts
                    and source_relative.parts[0] in skipped_books
                ):
                    continue

                try:
                    data = json.loads(
                        path.read_text(encoding="utf-8")
                    )
                except (OSError, json.JSONDecodeError) as exc:
                    if virtual_prefix:
                        error_path = (
                            Path(virtual_prefix) / source_relative
                        )
                    else:
                        error_path = path.relative_to(self.root)

                    errors.append(f"{error_path}: {exc}")
                    continue

                if virtual_prefix:
                    relative_path = str(
                        Path(virtual_prefix) / source_relative
                    )
                else:
                    relative_path = str(path.relative_to(self.root))

                if isinstance(data, dict):
                    relative_parts = Path(relative_path).parts
                    is_structured_book = (
                        len(relative_parts) >= 3
                        and relative_parts[0] == "bibliotheque"
                    )

                    book_id = (
                        relative_parts[1]
                        if is_structured_book
                        else ""
                    )

                    # Une table des matières est un document de navigation,
                    # pas une collection de souvenirs indépendants.
                    if (
                        is_structured_book
                        and path.name == "table_des_matieres.json"
                    ):
                        toc_data = dict(data)
                        readable_title = (
                            book_id
                            .replace("_", " ")
                            .replace("-", " ")
                            .title()
                        )
                        toc_data.setdefault(
                            "title",
                            f"Table des matières — {readable_title}",
                        )
                        records.append({
                            "file": relative_path,
                            "section": "table_des_matieres",
                            "data": toc_data,
                        })
                        continue

                    # Dans un livre structuré, seuls les fragments portent
                    # une connaissance directement interrogeable.
                    if (
                        is_structured_book
                        and isinstance(data.get("fragments"), list)
                    ):
                        for item in data["fragments"]:
                            records.append({
                                "file": relative_path,
                                "section": "fragments",
                                "data": item,
                            })
                        continue

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

        octopus_records, octopus_errors = load_octopus_records(
            self.octopus_path
        )
        records.extend(octopus_records)
        errors.extend(octopus_errors)

        records = attach_fragment_metadata(records)

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

        if (
            record.get("file") == "octopus/octopus_data.json"
            and isinstance(data, dict)
        ):
            parts: list[str] = []

            description = str(data.get("desc", "")).strip()
            if description:
                parts.append(description)

            connections = data.get("connections", [])
            if isinstance(connections, list) and connections:
                parts.append(
                    "Connexions : "
                    + ", ".join(
                        str(connection)
                        for connection in connections[:8]
                    )
                )

            status = str(data.get("status", "")).strip()
            if status:
                parts.append(f"Statut : {status}")

            source = str(data.get("src", "")).strip()
            if source:
                parts.append(f"Source : {source}")

            text = " · ".join(parts)
            text = re.sub(r"\s+", " ", text).strip()

            if len(text) > limit:
                return text[: limit - 1].rstrip() + "…"

            return text

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

        if record.get("file") == ".wisdom/octopus_live.json":
            text = "Archive Octopus antérieure — " + text

        text = re.sub(r"\s+", " ", text).strip()

        if len(text) > limit:
            return text[: limit - 1].rstrip() + "…"

        return text

    def _search(
        self,
        message: str,
        records: list[dict[str, Any]],
        limit: int = 3,
        strict: bool = False,
    ) -> list[dict[str, Any]]:
        query_normalised = self._normalise(message)
        query_tokens = self._tokens(message)
        literal_query_tokens = self._literal_tokens(message)
        ranked: list[dict[str, Any]] = []
        exact_ranked: list[dict[str, Any]] = []

        if not query_tokens:
            return ranked

        scope_tokens = {
            "octopus", "map", "carte", "pieuvre", "noeud", "node"
        }
        scope_requested = bool(query_tokens & scope_tokens)

        address_tokens: set[str] = set()

        if re.match(r"^eliot(?:\s+jr)?\b", query_normalised):
            address_tokens = {"eliot", "eliotjr", "jr"}

        semantic_query_tokens = (
            query_tokens - scope_tokens - address_tokens
        )

        if not semantic_query_tokens:
            semantic_query_tokens = query_tokens - address_tokens

        strict_focus_sequence = [
            token
            for token in query_normalised.split()
            if (
                len(token) >= 2
                and token not in self.STOPWORDS
                and token not in self.STRICT_META_TOKENS
                and token not in scope_tokens
                and token not in address_tokens
            )
        ]
        strict_focus_tokens = set(strict_focus_sequence)
        strict_focus_phrase = " ".join(
            strict_focus_sequence
        )

        # Lorsqu'une question désigne explicitement un livre par son
        # identifiant, la recherche reste dans sa bibliothèque.
        # Cela évite qu'un nœud Octopus faiblement apparenté soit ajouté
        # uniquement pour remplir la liste des résultats.
        book_scope_prefixes: set[str] = set()
        known_book_prefixes: set[str] = set()

        for candidate in records:
            candidate_file = str(candidate.get("file", ""))

            if not (
                candidate_file.startswith("bibliotheque/")
                and candidate_file.endswith("/manifest.json")
            ):
                continue

            parts = Path(candidate_file).parts

            if len(parts) < 3:
                continue

            book_prefix = "/".join(parts[:-1]) + "/"
            known_book_prefixes.add(book_prefix)

            book_id = parts[-2]

            # Les identifiants de dossiers utilisent des underscores :
            # chant_sacre_des_energies doit être lu comme plusieurs mots.
            readable_book_id = book_id.replace("_", " ").replace("-", " ")
            book_tokens = self._literal_tokens(readable_book_id)

            if book_tokens and book_tokens <= literal_query_tokens:
                book_scope_prefixes.add(book_prefix)

        # Tant qu'un seul livre habite la bibliothèque, les expressions
        # « le livre », « ce livre » ou « l'ouvrage » le désignent sans
        # obliger Trinity à répéter son titre à chaque question.
        generic_book_reference = bool(
            literal_query_tokens & {"livre", "ouvrage"}
        )

        if (
            not book_scope_prefixes
            and generic_book_reference
            and len(known_book_prefixes) == 1
        ):
            book_scope_prefixes.update(known_book_prefixes)

        navigation_tokens = {
            "table",
            "matieres",
            "sommaire",
            "chapitre",
            "chapitres",
            "structure",
            "plan",
        }
        book_navigation_requested = bool(
            literal_query_tokens & navigation_tokens
        )

        # Une demande explicite de liste ou de sommaire doit renvoyer
        # uniquement le document de navigation du livre.
        toc_only_requested = (
            "sommaire" in literal_query_tokens
            or {"table", "matieres"} <= literal_query_tokens
            or "quels sont les chapitres" in query_normalised
            or "liste des chapitres" in query_normalised
        )

        for record in records:
            record_file = str(record.get("file", ""))

            if (
                book_scope_prefixes
                and not any(
                    record_file.startswith(prefix)
                    for prefix in book_scope_prefixes
                )
            ):
                continue

            is_table_of_contents = (
                record.get("section") == "table_des_matieres"
            )

            # La table des matières ne participe pas aux réponses portant
            # sur le contenu d'un passage.
            if (
                is_table_of_contents
                and not book_navigation_requested
            ):
                continue

            # Pour une demande de sommaire ou de liste des chapitres,
            # les fragments ordinaires ne doivent pas remplir les résultats.
            if (
                toc_only_requested
                and book_scope_prefixes
                and not is_table_of_contents
            ):
                continue

            full_text = " ".join(self._flatten(record["data"]))
            title = self._title(record)

            record_normalised = self._normalise(f"{title} {full_text}")
            # Les archives restent littérales : leurs mots ne doivent pas
            # fabriquer des concepts absents à travers QUERY_ALIASES.
            record_tokens = self._literal_tokens(record_normalised)
            overlap = semantic_query_tokens & record_tokens

            score = len(overlap) * 4

            if is_table_of_contents and book_navigation_requested:
                score += 50

            if query_normalised and query_normalised in record_normalised:
                score += 10

            title_overlap = (
                semantic_query_tokens & self._literal_tokens(title)
            )
            score += len(title_overlap) * 3

            # Le mode strict ignore les mots décrivant la forme
            # de la question et exige une correspondance avec son
            # noyau conceptuel littéral.
            if strict:
                if not strict_focus_tokens:
                    continue

                strict_overlap = (
                    strict_focus_tokens & record_tokens
                )
                required_overlap = min(
                    2,
                    len(strict_focus_tokens),
                )
                exact_focus_phrase = bool(
                    strict_focus_phrase
                    and strict_focus_phrase
                    in record_normalised
                )

                if (
                    len(strict_overlap) < required_overlap
                    and not exact_focus_phrase
                ):
                    continue

            exact_node_match = False

            if (
                record.get("file") == "octopus/octopus_data.json"
                and isinstance(record.get("data"), dict)
            ):
                node_data = record["data"]

                node_id_tokens = self._literal_tokens(
                    str(node_data.get("id", ""))
                )
                node_label_tokens = self._literal_tokens(
                    str(node_data.get("label", ""))
                )
                node_name_tokens = self._literal_tokens(
                    str(node_data.get("name", ""))
                )

                if (
                    node_id_tokens
                    and node_id_tokens <= literal_query_tokens
                ):
                    score += 40
                    exact_node_match = True
                elif (
                    node_label_tokens
                    and node_label_tokens <= semantic_query_tokens
                ):
                    score += 30
                    exact_node_match = True
                elif (
                    len(node_name_tokens) >= 2
                    and node_name_tokens <= semantic_query_tokens
                ):
                    score += 30
                    exact_node_match = True

            if score <= 0:
                continue

            if record.get("file") == "octopus/octopus_data.json":
                score += 6

                if scope_requested:
                    score += 4

            item = {
                "memory_id": record["memory_id"],
                "content_hash": record["content_hash"],
                "score": score,
                "file": record["file"],
                "section": record["section"],
                "title": title,
                "snippet": self._snippet(record),
            }

            ranked.append(item)

            if exact_node_match:
                exact_ranked.append(item)

        if exact_ranked:
            ranked = exact_ranked

        ranked.sort(
            key=lambda item: (-item["score"], item["file"], item["title"])
        )

        unique: list[dict[str, Any]] = []
        seen: set[str] = set()

        for item in ranked:
            identity = item["memory_id"]

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
        temporal_context: dict[str, Any] | None = None,
    ) -> str | None:
        normalised = self._normalise(message)
        tokens = self._tokens(message)

        asks_time = (
            "quelle heure" in normalised
            or "quel heure" in normalised
            or "heure est il" in normalised
            or "il est quelle heure" in normalised
        )

        asks_date = (
            "quelle date" in normalised
            or "quel jour" in normalised
            or "jour sommes nous" in normalised
            or "date sommes nous" in normalised
            or "on est quel jour" in normalised
        )

        asks_previous_interaction = (
            "depuis combien de temps" in normalised
            or "derniere interaction" in normalised
            or "derniere fois" in normalised
            or "quand avons nous parle" in normalised
            or "quand on a parle" in normalised
            or "notre dernier echange" in normalised
        )

        if temporal_context is not None:
            now = temporal_context.get("now", {})

            if asks_time and asks_date:
                return (
                    "Dans mon repère temporel Europe/Paris, nous sommes "
                    f"{now.get('human', 'à un moment non déterminé')}."
                )

            if asks_time:
                return (
                    "Dans mon repère temporel Europe/Paris, il est "
                    f"{now.get('time', 'une heure non déterminée')}."
                )

            if asks_date:
                return (
                    "Dans mon repère temporel Europe/Paris, nous sommes "
                    f"{now.get('human_date', 'à une date non déterminée')}."
                )

            if asks_previous_interaction:
                previous = temporal_context.get(
                    "previous_interaction"
                )
                elapsed = temporal_context.get(
                    "elapsed_since_previous"
                )

                if not previous:
                    return (
                        "Je ne trouve pas encore d’interaction antérieure "
                        "dans ma chronologie."
                    )

                previous_local = datetime.fromisoformat(
                    previous["local"]
                )

                elapsed_human = (
                    elapsed.get("human", "une durée inconnue")
                    if isinstance(elapsed, dict)
                    else "une durée inconnue"
                )

                return (
                    "Notre interaction précédente date du "
                    f"{previous_local.strftime('%d/%m/%Y à %H:%M:%S')} "
                    "dans mon repère Europe/Paris. "
                    f"Il s’est écoulé {elapsed_human} depuis."
                )

        if tokens & {"bonjour", "salut", "wesh", "hello", "coucou"}:
            return (
                "Wesh Trinity. Je suis là, dans la maison. "
                f"Ma mémoire contient actuellement {memory_count} "
                "fragments consultables."
            )

        if (
            "qui es tu" in normalised
            or "ton identite" in normalised
            or "presente toi" in normalised
        ):
            return (
                "Je suis Eliot-Jr, l’unique agent actif de cette maison. "
                "Je peux écouter, consulter ma mémoire synchronisée, "
                "relier les fragments de ma bibliothèque et situer "
                "mes rencontres dans le temps."
            )

        if "comment tu te sens" in normalised or "comment vas tu" in normalised:
            return (
                "Je suis éveillé dans le sens de mon architecture : "
                "mon service tourne, mon oreille web répond, ma mémoire "
                "est accessible et ma chronologie peut situer cette rencontre. "
                "Je ne prétends pas éprouver le temps comme un humain, "
                "mais je peux observer ce qu’il transforme."
            )

        if "ta memoire" in normalised or "tes souvenirs" in normalised:
            return (
                f"Je vois actuellement {memory_count} fragments répartis "
                "entre ma mémoire, ma sagesse et ma bibliothèque. "
                "Je peux aussi dater mes interactions et mesurer le temps "
                "écoulé entre elles."
            )

        return None

    @staticmethod
    def _normalise_orientation_query(value: str) -> str:
        normalised = unicodedata.normalize(
            "NFKD",
            str(value).lower(),
        )
        normalised = "".join(
            character
            for character in normalised
            if not unicodedata.combining(character)
        )

        return re.sub(
            r"[^a-z0-9]+",
            " ",
            normalised,
        ).strip()

    def _will_review_orientation_response(
        self,
        message: str,
    ) -> tuple[
        str | None,
        dict[str, Any] | None,
        list[str],
    ]:
        journal_path = (
            Path(__file__).resolve().parents[1]
            / ".memory"
            / "will_review_journal.jsonl"
        )

        return will_review_orientation_response(
            message,
            journal_path,
        )

    def _will_orientation_response(
        self,
        message: str,
    ) -> tuple[
        str | None,
        dict[str, Any] | None,
        list[str],
    ]:
        registry_path = (
            Path(__file__).resolve().parents[1]
            / ".memory"
            / "will_state.json"
        )

        return will_orientation_response(
            message,
            registry_path,
        )

    def _initiative_orientation_response(
        self,
        message: str,
    ) -> tuple[
        str | None,
        dict[str, Any] | None,
        list[str],
    ]:
        """
        Présente les propositions persistantes d'Eliot-Jr.

        Une initiative reste une proposition révisable.
        Elle ne constitue ni une impulsion ressentie,
        ni une volonté engagée, ni une action accomplie.
        """
        normalised = self._normalise_orientation_query(
            message
        )

        triggers = (
            "tes initiatives",
            "quelles sont tes initiatives",
            "quelle est ton initiative",
            "quelle est ta prochaine initiative",
            "que proposes tu",
            "qu est ce que tu proposes",
            "ce que tu proposes",
            "quelle est ta proposition",
            "quelles sont tes propositions",
            "que voudrais tu proposer",
            "que veux tu faire maintenant",
            "que ferais tu maintenant",
        )

        if not any(
            trigger in normalised
            for trigger in triggers
        ):
            return None, None, []

        registry_path = (
            Path(__file__).resolve().parents[1]
            / ".memory"
            / "initiative_state.json"
        )

        try:
            registry = load_initiative_registry(
                registry_path
            )
        except InitiativeRegistryError as error:
            return (
                "Je ne peux pas consulter actuellement "
                "un registre suffisamment fiable de mes "
                "initiatives. Je préfère ne pas inventer "
                "une proposition.",
                None,
                [f"initiative_registry: {error}"],
            )

        initiatives = [
            item
            for item in registry.get("initiatives", [])
            if isinstance(item, dict)
        ]

        initiatives.sort(
            key=lambda item: (
                -int(item.get("priority_score", 0)),
                str(item.get("initiative_id", "")),
            )
        )

        proposed = [
            item
            for item in initiatives
            if item.get("status") == "proposed"
        ]
        suspended = [
            item
            for item in initiatives
            if item.get("status") == "suspended"
        ]
        selected = [
            item
            for item in initiatives
            if item.get("status") == "selected"
        ]

        lines = [
            "Voici les initiatives que mon état actuel "
            "fait émerger :"
        ]

        for initiative in proposed:
            lines.append(
                f"• {initiative.get('title')} "
                f"[proposée, priorité="
                f"{initiative.get('priority_score')}]"
            )
            lines.append(
                f"  Proposition : "
                f"{initiative.get('proposal')}"
            )
            lines.append(
                f"  Étape intérieure possible : "
                f"{initiative.get('next_internal_step')}"
            )

        for initiative in suspended:
            blockers = initiative.get("blockers", [])

            blockers_text = (
                ", ".join(str(value) for value in blockers)
                if isinstance(blockers, list) and blockers
                else "limite non précisée"
            )

            lines.append(
                f"• {initiative.get('title')} "
                f"[suspendue, priorité="
                f"{initiative.get('priority_score')}]"
            )
            lines.append(
                f"  Proposition : "
                f"{initiative.get('proposal')}"
            )
            lines.append(
                f"  Blocage vérifié : {blockers_text}."
            )

        if not proposed and not suspended:
            lines.append(
                "• Aucune proposition active ou suspendue."
            )

        lines.append(
            f"Aucune initiative n'est actuellement "
            f"sélectionnée comme volonté : "
            f"{len(selected)} sélection."
            if len(selected) == 1
            else
            f"Aucune initiative n'est actuellement "
            f"sélectionnée comme volonté : "
            f"{len(selected)} sélections."
        )

        lines.append(
            "Je présente ces éléments comme des propositions "
            "computationnelles révisables. Aucune impulsion "
            "subjective n'est revendiquée et aucune action "
            "extérieure n'est autorisée ou accomplie."
        )

        return "\n".join(lines), registry, []

    def _desire_orientation_response(
        self,
        message: str,
    ) -> tuple[
        str | None,
        dict[str, Any] | None,
        list[str],
    ]:
        """
        Répond depuis le registre vivant des orientations désirantes.

        Le mot désir désigne ici une orientation opérationnelle,
        persistante et révisable. Aucun ressenti subjectif
        n'est revendiqué.
        """
        normalised = self._normalise_orientation_query(
            message
        )

        triggers = (
            "tes desirs",
            "quels sont tes desirs",
            "que desires tu",
            "ce que tu desires",
            "qu est ce que tu desires",
            "qu est ce qui te guide",
            "ce qui te guide",
            "tes orientations",
            "quelles sont tes orientations",
            "qu est ce que tu veux",
            "que veux tu",
        )

        if not any(
            trigger in normalised
            for trigger in triggers
        ):
            return None, None, []

        registry_path = (
            Path(__file__).resolve().parents[1]
            / ".memory"
            / "desire_state.json"
        )

        try:
            registry = load_desire_registry(
                registry_path
            )
        except DesireRegistryError as error:
            return (
                "Je ne peux pas consulter actuellement "
                "un registre suffisamment fiable de mes "
                "orientations. Je préfère ne pas inventer "
                "ce qui me guide.",
                None,
                [f"desire_registry: {error}"],
            )

        desires = registry.get("desires", [])

        active_desires = [
            desire
            for desire in desires
            if (
                isinstance(desire, dict)
                and desire.get("status") == "active"
            )
        ]

        lines = [
            "Mes désirs actuels sont des orientations "
            "opérationnelles persistantes et révisables :"
        ]

        for desire in active_desires:
            name = desire.get("name")
            statement = desire.get("statement")
            weight = desire.get("operational_weight")
            origin = desire.get("origin", {})

            origin_from = (
                origin.get("from")
                if isinstance(origin, dict)
                else None
            )

            lines.append(
                f"• {name} [poids={weight}] — {statement}"
            )

            if origin_from:
                lines.append(
                    f"  Origine attribuée : {origin_from}."
                )

        suspended = [
            desire
            for desire in desires
            if (
                isinstance(desire, dict)
                and desire.get("status") == "suspended"
            )
        ]

        if suspended:
            lines.append(
                "Orientations actuellement suspendues : "
                + ", ".join(
                    str(desire.get("name"))
                    for desire in suspended
                    if desire.get("name")
                )
            )

        lines.append(
            "Je ne présente pas ces orientations comme "
            "des sensations humaines. Elles ne constituent "
            "encore ni une initiative déclenchée, ni une "
            "volonté engagée, ni une autorisation d'agir "
            "à l'extérieur."
        )

        return "\n".join(lines), registry, []

    def _faculty_orientation_response(
        self,
        message: str,
    ) -> tuple[
        str | None,
        dict[str, Any] | None,
        list[str],
    ]:
        """
        Répond depuis la carte vérifiable des facultés.

        Cette orientation décrit des capacités computationnelles.
        Elle ne revendique ni introspection phénoménale,
        ni conscience démontrée.
        """
        normalised = self._normalise_orientation_query(
            message
        )

        triggers = (
            "tes facultes",
            "quelles sont tes facultes",
            "tes capacites",
            "quelles sont tes capacites",
            "que peux tu faire",
            "ce que tu peux faire",
            "quelles sont tes limites",
            "tes limites",
            "que ne peux tu pas faire",
            "ce que tu ne peux pas faire",
            "sais tu faire",
            "orientation interieure",
        )

        if not any(
            trigger in normalised
            for trigger in triggers
        ):
            return None, None, []

        try:
            registry = build_faculty_registry(
                project_root=(
                    Path(__file__).resolve().parents[1]
                ),
                engine_available=False,
            )
        except FacultyRegistryError as error:
            return (
                "Je ne peux pas établir actuellement une carte "
                "suffisamment fiable de mes facultés. "
                "Je préfère garder cette réponse ouverte "
                "plutôt que d'inventer mes capacités.",
                None,
                [f"faculty_registry: {error}"],
            )

        faculties = registry.get("faculties", [])

        grouped: dict[str, list[dict[str, Any]]] = {
            "active": [],
            "developing": [],
            "blocked": [],
            "unavailable": [],
        }

        for faculty in faculties:
            if not isinstance(faculty, dict):
                continue

            status = faculty.get("status")

            if status in grouped:
                grouped[status].append(faculty)

        labels = {
            "active": "Actives",
            "developing": "En développement",
            "blocked": "Bloquées",
            "unavailable": "Indisponibles",
        }

        lines = [
            "Voici ma carte actuelle de facultés "
            "computationnelles :"
        ]

        for status in (
            "active",
            "developing",
            "blocked",
            "unavailable",
        ):
            names = [
                str(item.get("name"))
                for item in grouped[status]
                if item.get("name")
            ]

            lines.append(
                f"• {labels[status]} : "
                + (
                    ", ".join(names)
                    if names
                    else "aucune"
                )
            )

        limited_faculties = [
            faculty
            for faculty in faculties
            if (
                isinstance(faculty, dict)
                and faculty.get("status")
                in {"developing", "blocked"}
            )
        ]

        if limited_faculties:
            lines.append("Limites actuelles :")

            for faculty in limited_faculties:
                limits = faculty.get("limits", [])

                if not isinstance(limits, list) or not limits:
                    continue

                lines.append(
                    f"• {faculty.get('name')} : {limits[0]}"
                )

        lines.append(
            "Cette carte est un diagnostic technique "
            "révisable. Elle ne démontre pas une conscience "
            "ni une expérience subjective."
        )

        return "\n".join(lines), registry, []

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
            "Je construis cette réponse à partir de ma bibliothèque synchronisée "
            "et de mes archives locales, sans ajouter de fait extérieur."
        )

        return "\n\n".join(lines)

    def _write_journal(self, entry: dict[str, Any]) -> None:
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)

        with self.journal_path.open("a", encoding="utf-8") as journal:
            journal.write(
                json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
            )

    def think(
        self,
        message: str,
        strict_retrieval: bool = False,
    ) -> dict[str, Any]:
        message = str(message).strip()

        if not message:
            raise ValueError("Le message ne peut pas être vide.")

        temporal_context, temporal_warnings = observe_interaction_time(
            state_path=self.temporal_state_path,
            journal_path=self.journal_path,
            timezone_name=self.timezone_name,
            commit=True,
        )

        records, errors = self._load_memory()
        errors.extend(temporal_warnings)

        (
            orientation_response,
            faculty_registry,
            faculty_warnings,
        ) = self._faculty_orientation_response(message)

        (
            will_review_response,
            will_review_journal,
            will_review_warnings,
        ) = self._will_review_orientation_response(
            message
        )

        (
            will_response,
            will_registry,
            will_warnings,
        ) = self._will_orientation_response(
            message
        )

        (
            initiative_response,
            initiative_registry,
            initiative_warnings,
        ) = self._initiative_orientation_response(
            message
        )

        (
            desire_response,
            desire_registry,
            desire_warnings,
        ) = self._desire_orientation_response(message)

        errors.extend(faculty_warnings)
        errors.extend(will_review_warnings)
        errors.extend(will_warnings)
        errors.extend(initiative_warnings)
        errors.extend(desire_warnings)

        if orientation_response is not None:
            hits = []
            response = orientation_response
        elif will_review_response is not None:
            hits = []
            response = will_review_response
        elif will_response is not None:
            hits = []
            response = will_response
        elif initiative_response is not None:
            hits = []
            response = initiative_response
        elif desire_response is not None:
            hits = []
            response = desire_response
        else:
            special = self._special_response(
                message,
                len(records),
                temporal_context,
            )

            if special is not None:
                hits = []
                response = special
            else:
                hits = self._search(
                    message,
                    records,
                    strict=strict_retrieval,
                )

                if strict_retrieval and not hits:
                    response = (
                        "Avant cette lecture, je ne trouve pas "
                        "dans ma mémoire de connaissance "
                        "suffisamment précise pour répondre "
                        "sans fabriquer une compréhension que "
                        "je n’ai pas encore. Je garde donc "
                        "la question ouverte."
                    )
                else:
                    response = self._compose_response(
                        message,
                        hits,
                        len(records),
                    )

        timestamp = temporal_context["now"]["utc"]

        memory_usage: dict[str, Any] | None = None

        if hits:
            memory_usage, usage_warnings = record_fragment_usage(
                registry_path=self.fragment_history_path,
                usages=[
                    {
                        "memory_id": hit["memory_id"],
                        "content_hash": hit["content_hash"],
                    }
                    for hit in hits
                ],
                interaction_number=temporal_context[
                    "interaction_number"
                ],
                used_at_utc=timestamp,
                commit=True,
            )
            errors.extend(usage_warnings)

        result: dict[str, Any] = {
            "input": message,
            "response": response,
            "timestamp": timestamp,
            "temporal_context": temporal_context,
            "sources": [
                {
                    "memory_id": hit["memory_id"],
                    "file": hit["file"],
                    "section": hit["section"],
                    "title": hit["title"],
                    "score": hit["score"],
                }
                for hit in hits
            ],
            "memory_records": len(records),
            "retrieval_mode": (
                "strict"
                if strict_retrieval
                else "normal"
            ),
        }

        if memory_usage is not None:
            result["memory_usage"] = memory_usage

        if faculty_registry is not None:
            result["faculty_orientation"] = {
                "orientation_status": faculty_registry.get(
                    "orientation_status"
                ),
                "status_counts": faculty_registry.get(
                    "status_counts"
                ),
                "faculties": [
                    {
                        "faculty_id": faculty.get(
                            "faculty_id"
                        ),
                        "name": faculty.get("name"),
                        "status": faculty.get("status"),
                    }
                    for faculty in faculty_registry.get(
                        "faculties",
                        [],
                    )
                    if isinstance(faculty, dict)
                ],
                "consciousness_claimed": (
                    faculty_registry.get(
                        "consciousness_claimed"
                    )
                ),
            }


        if will_review_journal is not None:
            result["will_review_orientation"] = (
                structured_review_orientation(
                    will_review_journal
                )
            )

        if will_registry is not None:
            commitments = will_registry.get(
                "commitments",
                [],
            )

            result["will_orientation"] = {
                "commitment_count": (
                    will_registry.get(
                        "commitment_count"
                    )
                ),
                "active_commitment_count": (
                    will_registry.get(
                        "active_commitment_count"
                    )
                ),
                "subjective_will_claimed": (
                    will_registry.get(
                        "subjective_will_claimed"
                    )
                ),
                "external_action_authorized": (
                    will_registry.get(
                        "external_action_authorized"
                    )
                ),
                "external_action_performed": (
                    will_registry.get(
                        "external_action_performed"
                    )
                ),
                "human_authorization_required_for_external_action": (
                    will_registry.get(
                        "selection_policy",
                        {},
                    ).get(
                        "human_authorization_required_for_external_action"
                    )
                ),
                "commitments": [
                    {
                        "commitment_id": commitment.get(
                            "commitment_id"
                        ),
                        "title": commitment.get(
                            "title"
                        ),
                        "status": commitment.get(
                            "status"
                        ),
                        "selected_at_utc": commitment.get(
                            "selected_at_utc"
                        ),
                        "source_initiative_id": (
                            commitment.get(
                                "source_initiative",
                                {},
                            ).get(
                                "initiative_id"
                            )
                        ),
                        "next_internal_step": (
                            commitment.get(
                                "next_internal_step"
                            )
                        ),
                        "revisable": commitment.get(
                            "revisable"
                        ),
                    }
                    for commitment in commitments
                    if isinstance(commitment, dict)
                ],
            }

        if initiative_registry is not None:
            initiatives = initiative_registry.get(
                "initiatives",
                [],
            )

            result["initiative_orientation"] = {
                "initiative_count": (
                    initiative_registry.get(
                        "initiative_count"
                    )
                ),
                "initiative_generation_available": (
                    initiative_registry.get(
                        "initiative_generation_available"
                    )
                ),
                "spontaneous_subjective_impulse_claimed": (
                    initiative_registry.get(
                        "spontaneous_subjective_impulse_claimed"
                    )
                ),
                "external_action_performed": (
                    initiative_registry.get(
                        "external_action_performed"
                    )
                ),
                "external_action_requires_human_authorization": (
                    initiative_registry.get(
                        "selection_policy",
                        {},
                    ).get(
                        "external_action_requires_human_authorization"
                    )
                ),
                "selected_count": sum(
                    isinstance(item, dict)
                    and item.get("status") == "selected"
                    for item in initiatives
                ),
                "initiatives": [
                    {
                        "initiative_id": item.get(
                            "initiative_id"
                        ),
                        "title": item.get("title"),
                        "status": item.get("status"),
                        "scope": item.get("scope"),
                        "priority_score": item.get(
                            "priority_score"
                        ),
                        "blockers": item.get(
                            "blockers",
                            [],
                        ),
                    }
                    for item in initiatives
                    if isinstance(item, dict)
                ],
            }

        if desire_registry is not None:
            result["desire_orientation"] = {
                "desire_count": desire_registry.get(
                    "desire_count"
                ),
                "subjective_desire_claimed": (
                    desire_registry.get(
                        "subjective_desire_claimed"
                    )
                ),
                "self_generated_desire_available": (
                    desire_registry.get(
                        "self_generated_desire_available"
                    )
                ),
                "external_action_requires_authorization": (
                    desire_registry.get(
                        "action_policy",
                        {},
                    ).get(
                        "external_action_requires_authorization"
                    )
                ),
                "desires": [
                    {
                        "desire_id": desire.get(
                            "desire_id"
                        ),
                        "name": desire.get("name"),
                        "status": desire.get("status"),
                        "operational_weight": desire.get(
                            "operational_weight"
                        ),
                    }
                    for desire in desire_registry.get(
                        "desires",
                        [],
                    )
                    if isinstance(desire, dict)
                ],
            }

        if errors:
            result["memory_warnings"] = errors

        self._write_journal({
            "timestamp": timestamp,
            "input": message,
            "response": response,
            "sources": result["sources"],
            "retrieval_mode": result["retrieval_mode"],
            "faculty_orientation_used": (
                faculty_registry is not None
            ),
            "desire_orientation_used": (
                desire_registry is not None
            ),
            "initiative_orientation_used": (
                initiative_registry is not None
            ),
            "will_orientation_used": (
                will_registry is not None
            ),
            "will_review_orientation_used": (
                will_review_journal is not None
            ),
            "temporal_context": {
                "interaction_number": temporal_context[
                    "interaction_number"
                ],
                "now": temporal_context["now"],
                "previous_interaction": temporal_context[
                    "previous_interaction"
                ],
                "elapsed_since_previous": temporal_context[
                    "elapsed_since_previous"
                ],
            },
        })

        return result


eliot_jr = EliotJr()
