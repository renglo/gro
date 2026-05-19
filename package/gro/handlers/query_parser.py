from __future__ import annotations

from typing import Any, Dict

from gro.handlers.common import get_query_pattern, normalize_query_pattern


class QueryParser:
    """
    Converts incoming graph query payloads into normalized QueryPattern objects.
    """

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raw_pattern = get_query_pattern(payload or {})
        query_pattern = normalize_query_pattern(raw_pattern)
        return {
            "success": True,
            "component": "query_parser",
            "query_pattern": query_pattern,
        }
