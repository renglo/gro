from __future__ import annotations

from typing import Any, Dict, List


def get_query_pattern(payload: Dict[str, Any]) -> Dict[str, Any]:
    pattern = payload.get("query_pattern") or payload.get("query") or payload.get("input")
    if not isinstance(pattern, dict):
        raise ValueError("Missing query_pattern/query object")
    return pattern


def normalize_query_pattern(raw_pattern: Dict[str, Any]) -> Dict[str, Any]:
    target = str(raw_pattern.get("target", "")).strip()
    if not target:
        raise ValueError("query_pattern.target is required")

    constraints: List[Dict[str, Any]] = []
    for raw in raw_pattern.get("constraints", []):
        if not isinstance(raw, dict):
            continue
        node = str(raw.get("node", "")).strip()
        prop = str(raw.get("property", "")).strip()
        op = str(raw.get("operator", "=")).strip() or "="
        if not node or not prop:
            continue
        constraints.append(
            {
                "node": node,
                "property": prop,
                "operator": op,
                "value": raw.get("value"),
            }
        )

    relationships: List[Dict[str, Any]] = []
    for raw in raw_pattern.get("relationships", []):
        if not isinstance(raw, dict):
            continue
        from_node = str(raw.get("from", "")).strip()
        to_node = str(raw.get("to", "")).strip()
        edge = str(raw.get("edge", "")).strip()
        if not from_node or not to_node or not edge:
            continue
        relationships.append(
            {
                "from": from_node,
                "to": to_node,
                "edge": edge,
            }
        )

    return {
        "target": target,
        "constraints": constraints,
        "relationships": relationships,
    }


def make_constraint_key(constraint: Dict[str, Any]) -> str:
    return (
        f"{constraint.get('node', '')}."
        f"{constraint.get('property', '')}"
        f"{constraint.get('operator', '=')}"
        f"{constraint.get('value', '')}"
    )
