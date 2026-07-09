from __future__ import annotations

from typing import Any, Dict

from gro.handlers.cost_estimator import CostEstimator


class GraphStatisticsSummary:
    """
    Reads persisted graph statistics without recomputing them.
    """

    def __init__(self):
        self.cost_estimator = CostEstimator()

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        portfolio = str((payload or {}).get("portfolio", "")).strip()
        org = str((payload or {}).get("org", "")).strip()
        if not portfolio or not org:
            return {
                "success": False,
                "component": "graph_statistics_summary",
                "message": "portfolio and org are required",
            }

        stats = self.cost_estimator._resolve_stats({"portfolio": portfolio, "org": org})
        node_counts = stats.get("node_counts", {})
        property_cardinality = stats.get("property_cardinality", {})
        edge_fanout = stats.get("edge_fanout", {})

        return {
            "success": True,
            "component": "graph_statistics_summary",
            "totals": {
                "node_types": len(node_counts),
                "total_nodes": sum(int(count) for count in node_counts.values()),
                "property_entries": len(property_cardinality),
                "edge_types": len(edge_fanout),
                "total_edges": sum(
                    int(metrics.get("total_edges", 0) or 0) for metrics in edge_fanout.values()
                ),
            },
            "stats": stats,
        }
