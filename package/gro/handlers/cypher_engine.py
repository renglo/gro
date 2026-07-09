from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

from gro.handlers.ontology_mapper import OntologyMapper


class CypherEngine:
    """
    Executes Cypher against an in-memory GraphForge database.
    """

    _RELATIONSHIP_PATTERN = re.compile(r"\[:[^\]]+\]")

    def __init__(self, ontology: Optional[OntologyMapper] = None):
        self.ontology = ontology or OntologyMapper.default()

    def prepare_query(self, query_text: str) -> str:
        query = str(query_text or "").strip()
        if not query:
            raise ValueError("query_text is required")

        def _expand_relationship(match: re.Match[str]) -> str:
            token = match.group(0)
            inner = token[2:-1]
            if inner.startswith(":"):
                inner = inner[1:]
            if "|" not in inner and "*" not in inner and inner.isidentifier():
                return f"[:{self.ontology.canonical_relationship(inner)}]"
            if "|" in inner:
                base, _, remainder = inner.partition("*")
                expanded = self.ontology.expand_relationship_pattern(base)
                if remainder:
                    return f"[:{expanded}*{remainder}]"
                return f"[:{expanded}]"
            return token

        return self._RELATIONSHIP_PATTERN.sub(_expand_relationship, query)

    def execute(
        self,
        engine: Any,
        query_text: str,
        *,
        params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        prepared = self.prepare_query(query_text)
        if params:
            result = engine.execute(prepared, params)
        else:
            result = engine.execute(prepared)
        return self._serialize_result(result)

    def _serialize_result(self, result: Any) -> List[Dict[str, Any]]:
        if result is None:
            return []

        if hasattr(result, "to_pylist"):
            rows = result.to_pylist()
            return [self._serialize_row(row) for row in rows]

        if hasattr(result, "to_pandas"):
            frame = result.to_pandas()
            return [self._serialize_row(dict(row)) for row in frame.to_dict(orient="records")]

        if isinstance(result, list):
            return [self._serialize_row(row) for row in result]

        if isinstance(result, dict):
            return [self._serialize_row(result)]

        return [{"value": self._serialize_value(result)}]

    def _serialize_row(self, row: Any) -> Dict[str, Any]:
        if isinstance(row, dict):
            return {str(key): self._serialize_value(value) for key, value in row.items()}

        if hasattr(row, "keys"):
            return {str(key): self._serialize_value(row[key]) for key in row.keys()}

        return {"value": self._serialize_value(row)}

    def _serialize_value(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value

        if isinstance(value, list):
            return [self._serialize_value(item) for item in value]

        if isinstance(value, dict):
            return {str(key): self._serialize_value(item) for key, item in value.items()}

        if hasattr(value, "value"):
            return self._serialize_value(value.value)

        if hasattr(value, "properties") and isinstance(value.properties, dict):
            serialized = {str(key): self._serialize_value(item) for key, item in value.properties.items()}
            labels = getattr(value, "labels", None)
            if labels:
                serialized["_labels"] = list(labels)
            node_id = serialized.get("node_id")
            if node_id:
                serialized["_id"] = node_id
            return serialized

        if hasattr(value, "type") and hasattr(value, "start_node"):
            return {
                "type": str(getattr(value, "type", "")),
                "properties": self._serialize_value(getattr(value, "properties", {})),
            }

        if hasattr(value, "nodes") and hasattr(value, "relationships"):
            return {
                "length": len(getattr(value, "relationships", []) or []),
                "node_ids": [
                    self._serialize_value(getattr(node, "properties", node)).get("node_id")
                    if hasattr(node, "properties")
                    else self._serialize_value(node)
                    for node in getattr(value, "nodes", []) or []
                ],
            }

        return str(value)
