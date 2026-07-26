from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.inference_engine import (
    InferenceEngine,
    build_reading_inference_request,
)
from core.inference_validation import (
    validate_inference_result,
)
from core.reading_journal import (
    record_validated_inference_result,
)
from core.reading_source import (
    build_reading_manifest,
)


class ReadingOrchestratorError(ValueError):
    """Erreur contrôlée du parcours de lecture."""


class ReadingOrchestrator:
    """
    Relie la source, le journal, le moteur et la validation.

    Par défaut, aucune donnée vivante n'est modifiée.
    L'écriture doit être demandée explicitement avec commit=True.
    """

    def __init__(
        self,
        project_root: Path,
        journals_root: Path,
        source_file: str,
    ) -> None:
        self.project_root = project_root.resolve()
        self.journals_root = journals_root.resolve()
        self.source_file = source_file

    def _journal_path(self, journal_id: str) -> Path:
        journal_id = str(journal_id).strip()

        if not journal_id:
            raise ReadingOrchestratorError(
                "L'identifiant du journal est vide."
            )

        if not all(
            character.isalnum() or character in {"_", "-"}
            for character in journal_id
        ):
            raise ReadingOrchestratorError(
                "L'identifiant du journal contient "
                "des caractères interdits."
            )

        path = (
            self.journals_root
            / f"{journal_id}.json"
        ).resolve()

        try:
            path.relative_to(self.journals_root)
        except ValueError as exc:
            raise ReadingOrchestratorError(
                "Le journal sort du répertoire autorisé."
            ) from exc

        if not path.is_file():
            raise ReadingOrchestratorError(
                f"Journal introuvable : {journal_id}"
            )

        return path

    def load_journal(
        self,
        journal_id: str,
    ) -> dict[str, Any]:
        path = self._journal_path(journal_id)

        try:
            value = json.loads(
                path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise ReadingOrchestratorError(
                f"Journal illisible : {journal_id}"
            ) from exc

        if not isinstance(value, dict):
            raise ReadingOrchestratorError(
                "Le journal doit contenir un objet JSON."
            )

        return value

    def prepare(
        self,
        journal_id: str,
        passage_id: str,
    ) -> tuple[
        dict[str, Any],
        dict[str, Any],
        list[str],
    ]:
        journal = self.load_journal(journal_id)

        manifest, warnings = build_reading_manifest(
            project_root=self.project_root,
            source_file=self.source_file,
        )

        request = build_reading_inference_request(
            journal=journal,
            manifest=manifest,
            passage_id=passage_id,
        )

        return request, manifest, warnings

    def run(
        self,
        journal_id: str,
        passage_id: str,
        engine: InferenceEngine,
        *,
        commit: bool = False,
        committed_by: str = "eliot_jr",
    ) -> dict[str, Any]:
        """
        Exécute une tentative de rencontre.

        commit=False :
            aucun journal n'est modifié.

        commit=True :
            le résultat validé est transmis à l'écriture atomique.
            Une absence de moteur reste une simple tentative.
        """
        if not hasattr(engine, "infer"):
            raise ReadingOrchestratorError(
                "Le moteur ne fournit pas de méthode infer."
            )

        request, manifest, warnings = self.prepare(
            journal_id=journal_id,
            passage_id=passage_id,
        )

        raw_result = engine.infer(request)

        validated_result = validate_inference_result(
            request=request,
            result=raw_result,
        )

        record_report: dict[str, Any] | None = None

        if commit:
            _, record_report = (
                record_validated_inference_result(
                    journals_root=self.journals_root,
                    journal_id=journal_id,
                    request=request,
                    validated_result=validated_result,
                    committed_by=committed_by,
                    commit=True,
                )
            )

        return {
            "schema_version": 1,
            "journal_id": journal_id,
            "passage_id": passage_id,
            "source_sha256": manifest["source_sha256"],
            "payload_sha256": request["payload_sha256"],
            "request_sha256": request["request_sha256"],
            "engine_id": validated_result["engine_id"],
            "status": validated_result["status"],
            "reflection_produced": validated_result[
                "reflection_produced"
            ],
            "result_sha256": validated_result[
                "result_sha256"
            ],
            "warnings": warnings,
            "commit_requested": commit,
            "record_report": record_report,
        }
