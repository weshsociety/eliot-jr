"""Project JSON values onto logical fragment records."""

from typing import Any


def records_from_json(file: str, data: Any) -> list[dict[str, Any]]:
    """Keep the logical file name independent of its physical location."""
    if isinstance(data, dict):
        sections = {
            section: items for section, items in data.items()
            if isinstance(items, list)
        }
        if not sections:
            sections = {"root": [data]}
    elif isinstance(data, list):
        sections = {"root": data}
    else:
        return []

    return [
        {"file": file, "section": section, "data": item}
        for section, items in sections.items()
        for item in items
    ]
