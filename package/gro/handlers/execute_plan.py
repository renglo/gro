from __future__ import annotations

import importlib
from typing import Any, Dict, List, Optional, Set, Tuple

from renglo.common import load_config
from renglo.data.data_controller import DataController
from renglo.graph.graph_controller import GraphController

from gro.handlers.query_planner_optimizer import QueryPlannerOptimizer


class ReferencePlanExecutor:
    """
    Reference execution design.

    This class is intentionally simple and deterministic so other extensions can
    implement the same contract with different runtime characteristics.
    """

    def __init__(self):
        config = load_config()
        self.DAC = DataController(config=config)
        self.GRC = GraphController(config=config)

    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        portfolio = str(payload.get("portfolio", "")).strip()
        org = str(payload.get("org", "")).strip()
        if not portfolio or not org:
            raise ValueError("portfolio and org are required")

        execution_plan = payload.get("execution_plan")
        if not isinstance(execution_plan, list) or not execution_plan:
            raise ValueError("execution_plan is required and must be a non-empty list")

        working_set: Set[str] = set()
        trace: List[Dict[str, Any]] = []

        for idx, op in enumerate(execution_plan, start=1):
            op_type = str(op.get("op", "")).strip()
            if not op_type:
                raise ValueError(f"Invalid operation at index {idx - 1}: missing op")

            before = len(working_set)
            if op_type == "find_nodes":
                working_set = self._op_find_nodes(portfolio, org, op)
            elif op_type == "traverse_forward":
                working_set = self._op_traverse(portfolio, org, working_set, op, direction="forward")
            elif op_type == "traverse_reverse":
                working_set = self._op_traverse(portfolio, org, working_set, op, direction="reverse")
            elif op_type == "filter":
                working_set = self._op_filter(portfolio, org, working_set, op)
            else:
                raise ValueError(f"Unsupported op '{op_type}' at index {idx - 1}")

            trace.append(
                {
                    "step": idx,
                    "op": op_type,
                    "before_count": before,
                    "after_count": len(working_set),
                }
            )

        final_node_ids = sorted(working_set)
        final_documents = [doc for doc in (self._get_document(portfolio, org, node_id) for node_id in final_node_ids) if doc]

        return {
            "success": True,
            "executor_kind": "reference",
            "executor_name": "reference_default",
            "plan_length": len(execution_plan),
            "trace": trace,
            "result": {
                "final_node_ids": final_node_ids,
                "final_documents": final_documents,
            },
        }

    def _scan_ring_documents(self, portfolio: str, org: str, ring: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        last_id = None
        while True:
            response = self.DAC.get_a_b(portfolio, org, ring, limit=500, lastkey=last_id)
            if not response.get("success"):
                break
            batch = response.get("items", [])
            if not batch:
                break
            items.extend(batch)
            last_id = response.get("last_id")
            if not last_id:
                break
        return items

    def _split_node_id(self, node_id: str) -> Tuple[str, str]:
        if not isinstance(node_id, str):
            raise ValueError("node_id must be a string")
        parts = node_id.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid node id '{node_id}'")
        return parts[0], parts[1]

    def _compare(self, left: Any, operator: str, right: Any) -> bool:
        if operator in ("=", "=="):
            return left == right
        if operator == "!=":
            return left != right
        if operator == ">":
            return left is not None and right is not None and left > right
        if operator == "<":
            return left is not None and right is not None and left < right
        if operator in ("in", "IN"):
            return isinstance(right, list) and left in right
        return False

    def _op_find_nodes(self, portfolio: str, org: str, op: Dict[str, Any]) -> Set[str]:
        ring = str(op.get("type", "")).strip()
        if not ring:
            raise ValueError("find_nodes requires 'type'")
        filters = op.get("filter", {}) or {}
        if not isinstance(filters, dict):
            raise ValueError("find_nodes.filter must be an object")

        result: Set[str] = set()
        for doc in self._scan_ring_documents(portfolio, org, ring):
            if all(doc.get(field) == expected for field, expected in filters.items()):
                doc_id = str(doc.get("_id", "")).strip()
                if doc_id:
                    result.add(GraphController.make_node_id(ring, doc_id))
        return result

    def _op_traverse(
        self,
        portfolio: str,
        org: str,
        current: Set[str],
        op: Dict[str, Any],
        *,
        direction: str,
    ) -> Set[str]:
        edge = str(op.get("edge", "")).strip()
        if not edge:
            raise ValueError(f"traverse_{direction} requires 'edge'")
        target_type = str(op.get("target_type", "")).strip()

        next_set: Set[str] = set()
        for node_id in current:
            last_key = None
            while True:
                if direction == "forward":
                    page = self.GRC.list_outgoing_edges(
                        portfolio,
                        org,
                        edge,
                        node_id,
                        limit=300,
                        exclusive_start_key=last_key,
                    )
                    candidates = [edge_row.to_node_id for edge_row in page.items]
                else:
                    page = self.GRC.list_incoming_edges(
                        portfolio,
                        org,
                        edge,
                        node_id,
                        limit=300,
                        exclusive_start_key=last_key,
                    )
                    candidates = [edge_row.from_node_id for edge_row in page.items]

                for candidate in candidates:
                    if target_type:
                        ring, _ = self._split_node_id(candidate)
                        if ring != target_type:
                            continue
                    next_set.add(candidate)

                last_key = page.last_evaluated_key
                if not last_key:
                    break
        return next_set

    def _get_document(self, portfolio: str, org: str, node_id: str) -> Optional[Dict[str, Any]]:
        ring, idx = self._split_node_id(node_id)
        doc = self.DAC.get_a_b_c(portfolio, org, ring, idx)
        if isinstance(doc, dict) and doc.get("success") is False:
            return None
        if isinstance(doc, dict):
            return {
                "_node_id": node_id,
                "_ring": ring,
                **doc,
            }
        return None

    def _op_filter(self, portfolio: str, org: str, current: Set[str], op: Dict[str, Any]) -> Set[str]:
        node_type = str(op.get("node", "")).strip()
        prop = str(op.get("property", "")).strip()
        operator = str(op.get("operator", "=")).strip() or "="
        value = op.get("value")
        if not prop:
            raise ValueError("filter requires 'property'")

        out: Set[str] = set()
        for node_id in current:
            ring, _ = self._split_node_id(node_id)
            if node_type and ring != node_type:
                continue

            doc = self._get_document(portfolio, org, node_id)
            if not doc:
                continue

            left = doc.get(prop)
            if self._compare(left, operator, value):
                out.add(node_id)
        return out


class ExecutePlan:
    """
    Handler facade for execution.

    Distinction:
    - default executor: reference design (`reference_default`)
    - custom executors: provided by import path (`executor_path`)
    """

    def __init__(self):
        self.default_executor = ReferencePlanExecutor()
        self.planner = QueryPlannerOptimizer()

    def _load_custom_executor(self, executor_path: str):
        # Format: package.module:ClassName
        if ":" not in executor_path:
            raise ValueError("executor_path must follow 'package.module:ClassName'")
        module_name, class_name = executor_path.split(":", 1)
        module = importlib.import_module(module_name)
        klass = getattr(module, class_name)
        instance = klass()
        if not hasattr(instance, "execute"):
            raise ValueError("Custom executor must implement execute(payload)")
        return instance

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload = payload or {}
        working_payload = dict(payload)

        # If only a query_pattern is provided, plan first and execute next.
        if not working_payload.get("execution_plan") and working_payload.get("query_pattern"):
            planned = self.planner.run(working_payload)
            if not planned.get("success"):
                return {
                    "success": False,
                    "component": "execute_plan",
                    "message": "Planner failed",
                    "planner_output": planned,
                }
            working_payload["execution_plan"] = planned.get("execution_plan", [])
            working_payload["_planned"] = planned

        executor_name = str(working_payload.get("executor_name", "reference_default")).strip()
        executor_path = str(working_payload.get("executor_path", "")).strip()

        try:
            if executor_path:
                executor = self._load_custom_executor(executor_path)
                executor_source = "custom"
            else:
                executor = self.default_executor
                executor_source = "reference_default"

            execution = executor.execute(working_payload)
            return {
                "success": True,
                "component": "execute_plan",
                "executor_name": executor_name if executor_path else "reference_default",
                "executor_source": executor_source,
                "execution_plan": working_payload.get("execution_plan", []),
                "execution": execution,
                "planner": working_payload.get("_planned"),
            }
        except Exception as exc:
            return {
                "success": False,
                "component": "execute_plan",
                "executor_name": executor_name,
                "message": str(exc),
            }
