from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_octopus_records(
    map_path: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Transforme la map Octopus vivante en fragments lisibles par Eliot-Jr."""

    records: list[dict[str, Any]] = []
    errors: list[str] = []

    try:
        data = json.loads(map_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return records, [f"Octopus : {exc}"]

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    if not isinstance(nodes, list):
        return records, ["Octopus : le champ nodes n'est pas une liste."]

    node_by_id: dict[str, dict[str, Any]] = {}

    for node in nodes:
        if not isinstance(node, dict):
            continue

        node_id = str(node.get("id", "")).strip()

        if node_id:
            node_by_id[node_id] = node

    adjacency: dict[str, set[str]] = {
        node_id: set() for node_id in node_by_id
    }

    if isinstance(edges, list):
        for edge in edges:
            if not isinstance(edge, dict):
                continue

            source_id = str(edge.get("f", "")).strip()
            target_id = str(edge.get("t", "")).strip()

            if source_id and target_id:
                adjacency.setdefault(source_id, set()).add(target_id)
                adjacency.setdefault(target_id, set()).add(source_id)

    for node in nodes:
        if not isinstance(node, dict):
            continue

        node_id = str(node.get("id", "")).strip()
        connection_ids: set[str] = set(adjacency.get(node_id, set()))

        declared = node.get("conn", [])

        if isinstance(declared, list):
            connection_ids.update(
                str(connection).strip()
                for connection in declared
                if str(connection).strip()
            )

        connection_names: list[str] = []

        for connection_id in sorted(connection_ids):
            connected = node_by_id.get(connection_id, {})

            connection_names.append(
                str(
                    connected.get("name")
                    or connected.get("label")
                    or connection_id
                )
            )

        records.append({
            "file": "octopus/octopus_data.json",
            "section": "nodes",
            "data": {
                "id": node_id,
                "label": node.get("label", ""),
                "name": node.get("name", ""),
                "date": node.get("date", ""),
                "desc": node.get("desc", ""),
                "src": node.get("src", ""),
                "status": node.get("status", ""),
                "type": node.get("type", ""),
                "connections": connection_names,
                "map": "Octopus",
                "origin": "OCTOPUS LIVE",
            },
        })

    return records, errors
