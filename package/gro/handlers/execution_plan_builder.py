from __future__ import annotations

from typing import Any, Dict, List

from gro.handlers.common import get_query_pattern, normalize_query_pattern, same_constraint


class ExecutionPlanBuilder:
    """
    Builds executable traversal operations from the selected plan.
    """

    def _anchor_operation(self, anchor: Dict[str, Any]) -> Dict[str, Any]:
        if anchor.get("property"):
            return {
                "op": "find_nodes",
                "type": anchor.get("node"),
                "filter": {anchor.get("property"): anchor.get("value")},
            }
        return {
            "op": "find_nodes",
            "type": anchor.get("node"),
            "filter": {},
        }

    def _edge_operation(self, step: Dict[str, Any]) -> Dict[str, Any]:
        direction = str(step.get("direction", "forward")).strip() or "forward"
        edge_where = step.get("edge_where")
        if direction == "auto":
            op: Dict[str, Any] = {
                "op": "traverse_auto",
                "edge": step.get("edge"),
                "target_type": step.get("to"),
            }
            if isinstance(edge_where, dict) and edge_where:
                op["edge_where"] = edge_where
            return op
        op_name = "traverse_forward" if direction == "forward" else "traverse_reverse"
        op: Dict[str, Any] = {
            "op": op_name,
            "edge": step.get("edge"),
            "target_type": step.get("to"),
        }
        if isinstance(edge_where, dict) and edge_where:
            op["edge_where"] = edge_where
        return op

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        query_pattern = normalize_query_pattern(get_query_pattern(payload or {}))
        best_plan = payload.get("best_plan") or {}

        operations: List[Dict[str, Any]] = []
        anchor = best_plan.get("anchor", {"node": query_pattern["target"]})
        operations.append(self._anchor_operation(anchor))

        for step in best_plan.get("edge_steps", []):
            operations.append(self._edge_operation(step))

        for constraint in query_pattern.get("constraints", []):
            if same_constraint(constraint, anchor):
                continue
            operations.append(
                {
                    "op": "filter",
                    "node": constraint.get("node"),
                    "property": constraint.get("property"),
                    "operator": constraint.get("operator"),
                    "value": constraint.get("value"),
                }
            )

        return {
            "success": True,
            "component": "execution_plan_builder",
            "execution_plan": operations,
            "best_plan": best_plan,
        }
