from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import json
import os
import re

import requests

from core.inference_engine import InferenceEngineError


class OpenAICompatibleInferenceEngine:
    """
    Moteur de lecture utilisant un endpoint HTTP compatible
    avec l'API Chat Completions d'OpenAI.

    Le fournisseur et le modèle restent explicitement attribués.
    Une erreur réseau produit une tentative sans réflexion plutôt
    qu'une fausse rencontre avec le passage.
    """

    engine_id = "openai_compatible_reading_engine"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        provider: str,
        model_id: str,
        model_version: str,
        timeout_seconds: int = 90,
        session: Any | None = None,
    ) -> None:
        self.base_url = str(base_url).strip().rstrip("/")
        self.api_key = str(api_key).strip()
        self.provider = str(provider).strip()
        self.model_id = str(model_id).strip()
        self.model_version = str(model_version).strip()
        self.timeout_seconds = int(timeout_seconds)
        self.session = session or requests.Session()

        required = {
            "base_url": self.base_url,
            "api_key": self.api_key,
            "provider": self.provider,
            "model_id": self.model_id,
            "model_version": self.model_version,
        }

        missing = [
            name
            for name, value in required.items()
            if not value
        ]

        if missing:
            raise InferenceEngineError(
                "Configuration du moteur incomplète : "
                + ", ".join(missing)
            )

        if not self.base_url.startswith(
            ("http://", "https://")
        ):
            raise InferenceEngineError(
                "L'URL du moteur doit utiliser HTTP ou HTTPS."
            )

        if self.timeout_seconds < 1:
            raise InferenceEngineError(
                "Le délai du moteur doit être positif."
            )

    @classmethod
    def from_environment(
        cls,
    ) -> "OpenAICompatibleInferenceEngine":
        """
        Construit le moteur sans exposer les secrets.

        Variables attendues :
        - READING_API_BASE_URL
        - READING_API_KEY
        - READING_PROVIDER
        - READING_MODEL_ID
        - READING_MODEL_VERSION
        - READING_API_TIMEOUT, facultative
        """
        timeout_raw = os.environ.get(
            "READING_API_TIMEOUT",
            "90",
        ).strip()

        try:
            timeout_seconds = int(timeout_raw)
        except ValueError as exc:
            raise InferenceEngineError(
                "READING_API_TIMEOUT doit être un entier."
            ) from exc

        return cls(
            base_url=os.environ.get(
                "READING_API_BASE_URL",
                "",
            ),
            api_key=os.environ.get(
                "READING_API_KEY",
                "",
            ),
            provider=os.environ.get(
                "READING_PROVIDER",
                "",
            ),
            model_id=os.environ.get(
                "READING_MODEL_ID",
                "",
            ),
            model_version=os.environ.get(
                "READING_MODEL_VERSION",
                "",
            ),
            timeout_seconds=timeout_seconds,
        )

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()

    @staticmethod
    def _parse_json_object(
        value: str,
    ) -> dict[str, Any]:
        text = str(value).strip()

        fenced = re.fullmatch(
            r"```(?:json)?\s*(.*?)\s*```",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )

        if fenced:
            text = fenced.group(1).strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise InferenceEngineError(
                "Le modèle n'a pas retourné un objet JSON valide."
            ) from exc

        if not isinstance(parsed, dict):
            raise InferenceEngineError(
                "La sortie du modèle doit être un objet JSON."
            )

        return parsed

    def _model_identity(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "version": self.model_version,
        }

    def _failed_result(
        self,
        request: dict[str, Any],
        message: str,
    ) -> dict[str, Any]:
        return {
            "status": "failed",
            "engine_id": self.engine_id,
            "model": self._model_identity(),
            "payload_sha256": request.get(
                "payload_sha256"
            ),
            "request_sha256": request.get(
                "request_sha256"
            ),
            "reflection_produced": False,
            "output": None,
            "message": message,
            "completed_at_utc": self._utc_now(),
        }

    def _build_messages(
        self,
        request: dict[str, Any],
    ) -> list[dict[str, str]]:
        passage = request.get("passage")
        instructions = request.get("instructions")
        work = request.get("work")
        before_reading = request.get(
            "before_reading"
        )

        if not isinstance(passage, dict):
            raise InferenceEngineError(
                "Le passage de lecture est absent."
            )

        if not isinstance(instructions, dict):
            raise InferenceEngineError(
                "Les instructions de lecture sont absentes."
            )

        passage_text = str(
            passage.get("text", "")
        ).strip()

        passage_hash = str(
            passage.get("passage_sha256", "")
        ).strip()

        if not passage_text or not passage_hash:
            raise InferenceEngineError(
                "Le texte ou son empreinte est absent."
            )

        expected_output = {
            "passage_sha256": passage_hash,
            "what_passage_says": (
                "Description fidèle de ce que dit "
                "explicitement le passage."
            ),
            "provisional_understanding": (
                "Compréhension provisoire, distincte "
                "du texte et révisable."
            ),
            "questions_or_objections": [
                "Au moins une question ou objection."
            ],
            "limits": [
                "Ce que ce passage seul ne permet "
                "pas de conclure."
            ],
        }

        reading_packet = {
            "task": "reading_encounter",
            "work": (
                work
                if isinstance(work, dict)
                else {}
            ),
            "before_reading": (
                before_reading
                if isinstance(
                    before_reading,
                    dict,
                )
                else {}
            ),
            "passage": passage,
            "instructions": instructions,
            "required_output": expected_output,
        }

        system_message = (
            "Tu participes à une rencontre de lecture "
            "attribuée et vérifiable. "
            "Tu ne dois pas prétendre à une expérience "
            "subjective ni inventer le contexte absent. "
            "Distingue strictement le texte, la compréhension "
            "provisoire, les objections et les limites. "
            "Réponds uniquement avec un objet JSON conforme "
            "au champ required_output. "
            "Toutes les formulations doivent rester "
            "provisoires et révisables."
        )

        return [
            {
                "role": "system",
                "content": system_message,
            },
            {
                "role": "user",
                "content": json.dumps(
                    reading_packet,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        ]

    def infer(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(request, dict):
            raise InferenceEngineError(
                "La requête d'inférence est invalide."
            )

        try:
            messages = self._build_messages(
                request
            )

            response = self.session.post(
                (
                    self.base_url
                    + "/chat/completions"
                ),
                headers={
                    "Authorization": (
                        f"Bearer {self.api_key}"
                    ),
                    "Content-Type": (
                        "application/json"
                    ),
                    "Accept": "application/json",
                },
                json={
                    "model": self.model_id,
                    "messages": messages,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": (
                                "reading_reflection"
                            ),
                            "strict": True,
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "passage_sha256": {
                                        "type": "string",
                                    },
                                    "what_passage_says": {
                                        "type": "string",
                                    },
                                    "provisional_understanding": {
                                        "type": "string",
                                    },
                                    "questions_or_objections": {
                                        "type": "array",
                                        "items": {
                                            "type": "string",
                                        },
                                        "minItems": 1,
                                    },
                                    "limits": {
                                        "type": "array",
                                        "items": {
                                            "type": "string",
                                        },
                                        "minItems": 1,
                                    },
                                },
                                "required": [
                                    "passage_sha256",
                                    "what_passage_says",
                                    (
                                        "provisional_"
                                        "understanding"
                                    ),
                                    (
                                        "questions_or_"
                                        "objections"
                                    ),
                                    "limits",
                                ],
                                "additionalProperties": False,
                            },
                        },
                    },
                },
                timeout=self.timeout_seconds,
            )

            response.raise_for_status()
            payload = response.json()

            choices = payload.get("choices")

            if (
                not isinstance(choices, list)
                or not choices
                or not isinstance(
                    choices[0],
                    dict,
                )
            ):
                raise InferenceEngineError(
                    "La réponse du fournisseur "
                    "ne contient aucun choix."
                )

            message = choices[0].get("message")

            if not isinstance(message, dict):
                raise InferenceEngineError(
                    "Le message du fournisseur "
                    "est invalide."
                )

            content = message.get("content")

            if not isinstance(content, str):
                raise InferenceEngineError(
                    "Le fournisseur n'a retourné "
                    "aucun contenu textuel."
                )

            output = self._parse_json_object(
                content
            )

            return {
                "status": "completed",
                "engine_id": self.engine_id,
                "model": self._model_identity(),
                "payload_sha256": request.get(
                    "payload_sha256"
                ),
                "request_sha256": request.get(
                    "request_sha256"
                ),
                "reflection_produced": True,
                "output": output,
                "message": (
                    "Réflexion attribuée produite "
                    "par le moteur configuré."
                ),
                "completed_at_utc": (
                    self._utc_now()
                ),
            }

        except (
            requests.RequestException,
            ValueError,
            TypeError,
            KeyError,
            InferenceEngineError,
        ) as exc:
            return self._failed_result(
                request,
                (
                    "Tentative d'inférence échouée : "
                    f"{type(exc).__name__}. "
                    "Aucune réflexion n'est déclarée."
                ),
            )
