from __future__ import annotations

from typing import Any, Dict, List


def normalize_blueprint_name(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def get_query_pattern(payload: Dict[str, Any]) -> Dict[str, Any]:
    pattern = payload.get("query_pattern") or payload.get("query") or payload.get("input")
    if not isinstance(pattern, dict):
        raise ValueError("Missing query_pattern/query object")
    return pattern


def normalize_query_pattern(raw_pattern: Dict[str, Any]) -> Dict[str, Any]:
    target = normalize_blueprint_name(str(raw_pattern.get("target", "")))
    if not target:
        raise ValueError("query_pattern.target is required")

    constraints: List[Dict[str, Any]] = []
    for raw in raw_pattern.get("constraints", []):
        if not isinstance(raw, dict):
            continue
        node = normalize_blueprint_name(str(raw.get("node", "")))
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
        from_node = normalize_blueprint_name(str(raw.get("from", "")))
        to_node = normalize_blueprint_name(str(raw.get("to", "")))
        edge = str(raw.get("edge", "")).strip()
        if not from_node or not to_node or not edge:
            continue
        rel: Dict[str, Any] = {
            "from": from_node,
            "to": to_node,
            "edge": edge,
        }
        direction = str(raw.get("direction", "")).strip().lower()
        if direction in {"incoming", "outgoing", "either"}:
            rel["direction"] = direction
        edge_where = raw.get("edge_where")
        if isinstance(edge_where, dict):
            rel["edge_where"] = edge_where
        relationships.append(rel)

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


def same_constraint(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    left_key = str(left.get("key", "")).strip()
    right_key = str(right.get("key", "")).strip()
    if left_key and right_key:
        return left_key == right_key
    return make_constraint_key(left) == make_constraint_key(right)


def make_edge_fanout_key(from_node: str, to_node: str, edge: str) -> str:
    return f"{from_node}->{to_node}:{edge}"


def make_edge_fanout_doc_key(from_node: str, to_node: str, edge: str) -> str:
    return f"{from_node}:{to_node}:{edge}"
