from __future__ import annotations

from typing import Any, Dict, List

from gro.handlers.common import get_query_pattern, normalize_query_pattern


class CandidatePlanGenerator:
    """
    Generates alternative traversal plans based on available anchors.
    """

    def _build_edge_steps(
        self,
        anchor_node: str,
        relationships: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        current = anchor_node
        pending = [dict(rel) for rel in relationships]
        steps: List[Dict[str, Any]] = []

        while pending:
            next_idx = -1
            for idx, rel in enumerate(pending):
                if rel["from"] == current:
                    steps.append(
                        {
                            "edge": rel["edge"],
                            "direction": "forward",
                            "from": rel["from"],
                            "to": rel["to"],
                        }
                    )
                    current = rel["to"]
                    next_idx = idx
                    break
                if rel["to"] == current:
                    steps.append(
                        {
                            "edge": rel["edge"],
                            "direction": "reverse",
                            "from": rel["to"],
                            "to": rel["from"],
                        }
                    )
                    current = rel["from"]
                    next_idx = idx
                    break

            if next_idx == -1:
                rel = pending.pop(0)
                steps.append(
                    {
                        "edge": rel["edge"],
                        "direction": "forward",
                        "from": rel["from"],
                        "to": rel["to"],
                    }
                )
            else:
                pending.pop(next_idx)

        return steps

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        query_pattern = normalize_query_pattern(get_query_pattern(payload or {}))
        anchors = payload.get("anchors") or query_pattern.get("constraints") or []
        relationships = query_pattern.get("relationships", [])

        candidate_plans: List[Dict[str, Any]] = []
        for idx, anchor in enumerate(anchors):
            anchor_node = anchor.get("node", query_pattern["target"])
            edge_steps = self._build_edge_steps(anchor_node, relationships)

            candidate_plans.append(
                {
                    "plan_id": f"plan_{idx + 1}",
                    "anchor": anchor,
                    "anchor_node": anchor_node,
                    "target": query_pattern["target"],
                    "traversal_depth": len(edge_steps),
                    "edge_steps": edge_steps,
                }
            )

        if not candidate_plans:
            candidate_plans.append(
                {
                    "plan_id": "plan_1",
                    "anchor": {"node": query_pattern["target"]},
                    "anchor_node": query_pattern["target"],
                    "target": query_pattern["target"],
                    "traversal_depth": len(relationships),
                    "edge_steps": self._build_edge_steps(query_pattern["target"], relationships),
                }
            )

        return {
            "success": True,
            "component": "candidate_plan_generator",
            "query_pattern": query_pattern,
            "candidate_plans": candidate_plans,
        }
