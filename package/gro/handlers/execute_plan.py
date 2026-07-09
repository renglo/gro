from __future__ import annotations

import importlib
from typing import Any, Dict, List, Optional, Set, Tuple

from renglo.common import load_config
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
        self.GRC = GraphController(config=config)
        self.node_projection: Dict[str, Dict[str, Any]] = {}
        self.edge_cache_by_type: Dict[str, List[Any]] = {}
        self.edge_cache_complete: Set[str] = set()

    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        portfolio = str(payload.get("portfolio", "")).strip()
        org = str(payload.get("org", "")).strip()
        if not portfolio or not org:
            raise ValueError("portfolio and org are required")

        execution_plan = payload.get("execution_plan")
        if not isinstance(execution_plan, list) or not execution_plan:
            raise ValueError("execution_plan is required and must be a non-empty list")

        self.node_projection = {}
        self.edge_cache_by_type = {}
        self.edge_cache_complete = set()
        working_set: Set[str] = set()
        trace: List[Dict[str, Any]] = []

        for idx, op in enumerate(execution_plan, start=1):
            op_type = str(op.get("op", "")).strip()
            if not op_type:
                raise ValueError(f"Invalid operation at index {idx - 1}: missing op")

            before = len(working_set)
            resolved_direction = None
            if op_type == "find_nodes":
                working_set = self._op_find_nodes(portfolio, org, op, execution_plan, idx)
            elif op_type == "traverse_forward":
                working_set = self._op_traverse(portfolio, org, working_set, op, direction="forward")
            elif op_type == "traverse_reverse":
                working_set = self._op_traverse(portfolio, org, working_set, op, direction="reverse")
            elif op_type == "traverse_auto":
                following_filters = self._following_filters(execution_plan, idx)
                working_set, resolved_direction = self._op_traverse_auto(
                    portfolio,
                    org,
                    working_set,
                    op,
                    following_filters,
                )
            elif op_type == "filter":
                working_set = self._op_filter(working_set, op)
            else:
                raise ValueError(f"Unsupported op '{op_type}' at index {idx - 1}")

            trace_entry: Dict[str, Any] = {
                "step": idx,
                "op": op_type,
                "before_count": before,
                "after_count": len(working_set),
            }
            if resolved_direction:
                trace_entry["resolved_direction"] = resolved_direction
            trace.append(trace_entry)

        final_node_ids = sorted(working_set)
        return_spec = payload.get("return_spec")
        if isinstance(return_spec, dict):
            kind = str(return_spec.get("kind", "node_ids")).strip().lower()
            if kind != "node_ids":
                raise ValueError("Only return.kind=node_ids is currently supported")
            side = str(return_spec.get("side", "from")).strip().lower()
            if side == "both":
                raise ValueError("return.side=both is not yet supported in execution")
            if side not in {"from", "to"}:
                raise ValueError("return.side must be from or to")
            if not bool(return_spec.get("distinct", True)):
                # Node IDs are always de-duplicated sets in current runtime.
                pass
            offset_raw = return_spec.get("offset")
            limit_raw = return_spec.get("limit")
            offset = int(offset_raw) if isinstance(offset_raw, int) and offset_raw >= 0 else 0
            if offset > 0:
                final_node_ids = final_node_ids[offset:]
            if isinstance(limit_raw, int) and limit_raw >= 0:
                final_node_ids = final_node_ids[:limit_raw]

        return {
            "success": True,
            "executor_kind": "reference",
            "executor_name": "reference_default",
            "plan_length": len(execution_plan),
            "trace": trace,
            "result": {
                "final_node_ids": final_node_ids,
            },
        }

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
        if operator == "not_in":
            return isinstance(right, list) and left not in right
        if operator == "exists":
            return left is not None
        if operator == "not_exists":
            return left is None
        if operator == ">":
            return left is not None and right is not None and left > right
        if operator == "<":
            return left is not None and right is not None and left < right
        if operator in ("in", "IN"):
            return isinstance(right, list) and left in right
        return False

    def _resolve_edge_field(self, edge_row: Any, field_path: str) -> Any:
        field_path = str(field_path or "").strip()
        if not field_path:
            return None
        if field_path in {"from_node_id", "to_node_id", "edge_type"}:
            return getattr(edge_row, field_path, None)

        properties = edge_row.properties if isinstance(edge_row.properties, dict) else {}
        cursor: Any = properties
        for part in field_path.split("."):
            if not isinstance(cursor, dict):
                return None
            if part not in cursor:
                return None
            cursor = cursor.get(part)
        return cursor

    def _edge_matches_predicates(self, edge_row: Any, edge_where: Dict[str, Any]) -> bool:
        for field_path, predicate in edge_where.items():
            if not isinstance(predicate, dict):
                continue
            op = str(predicate.get("op", "=")).strip().lower() or "="
            left = self._resolve_edge_field(edge_row, field_path)
            if not self._compare(left, op, predicate.get("value")):
                return False
        return True

    def _cache_node_projection(self, node_id: str, attrs: Dict[str, Any]) -> None:
        if not attrs:
            return
        existing = self.node_projection.get(node_id, {})
        self.node_projection[node_id] = {**existing, **attrs}

    def _cache_edge_projection(self, edge_row: Any) -> None:
        properties = edge_row.properties if isinstance(edge_row.properties, dict) else {}
        projection = properties.get("projection")
        if not isinstance(projection, dict):
            return

        from_attrs: Dict[str, Any] = {}
        to_attrs: Dict[str, Any] = {}
        for key, value in projection.items():
            if not isinstance(key, str):
                continue
            if key.startswith("from."):
                from_attrs[key[5:]] = value
            elif key.startswith("to."):
                to_attrs[key[3:]] = value

        self._cache_node_projection(edge_row.from_node_id, from_attrs)
        self._cache_node_projection(edge_row.to_node_id, to_attrs)

    def _matches_projection_filter(self, node_id: str, filters: Dict[str, Any]) -> bool:
        attrs = self.node_projection.get(node_id, {})
        for field, expected in filters.items():
            if attrs.get(field) != expected:
                return False
        return True

    def _next_traversal_op(
        self,
        execution_plan: List[Dict[str, Any]],
        step_index: int,
    ) -> Optional[Dict[str, Any]]:
        for op in execution_plan[step_index:]:
            op_type = str(op.get("op", "")).strip()
            if op_type in {"traverse_forward", "traverse_reverse", "traverse_auto"}:
                return op
            if op_type not in {"filter"}:
                break
        return None

    def _op_find_nodes(
        self,
        portfolio: str,
        org: str,
        op: Dict[str, Any],
        execution_plan: List[Dict[str, Any]],
        step_index: int,
    ) -> Set[str]:
        ring = str(op.get("type", "")).strip()
        if not ring:
            raise ValueError("find_nodes requires 'type'")
        filters = op.get("filter", {}) or {}
        if not isinstance(filters, dict):
            raise ValueError("find_nodes.filter must be an object")

        traversal_op = self._next_traversal_op(execution_plan, step_index)
        if not traversal_op:
            raise ValueError(
                "find_nodes requires a subsequent traverse operation in graph-only mode"
            )
        edge_type = str(traversal_op.get("edge", "")).strip()
        if not edge_type:
            raise ValueError(
                "find_nodes requires traverse edge in graph-only mode"
            )
        traversal_kind = str(traversal_op.get("op", "")).strip()

        result: Set[str] = set()
        cached_edges: List[Any] = []
        last_key = None
        while True:
            page = self.GRC.list_edges_by_type(
                portfolio,
                org,
                edge_type,
                limit=500,
                exclusive_start_key=last_key,
            )
            for edge_row in page.items:
                cached_edges.append(edge_row)
                self._cache_edge_projection(edge_row)
                candidates: List[str] = []
                if traversal_kind in {"traverse_forward", "traverse_auto"}:
                    candidates.append(edge_row.from_node_id)
                if traversal_kind in {"traverse_reverse", "traverse_auto"}:
                    candidates.append(edge_row.to_node_id)
                for node_id in candidates:
                    node_ring, _ = self._split_node_id(node_id)
                    if node_ring != ring:
                        continue
                    if not self._matches_projection_filter(node_id, filters):
                        continue
                    result.add(node_id)
            last_key = page.last_evaluated_key
            if not last_key:
                break
        self.edge_cache_by_type[edge_type] = cached_edges
        self.edge_cache_complete.add(edge_type)
        return result

    def _traverse_from_cached_edges(
        self,
        current: Set[str],
        cached_edges: List[Any],
        *,
        direction: str,
        target_type: str,
        edge_where: Dict[str, Any],
    ) -> Set[str]:
        next_set: Set[str] = set()
        for edge_row in cached_edges:
            if direction == "forward":
                if edge_row.from_node_id not in current:
                    continue
                candidate = edge_row.to_node_id
            else:
                if edge_row.to_node_id not in current:
                    continue
                candidate = edge_row.from_node_id

            if edge_where and not self._edge_matches_predicates(edge_row, edge_where):
                continue

            self._cache_edge_projection(edge_row)
            if target_type:
                ring, _ = self._split_node_id(candidate)
                if ring != target_type:
                    continue
            next_set.add(candidate)
        return next_set

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
        edge_where = op.get("edge_where")
        if edge_where is not None and not isinstance(edge_where, dict):
            raise ValueError("traverse edge_where must be an object")
        edge_where = edge_where or {}

        cached_edges = self.edge_cache_by_type.get(edge)
        if edge in self.edge_cache_complete and isinstance(cached_edges, list):
            return self._traverse_from_cached_edges(
                current,
                cached_edges,
                direction=direction,
                target_type=target_type,
                edge_where=edge_where,
            )

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
                    candidates = [(edge_row.to_node_id, edge_row) for edge_row in page.items]
                else:
                    page = self.GRC.list_incoming_edges(
                        portfolio,
                        org,
                        edge,
                        node_id,
                        limit=300,
                        exclusive_start_key=last_key,
                    )
                    candidates = [(edge_row.from_node_id, edge_row) for edge_row in page.items]

                for candidate, edge_row in candidates:
                    if edge_where and not self._edge_matches_predicates(edge_row, edge_where):
                        continue
                    self._cache_edge_projection(edge_row)
                    if target_type:
                        ring, _ = self._split_node_id(candidate)
                        if ring != target_type:
                            continue
                    next_set.add(candidate)

                last_key = page.last_evaluated_key
                if not last_key:
                    break
        return next_set

    def _following_filters(
        self,
        execution_plan: List[Dict[str, Any]],
        step_index: int,
    ) -> List[Dict[str, Any]]:
        filters: List[Dict[str, Any]] = []
        for op in execution_plan[step_index:]:
            if str(op.get("op", "")).strip() != "filter":
                break
            filters.append(op)
        return filters

    def _apply_filters(
        self,
        current: Set[str],
        filters: List[Dict[str, Any]],
    ) -> Set[str]:
        working = set(current)
        for filter_op in filters:
            working = self._op_filter(working, filter_op)
        return working

    def _op_traverse_auto(
        self,
        portfolio: str,
        org: str,
        current: Set[str],
        op: Dict[str, Any],
        following_filters: List[Dict[str, Any]],
    ) -> Tuple[Set[str], str]:
        forward_set = self._op_traverse(portfolio, org, current, op, direction="forward")
        reverse_set = self._op_traverse(portfolio, org, current, op, direction="reverse")

        if not following_filters:
            if len(reverse_set) > len(forward_set):
                return reverse_set, "reverse"
            return forward_set, "forward"

        forward_matches = self._apply_filters(forward_set, following_filters)
        reverse_matches = self._apply_filters(reverse_set, following_filters)

        if len(reverse_matches) > len(forward_matches):
            return reverse_set, "reverse"
        if len(forward_matches) > len(reverse_matches):
            return forward_set, "forward"

        # Tie-breaker: prefer the direction with fewer raw neighbors (cheaper).
        if len(reverse_set) < len(forward_set):
            return reverse_set, "reverse"
        return forward_set, "forward"

    def _op_filter(self, current: Set[str], op: Dict[str, Any]) -> Set[str]:
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

            left = self.node_projection.get(node_id, {}).get(prop)
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

    def _compact_stats_summary(self, stats: Dict[str, Any]) -> Dict[str, int]:
        node_counts = stats.get("node_counts")
        property_cardinality = stats.get("property_cardinality")
        edge_fanout = stats.get("edge_fanout")
        return {
            "node_counts": len(node_counts) if isinstance(node_counts, dict) else 0,
            "property_cardinality": len(property_cardinality) if isinstance(property_cardinality, dict) else 0,
            "edge_fanout": len(edge_fanout) if isinstance(edge_fanout, dict) else 0,
        }

    def _compact_planner_output(self, planned: Dict[str, Any]) -> Dict[str, Any]:
        compact: Dict[str, Any] = {
            "component": planned.get("component", "query_planner_optimizer"),
            "input_kind": planned.get("input_kind"),
            "best_plan": planned.get("best_plan"),
        }
        if isinstance(planned.get("query_pattern"), dict):
            compact["query_pattern"] = planned.get("query_pattern")
        if isinstance(planned.get("return_spec"), dict):
            compact["return_spec"] = planned.get("return_spec")
        if isinstance(planned.get("query_v1"), dict):
            compact["query_v1"] = planned.get("query_v1")

        ranked_plans = planned.get("ranked_plans")
        if isinstance(ranked_plans, list):
            compact["ranked_plan_count"] = len(ranked_plans)

        stats = planned.get("stats")
        if isinstance(stats, dict):
            compact["stats_summary"] = self._compact_stats_summary(stats)
        return compact

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
        include_planner_debug = bool(working_payload.get("include_planner_debug", False))

        # If only a query_pattern is provided, plan first and execute next.
        can_plan = bool(
            working_payload.get("query_pattern")
            or isinstance(working_payload.get("query_text"), str)
            or isinstance(working_payload.get("cypher"), str)
            or (
                isinstance(working_payload.get("version"), (str, int))
                and isinstance(working_payload.get("match"), dict)
            )
        )
        if not working_payload.get("execution_plan") and can_plan:
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
            if planned.get("return_spec"):
                working_payload["return_spec"] = planned.get("return_spec")
            if planned.get("query_v1"):
                working_payload["query_v1"] = planned.get("query_v1")

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
            planner_output = working_payload.get("_planned")
            planner_payload = (
                planner_output if include_planner_debug else self._compact_planner_output(planner_output)
            ) if isinstance(planner_output, dict) else None
            return {
                "success": True,
                "component": "execute_plan",
                "executor_name": executor_name if executor_path else "reference_default",
                "executor_source": executor_source,
                "execution_plan": working_payload.get("execution_plan", []),
                "execution": execution,
                "planner": planner_payload,
            }
        except Exception as exc:
            return {
                "success": False,
                "component": "execute_plan",
                "executor_name": executor_name,
                "message": str(exc),
            }
