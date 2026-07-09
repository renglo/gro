from __future__ import annotations

from typing import Any, Dict, List

from gro.handlers.common import get_query_pattern, normalize_query_pattern, make_constraint_key


class ConstraintExtractor:
    """
    Extracts anchors, filters and traversal edges from QueryPattern.
    """

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        query_pattern = normalize_query_pattern(get_query_pattern(payload or {}))
        constraints = query_pattern.get("constraints", [])
        relationships = query_pattern.get("relationships", [])

        anchors: List[Dict[str, Any]] = []
        property_filters: List[Dict[str, Any]] = []

        for constraint in constraints:
            anchor = dict(constraint)
            anchor["key"] = make_constraint_key(constraint)
            anchors.append(anchor)
            if constraint["node"] != query_pattern["target"]:
                property_filters.append(dict(constraint))

        forced_anchor = payload.get("force_anchor")
        if isinstance(forced_anchor, dict):
            forced_key = make_constraint_key(forced_anchor)
            selected = [anchor for anchor in anchors if make_constraint_key(anchor) == forced_key]
            if selected:
                anchors = selected

        return {
            "success": True,
            "component": "constraint_extractor",
            "query_pattern": query_pattern,
            "anchors": anchors,
            "property_filters": property_filters,
            "traversal_edges": relationships,
            "aggregation_hints": payload.get("aggregation_hints", []),
        }
