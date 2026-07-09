from __future__ import annotations

import re
from typing import Any, Dict, Tuple

from gro.handlers.common import get_query_pattern, normalize_blueprint_name, normalize_query_pattern


class QueryParser:
    """
    Converts incoming graph query payloads into normalized QueryPattern objects.
    """

    _SUPPORTED_OPERATORS = {"=", "!=", "in", "not_in", "exists", "not_exists"}

    def _parse_where_clause(
        self,
        where_raw: Dict[str, Any],
    ) -> Tuple[list[Dict[str, Any]], Dict[str, Any]]:
        constraints: list[Dict[str, Any]] = []
        edge_where: Dict[str, Any] = {}
        for side in ("from", "to"):
            side_map = where_raw.get(side, {})
            if not isinstance(side_map, dict):
                continue
            for field, predicate in side_map.items():
                if not isinstance(predicate, dict):
                    continue
                op = str(predicate.get("op", "=")).strip().lower() or "="
                if op not in self._SUPPORTED_OPERATORS:
                    raise ValueError(f"Unsupported where operator '{op}'")
                constraints.append(
                    {
                        "node": "__placeholder__",  # replaced by caller
                        "property": str(field).strip(),
                        "operator": op,
                        "value": predicate.get("value"),
                        "_side": side,
                    }
                )

        edge_map = where_raw.get("edge", {})
        if isinstance(edge_map, dict):
            for field, predicate in edge_map.items():
                if not isinstance(predicate, dict):
                    continue
                op = str(predicate.get("op", "=")).strip().lower() or "="
                if op not in self._SUPPORTED_OPERATORS:
                    raise ValueError(f"Unsupported edge where operator '{op}'")
                edge_where[str(field).strip()] = {
                    "op": op,
                    "value": predicate.get("value"),
                }

        return constraints, edge_where

    def _compile_v1_to_query_pattern(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        version = str(payload.get("version", "")).strip()
        if version not in {"1.0", "1"}:
            raise ValueError("Only Gro query schema version 1.0 is supported")

        match = payload.get("match")
        if not isinstance(match, dict):
            raise ValueError("match object is required")
        edge_type = str(match.get("edge_type", "")).strip()
        if not edge_type:
            raise ValueError("match.edge_type is required")

        from_obj = match.get("from")
        to_obj = match.get("to")
        if not isinstance(from_obj, dict) or not isinstance(to_obj, dict):
            raise ValueError("match.from and match.to are required objects")
        from_ring = normalize_blueprint_name(str(from_obj.get("ring", "")))
        to_ring = normalize_blueprint_name(str(to_obj.get("ring", "")))
        if not from_ring or not to_ring:
            raise ValueError("match.from.ring and match.to.ring are required")

        direction = str(match.get("direction", "outgoing")).strip().lower() or "outgoing"
        if direction not in {"outgoing", "incoming", "either"}:
            raise ValueError("match.direction must be outgoing, incoming, or either")

        return_spec = payload.get("return")
        if not isinstance(return_spec, dict):
            raise ValueError("return object is required")
        kind = str(return_spec.get("kind", "")).strip().lower()
        if kind != "node_ids":
            raise ValueError("return.kind currently supports only 'node_ids'")
        side = str(return_spec.get("side", "")).strip().lower()
        if side not in {"from", "to", "both"}:
            raise ValueError("return.side must be from, to, or both")

        where_raw = payload.get("where", {})
        if where_raw is not None and not isinstance(where_raw, dict):
            raise ValueError("where must be an object")
        where_raw = where_raw or {}
        constraints, edge_where = self._parse_where_clause(where_raw)
        mapped_constraints: list[Dict[str, Any]] = []
        for item in constraints:
            mapped = dict(item)
            side_name = mapped.pop("_side", "")
            mapped["node"] = from_ring if side_name == "from" else to_ring
            mapped_constraints.append(mapped)

        where_from_map = where_raw.get("from", {}) if isinstance(where_raw.get("from"), dict) else {}
        where_to_map = where_raw.get("to", {}) if isinstance(where_raw.get("to"), dict) else {}

        rel_from = from_ring
        rel_to = to_ring
        if direction == "incoming":
            rel_from, rel_to = to_ring, from_ring
        relationship: Dict[str, Any] = {
            "from": rel_from,
            "to": rel_to,
            "edge": edge_type,
            "direction": direction,
        }
        if edge_where:
            relationship["edge_where"] = edge_where

        target = from_ring if side == "from" else to_ring
        force_anchor: Dict[str, Any] | None = None
        if side in {"from", "to"}:
            opposite_side = "to" if side == "from" else "from"
            opposite_ring = to_ring if opposite_side == "to" else from_ring
            opposite_filters = where_to_map if opposite_side == "to" else where_from_map
            for field, predicate in opposite_filters.items():
                if not isinstance(predicate, dict):
                    continue
                op = str(predicate.get("op", "=")).strip().lower() or "="
                force_anchor = {
                    "node": opposite_ring,
                    "property": str(field).strip(),
                    "operator": op,
                    "value": predicate.get("value"),
                }
                break
            if force_anchor is None:
                # Fallback for legacy payloads lacking where.from/where.to.
                for c in mapped_constraints:
                    if c.get("node") == opposite_ring:
                        force_anchor = dict(c)
                        break

        options = payload.get("options", {})
        trace = bool(options.get("trace", False)) if isinstance(options, dict) else False

        query_pattern = {
            "target": target,
            "constraints": mapped_constraints,
            "relationships": [relationship],
        }
        return {
            "query_pattern": normalize_query_pattern(query_pattern),
            "query_v1": {
                "version": "1.0",
                "match": {
                    "edge_type": edge_type,
                    "from": {"ring": from_ring, "alias": str(from_obj.get("alias", "from"))},
                    "to": {"ring": to_ring, "alias": str(to_obj.get("alias", "to"))},
                    "direction": direction,
                },
                "where": where_raw,
                "return": {
                    "kind": "node_ids",
                    "side": side,
                    "distinct": bool(return_spec.get("distinct", True)),
                    "limit": return_spec.get("limit"),
                    "offset": return_spec.get("offset"),
                },
                "options": {
                    "mode": "graph_only",
                    "strict_projection": bool(options.get("strict_projection", True))
                    if isinstance(options, dict)
                    else True,
                    "prefer_direction": str(options.get("prefer_direction", "auto"))
                    if isinstance(options, dict)
                    else "auto",
                    "timeout_ms": options.get("timeout_ms") if isinstance(options, dict) else None,
                    "trace": trace,
                },
            },
            "return_spec": {
                "kind": "node_ids",
                "side": side,
                "distinct": bool(return_spec.get("distinct", True)),
                "limit": return_spec.get("limit"),
                "offset": return_spec.get("offset"),
            },
            "force_anchor": force_anchor,
        }

    def _parse_inline_props(self, raw: str) -> Dict[str, Any]:
        raw = raw.strip()
        if not raw:
            return {}
        out: Dict[str, Any] = {}
        for token in [part.strip() for part in raw.split(",") if part.strip()]:
            if ":" not in token:
                continue
            key, value = token.split(":", 1)
            k = key.strip()
            v = value.strip()
            if (v.startswith("'") and v.endswith("'")) or (v.startswith('"') and v.endswith('"')):
                out[k] = v[1:-1]
            else:
                out[k] = v
        return out

    def _parse_literal_value(self, raw: str) -> Any:
        token = raw.strip()
        if not token:
            return token
        if (token.startswith("'") and token.endswith("'")) or (
            token.startswith('"') and token.endswith('"')
        ):
            return token[1:-1]
        lowered = token.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        if lowered == "null":
            return None
        if token.isdigit() or (token.startswith("-") and token[1:].isdigit()):
            try:
                return int(token)
            except ValueError:
                return token
        return token

    def _parse_where_conditions(
        self,
        where_clause: str,
        left_alias: str,
        right_alias: str,
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        where_from: Dict[str, Dict[str, Any]] = {}
        where_to: Dict[str, Dict[str, Any]] = {}
        edge_where: Dict[str, Dict[str, Any]] = {}
        if not where_clause:
            return where_from, where_to, edge_where

        comparisons = [part.strip() for part in re.split(r"(?i)\s+AND\s+", where_clause) if part.strip()]
        comparison_re = re.compile(
            r"^([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_\.]*)\s*(=|!=)\s*(.+)$"
        )
        for comparison in comparisons:
            matched = comparison_re.match(comparison)
            if not matched:
                continue
            alias, field, operator, raw_value = (
                matched.group(1),
                matched.group(2),
                matched.group(3),
                matched.group(4),
            )
            predicate = {"op": operator, "value": self._parse_literal_value(raw_value)}
            if alias == left_alias:
                where_from[field] = predicate
            elif alias == right_alias:
                where_to[field] = predicate
            elif alias.lower() in {"edge", "e", "r"}:
                edge_where[field] = predicate
        return where_from, where_to, edge_where

    def _compile_cypher_like(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        query_text = str(payload.get("query_text") or payload.get("cypher") or "").strip()
        if not query_text:
            raise ValueError("query_text/cypher is required")
        compact = " ".join(query_text.split())

        pattern = re.compile(
            r"(?i)^MATCH\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\{([^}]*)\})?\s*\)\s*"
            r"(?:(<-)|-)\s*\[\s*(?:[A-Za-z_][A-Za-z0-9_]*\s*)?(?::\s*`?([^\]`\s]+(?:[:][^\]`\s]+)*)`?\s*)?\]\s*(?:(->)|-)\s*"
            r"\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\{([^}]*)\})?\s*\)\s*"
            r"(?:WHERE\s+(.+?)\s+)?RETURN\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s+LIMIT\s+(\d+))?\s*;?\s*$"
        )
        match_obj = pattern.match(compact)
        if not match_obj:
            raise ValueError(
                "Unsupported Cypher-like format. Use MATCH (a:Ring {k:'v'})-[:EDGE]->(b:Ring {k:'v'}) RETURN a"
            )

        (
            left_alias,
            left_ring,
            left_props,
            arrow_left,
            edge_type,
            arrow_right,
            right_alias,
            right_ring,
            right_props,
            where_clause,
            return_alias,
            limit_value,
        ) = (match_obj.group(i) for i in range(1, 13))
        if not edge_type:
            raise ValueError("Cypher-like query must include edge type in [:EDGE_TYPE]")
        direction = "outgoing"
        if arrow_left and not arrow_right:
            direction = "incoming"
        elif not arrow_left and not arrow_right:
            direction = "either"

        where_from = {
            key: {"op": "=", "value": value}
            for key, value in self._parse_inline_props(left_props or "").items()
        }
        where_to = {
            key: {"op": "=", "value": value}
            for key, value in self._parse_inline_props(right_props or "").items()
        }
        where_from_extra, where_to_extra, edge_where = self._parse_where_conditions(
            where_clause or "",
            left_alias,
            right_alias,
        )
        where_from.update(where_from_extra)
        where_to.update(where_to_extra)
        if return_alias not in {left_alias, right_alias}:
            raise ValueError("RETURN alias must match one of the MATCH node aliases")
        return_side = "from" if return_alias == left_alias else "to"
        return_payload: Dict[str, Any] = {
            "kind": "node_ids",
            "side": return_side,
            "distinct": True,
        }
        if limit_value:
            try:
                return_payload["limit"] = int(limit_value)
            except ValueError:
                pass

        where_payload: Dict[str, Any] = {
            "from": where_from,
            "to": where_to,
        }
        if edge_where:
            where_payload["edge"] = edge_where
        compiled_payload = {
            "version": "1.0",
            "match": {
                "edge_type": edge_type.strip(),
                "from": {"ring": left_ring, "alias": left_alias},
                "to": {"ring": right_ring, "alias": right_alias},
                "direction": direction,
            },
            "where": where_payload,
            "return": return_payload,
            "options": {
                "mode": "graph_only",
                "strict_projection": True,
            },
        }
        return self._compile_v1_to_query_pattern(compiled_payload)

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = payload or {}
        if isinstance(body.get("version"), (str, int)) and isinstance(body.get("match"), dict):
            compiled = self._compile_v1_to_query_pattern(body)
            return {
                "success": True,
                "component": "query_parser",
                **compiled,
                "input_kind": "json_v1",
            }
        if isinstance(body.get("query_text"), str) or isinstance(body.get("cypher"), str):
            compiled = self._compile_cypher_like(body)
            return {
                "success": True,
                "component": "query_parser",
                **compiled,
                "input_kind": "cypher_like",
            }

        raw_pattern = get_query_pattern(body)
        query_pattern = normalize_query_pattern(raw_pattern)
        return {
            "success": True,
            "component": "query_parser",
            "query_pattern": query_pattern,
            "input_kind": "legacy_query_pattern",
        }
