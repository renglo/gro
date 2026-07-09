from __future__ import annotations

from typing import Any, Dict

from gro.handlers.execute_plan import ExecutePlan


class GraphQueryV1:
    """
    Executes Gro query schema v1 (or Cypher-like query_text compiled to v1).
    """

    def __init__(self):
        self.executor = ExecutePlan()

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        executed = self.executor.run(payload or {})
        if not executed.get("success"):
            return {
                "success": False,
                "component": "graph_query_v1",
                "message": executed.get("message", "Execution failed"),
                "execution": executed,
            }

        execution = executed.get("execution", {}) if isinstance(executed.get("execution"), dict) else {}
        result = execution.get("result", {}) if isinstance(execution.get("result"), dict) else {}
        trace = execution.get("trace", []) if isinstance(execution.get("trace"), list) else []
        planner = executed.get("planner", {}) if isinstance(executed.get("planner"), dict) else {}
        query_v1 = planner.get("query_v1")
        if not isinstance(query_v1, dict):
            query_v1 = payload.get("query_v1") if isinstance(payload.get("query_v1"), dict) else {}

        direction_resolved = None
        for step in trace:
            if isinstance(step, dict) and step.get("resolved_direction"):
                direction_resolved = step.get("resolved_direction")

        node_ids = result.get("final_node_ids", [])
        node_count = len(node_ids) if isinstance(node_ids, list) else 0

        response: Dict[str, Any] = {
            "success": True,
            "component": "graph_query_v1",
            "query": query_v1,
            "result": {
                "node_ids": node_ids if isinstance(node_ids, list) else [],
            },
            "meta": {
                "returned_count": node_count,
            },
        }
        if direction_resolved:
            response["meta"]["direction_resolved"] = direction_resolved
        if query_v1.get("options", {}).get("trace"):
            response["trace"] = {"stages": trace}
        response["execution_plan"] = executed.get("execution_plan", [])
        return response
