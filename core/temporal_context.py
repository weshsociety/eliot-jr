from __future__ import annotations

import fcntl
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


DEFAULT_TIMEZONE = "Europe/Paris"

WEEKDAYS_FR = [
    "lundi",
    "mardi",
    "mercredi",
    "jeudi",
    "vendredi",
    "samedi",
    "dimanche",
]

MONTHS_FR = [
    "",
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
]


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None

    try:
        parsed = datetime.fromisoformat(
            value.strip().replace("Z", "+00:00")
        )
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _journal_history(
    journal_path: Path,
) -> tuple[datetime | None, datetime | None, int, list[str]]:
    first: datetime | None = None
    last: datetime | None = None
    count = 0
    warnings: list[str] = []

    if not journal_path.is_file():
        return first, last, count, warnings

    try:
        lines = journal_path.read_text(
            encoding="utf-8"
        ).splitlines()
    except OSError as exc:
        return first, last, count, [
            f"Journal temporel illisible : {exc}"
        ]

    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue

        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            warnings.append(
                f"Entrée de journal invalide à la ligne {line_number}."
            )
            continue

        timestamp = _parse_datetime(entry.get("timestamp"))

        if timestamp is None:
            warnings.append(
                f"Timestamp absent ou invalide à la ligne {line_number}."
            )
            continue

        count += 1

        if first is None or timestamp < first:
            first = timestamp

        if last is None or timestamp > last:
            last = timestamp

    return first, last, count, warnings


def _format_duration(total_seconds: int) -> str:
    total_seconds = max(0, int(total_seconds))

    days, remainder = divmod(total_seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, seconds = divmod(remainder, 60)

    parts: list[str] = []

    if days:
        parts.append(f"{days} jour" + ("s" if days > 1 else ""))

    if hours:
        parts.append(f"{hours} heure" + ("s" if hours > 1 else ""))

    if minutes:
        parts.append(
            f"{minutes} minute" + ("s" if minutes > 1 else "")
        )

    if not parts:
        parts.append(
            f"{seconds} seconde" + ("s" if seconds != 1 else "")
        )

    return ", ".join(parts[:3])


def _read_state(path: Path) -> tuple[dict[str, Any], list[str]]:
    if not path.is_file():
        return {}, []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"État temporel illisible : {exc}"]

    if not isinstance(data, dict):
        return {}, ["L’état temporel n’est pas un objet JSON."]

    return data, []


def _write_state_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=path.parent,
    )

    try:
        with os.fdopen(
            file_descriptor,
            "w",
            encoding="utf-8",
        ) as temporary:
            json.dump(
                data,
                temporary,
                ensure_ascii=False,
                indent=2,
            )
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())

        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)

    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def observe_interaction_time(
    state_path: Path,
    journal_path: Path,
    timezone_name: str = DEFAULT_TIMEZONE,
    now: datetime | None = None,
    commit: bool = True,
) -> tuple[dict[str, Any], list[str]]:
    """
    Situe une interaction dans la chronologie d’Eliot.

    Si aucun état temporel n’existe encore, le journal historique sert
    à retrouver la première et la dernière interaction connues.
    """
    zone = ZoneInfo(timezone_name)

    current_utc = now or datetime.now(timezone.utc)

    if current_utc.tzinfo is None:
        current_utc = current_utc.replace(tzinfo=timezone.utc)

    current_utc = current_utc.astimezone(timezone.utc)
    current_local = current_utc.astimezone(zone)

    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")

    warnings: list[str] = []

    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)

        state, state_warnings = _read_state(state_path)
        warnings.extend(state_warnings)

        journal_first, journal_last, journal_count, journal_warnings = (
            _journal_history(journal_path)
        )
        warnings.extend(journal_warnings)

        stored_first = _parse_datetime(
            state.get("first_interaction_at_utc")
        )
        stored_last = _parse_datetime(
            state.get("last_interaction_at_utc")
        )

        first_interaction = stored_first or journal_first or current_utc
        previous_interaction = stored_last or journal_last

        stored_count = state.get("interaction_count")

        if isinstance(stored_count, int) and stored_count >= 0:
            previous_count = stored_count
            state_source = "temporal_state"
        else:
            previous_count = journal_count
            state_source = (
                "dialogue_journal"
                if journal_count
                else "new_chronology"
            )

        elapsed_seconds: int | None = None

        if previous_interaction is not None:
            elapsed_seconds = max(
                0,
                int(
                    (
                        current_utc - previous_interaction
                    ).total_seconds()
                ),
            )

        interaction_number = previous_count + 1

        context: dict[str, Any] = {
            "timezone": timezone_name,
            "state_source": state_source,
            "interaction_number": interaction_number,
            "now": {
                "utc": current_utc.isoformat(),
                "local": current_local.isoformat(),
                "date": current_local.date().isoformat(),
                "time": current_local.strftime("%H:%M:%S"),
                "weekday": WEEKDAYS_FR[current_local.weekday()],
                "human_date": (
                    f"{WEEKDAYS_FR[current_local.weekday()]} "
                    f"{current_local.day} "
                    f"{MONTHS_FR[current_local.month]} "
                    f"{current_local.year}"
                ),
                "human": (
                    f"{WEEKDAYS_FR[current_local.weekday()]} "
                    f"{current_local.day} "
                    f"{MONTHS_FR[current_local.month]} "
                    f"{current_local.year} à "
                    f"{current_local.strftime('%H:%M:%S')}"
                ),
            },
            "first_interaction_at_utc": (
                first_interaction.isoformat()
            ),
            "previous_interaction": None,
            "elapsed_since_previous": None,
        }

        if previous_interaction is not None:
            previous_local = previous_interaction.astimezone(zone)

            context["previous_interaction"] = {
                "utc": previous_interaction.isoformat(),
                "local": previous_local.isoformat(),
            }
            context["elapsed_since_previous"] = {
                "seconds": elapsed_seconds,
                "human": _format_duration(elapsed_seconds or 0),
            }

        if commit:
            new_state = {
                "version": 1,
                "timezone": timezone_name,
                "first_interaction_at_utc": (
                    first_interaction.isoformat()
                ),
                "last_interaction_at_utc": current_utc.isoformat(),
                "interaction_count": interaction_number,
                "updated_at_utc": current_utc.isoformat(),
            }
            _write_state_atomic(state_path, new_state)

        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    return context, warnings
