from __future__ import annotations

from typing import Any, Dict, List, Optional

from renglo.common import load_config
from renglo.data.data_controller import DataController

from gro.handlers.common import make_constraint_key, make_edge_fanout_key


class CostEstimator:
    """
    Estimates plan cost using persisted graph statistics.
    """

    NODE_COUNTS_RING = "gro_node_counts"
    PROPERTY_CARDINALITY_RING = "gro_property_cardinality"
    EDGE_FANOUT_RING = "gro_edge_fanout"

    def __init__(self):
        self.DAC = DataController(config=load_config())

    def _scan_ring_documents(self, portfolio: str, org: str, ring: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        last_id: Optional[str] = None
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

    def _read_node_counts(self, portfolio: str, org: str) -> Dict[str, int]:
        node_counts: Dict[str, int] = {}
        for doc in self._scan_ring_documents(portfolio, org, self.NODE_COUNTS_RING):
            ring_name = doc.get("node_type")
            count = doc.get("count")
            if ring_name is None:
                continue
            try:
                node_counts[str(ring_name)] = int(count)
            except (TypeError, ValueError):
                continue
        return node_counts

    def _read_property_cardinality(self, portfolio: str, org: str) -> Dict[str, int]:
        flattened: Dict[str, int] = {}
        for doc in self._scan_ring_documents(portfolio, org, self.PROPERTY_CARDINALITY_RING):
            ring_name = str(doc.get("node_type", "")).strip()
            property_counts = doc.get("property_counts", {})
            if not ring_name or not isinstance(property_counts, dict):
                continue

            for field_name, values_map in property_counts.items():
                if not isinstance(values_map, dict):
                    continue
                for value_key, count in values_map.items():
                    key = f"{ring_name}.{field_name}={value_key}"
                    try:
                        flattened[key] = int(count)
                    except (TypeError, ValueError):
                        continue
        return flattened

    def _read_edge_fanout(self, portfolio: str, org: str) -> Dict[str, Dict[str, Any]]:
        edge_fanout: Dict[str, Dict[str, Any]] = {}
        for doc in self._scan_ring_documents(portfolio, org, self.EDGE_FANOUT_RING):
            from_node = str(doc.get("from_node", "")).strip()
            to_node = str(doc.get("to_node", "")).strip()
            edge_type = str(doc.get("edge_type", "")).strip()
            if not edge_type:
                continue

            metrics = {
                "from_node": from_node,
                "to_node": to_node,
                "edge_type": edge_type,
                "total_edges": int(doc.get("total_edges", 0) or 0),
                "distinct_sources": int(doc.get("distinct_sources", 0) or 0),
                "avg_fanout": float(doc.get("avg_fanout", 0.0) or 0.0),
                "max_fanout": int(doc.get("max_fanout", 0) or 0),
            }
            if from_node and to_node:
                edge_fanout[make_edge_fanout_key(from_node, to_node, edge_type)] = metrics
            else:
                edge_fanout[edge_type] = metrics
        return edge_fanout

    def _resolve_stats(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        stats = payload.get("stats") or {}
        if stats.get("node_counts") and stats.get("property_cardinality") and stats.get("edge_fanout"):
            return stats

        portfolio = str(payload.get("portfolio", "")).strip()
        org = str(payload.get("org", "")).strip()
        if not portfolio or not org:
            return {
                "node_counts": stats.get("node_counts", {}),
                "property_cardinality": stats.get("property_cardinality", {}),
                "edge_fanout": stats.get("edge_fanout", {}),
            }

        return {
            "node_counts": stats.get("node_counts") or self._read_node_counts(portfolio, org),
            "property_cardinality": stats.get("property_cardinality") or self._read_property_cardinality(portfolio, org),
            "edge_fanout": stats.get("edge_fanout") or self._read_edge_fanout(portfolio, org),
        }

    def _anchor_candidate_count(self, anchor: Dict[str, Any], stats: Dict[str, Any]) -> int:
        property_cardinality = stats.get("property_cardinality", {})
        node_counts = stats.get("node_counts", {})

        if anchor.get("property"):
            key = make_constraint_key(anchor)
            if key in property_cardinality:
                return int(property_cardinality[key])

        node = anchor.get("node")
        if node in node_counts:
            return int(node_counts[node])
        return 1

    def _lookup_avg_fanout(self, edge_fanout: Dict[str, Dict[str, Any]], step: Dict[str, Any]) -> float:
        from_node = str(step.get("from", "")).strip()
        to_node = str(step.get("to", "")).strip()
        edge = str(step.get("edge", "")).strip()

        if from_node and to_node and edge:
            scoped = edge_fanout.get(make_edge_fanout_key(from_node, to_node, edge))
            if scoped is not None:
                return max(float(scoped.get("avg_fanout", 1.0)), 1.0)

        if edge:
            legacy = edge_fanout.get(edge)
            if legacy is not None:
                return max(float(legacy.get("avg_fanout", 1.0)), 1.0)

        return 1.0

    def _cumulative_fanout(self, edge_steps: List[Dict[str, Any]], stats: Dict[str, Any]) -> float:
        edge_fanout = stats.get("edge_fanout", {})
        cumulative = 1.0
        for step in edge_steps:
            cumulative *= self._lookup_avg_fanout(edge_fanout, step)
        return cumulative

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        candidate_plans = payload.get("candidate_plans", [])
        stats = self._resolve_stats(payload or {})
        estimated_plans = []

        for plan in candidate_plans:
            candidate_count = self._anchor_candidate_count(plan.get("anchor", {}), stats)
            cumulative_fanout = self._cumulative_fanout(plan.get("edge_steps", []), stats)
            traversal_depth = max(int(plan.get("traversal_depth", 1)), 1)

            estimated_cost = candidate_count * cumulative_fanout * traversal_depth
            intermediate_explosion = candidate_count * cumulative_fanout

            enriched = dict(plan)
            enriched["cost_breakdown"] = {
                "candidate_count": candidate_count,
                "cumulative_fanout": cumulative_fanout,
                "traversal_depth": traversal_depth,
                "intermediate_explosion": intermediate_explosion,
            }
            enriched["estimated_cost"] = estimated_cost
            estimated_plans.append(enriched)

        return {
            "success": True,
            "component": "cost_estimator",
            "stats": stats,
            "estimated_plans": estimated_plans,
        }
