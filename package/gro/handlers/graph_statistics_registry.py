from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from renglo.blueprint.blueprint_controller import BlueprintController
from renglo.common import load_config
from renglo.data.data_controller import DataController
from renglo.graph.graph_controller import GraphController

from gro.handlers.common import (
    get_query_pattern,
    make_constraint_key,
    normalize_query_pattern,
)


class GraphStatisticsRegistry:
    """
    Computes and persists graph statistics used by cost estimation.
    """

    NODE_COUNTS_RING = "gro_node_counts"
    PROPERTY_CARDINALITY_RING = "gro_property_cardinality"
    EDGE_FANOUT_RING = "gro_edge_fanout"

    def __init__(self):
        config = load_config()
        self.config = config
        self.DAC = DataController(config=config)
        self.GRC = GraphController(config=config)
        self.BPC = BlueprintController(config=config)

    def _require_scope(self, payload: Dict[str, Any]) -> Tuple[str, str]:
        portfolio = str(payload.get("portfolio", "")).strip()
        org = str(payload.get("org", "")).strip()
        if not portfolio or not org:
            raise ValueError("portfolio and org are required")
        return portfolio, org

    def _scan_ring_documents(self, portfolio: str, org: str, ring: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        last_id: Optional[str] = None

        while True:
            response = self.DAC.get_a_b(
                portfolio,
                org,
                ring,
                limit=500,
                lastkey=last_id,
            )
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

    def _count_ring(self, portfolio: str, org: str, ring: str) -> int:
        return len(self._scan_ring_documents(portfolio, org, ring))

    def _matches_constraint(self, value: Any, operator: str, expected: Any) -> bool:
        if operator in ("=", "=="):
            return value == expected
        if operator == "!=":
            return value != expected
        if operator == ">":
            return value is not None and expected is not None and value > expected
        if operator == "<":
            return value is not None and expected is not None and value < expected
        if operator in ("in", "IN"):
            return isinstance(expected, list) and value in expected
        return False

    def _count_constraint(self, portfolio: str, org: str, constraint: Dict[str, Any]) -> int:
        ring = constraint["node"]
        prop = constraint["property"]
        operator = constraint.get("operator", "=")
        expected = constraint.get("value")

        count = 0
        for item in self._scan_ring_documents(portfolio, org, ring):
            if self._matches_constraint(item.get(prop), operator, expected):
                count += 1
        return count

    def _range_bucket(
        self,
        value: Any,
        ranges: List[Any],
    ) -> str:
        """
        Returns the bucket key for range-limited countable fields.
        """
        if value in ranges:
            return str(value)
        return "__other__"

    def _countable_field_stats(
        self,
        portfolio: str,
        org: str,
        ring: str,
        field_cfg: Dict[str, Any],
    ) -> Dict[str, int]:
        field_name = str(field_cfg.get("name", "")).strip()
        if not field_name:
            return {}

        ranges = field_cfg.get("count_ranges")
        if ranges is not None and not isinstance(ranges, list):
            ranges = None

        counts: Dict[str, int] = {}
        for item in self._scan_ring_documents(portfolio, org, ring):
            if field_name not in item:
                continue
            raw_value = item.get(field_name)
            if ranges is not None:
                bucket = self._range_bucket(raw_value, ranges)
                counts[bucket] = counts.get(bucket, 0) + 1
                continue

            key = str(raw_value)
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _edge_fanout(self, portfolio: str, org: str, edge_type: str) -> Dict[str, Any]:
        last_key: Optional[Dict[str, Any]] = None
        total_edges = 0
        source_counts: Dict[str, int] = {}

        while True:
            page = self.GRC.list_edges_by_type(
                portfolio,
                org,
                edge_type,
                limit=500,
                exclusive_start_key=last_key,
            )
            for edge in page.items:
                total_edges += 1
                source_counts[edge.from_node_id] = source_counts.get(edge.from_node_id, 0) + 1

            last_key = page.last_evaluated_key
            if not last_key:
                break

        distinct_sources = len(source_counts)
        avg_fanout = (total_edges / distinct_sources) if distinct_sources > 0 else 0.0
        max_fanout = max(source_counts.values()) if source_counts else 0

        return {
            "total_edges": total_edges,
            "distinct_sources": distinct_sources,
            "avg_fanout": avg_fanout,
            "max_fanout": max_fanout,
        }

    def _build_path_index(self, org: str, ring: str, index_value: str) -> str:
        return f"irn:h_index:{org}:{ring}:{index_value}"

    def _upsert_stats_doc(
        self,
        portfolio: str,
        org: str,
        ring: str,
        key: str,
        attributes: Dict[str, Any],
        timestamp: str,
    ) -> Dict[str, Any]:
        # Deterministic IDs allow incremental per-key updates.
        doc_id = f"{ring}:{key}"

        blueprint = self.BPC.get_blueprint("irma", ring, "last")
        blueprint_uri = blueprint.get("uri", "")
        blueprint_version = blueprint.get("version", "")

        item = {
            "added": timestamp,
            "modified": timestamp,
            "license": "CC BY",
            "public": False,
            "blueprint": blueprint_uri,
            "portfolio": portfolio,
            "org": org,
            "ring": ring,
            "blueprint_version": blueprint_version,
            "_id": doc_id,
            "attributes": self.DAC.sanitize(attributes),
            "path_index": self._build_path_index(org, ring, key),
        }

        response = self.DAC.DAM.post_a_b(portfolio, org, ring, item)
        return {"response": response, "status": 200 if "error" not in response else 400}

    def _get_countable_fields(self, ring: str) -> List[Dict[str, Any]]:
        blueprint = self.BPC.get_blueprint("irma", ring, "last")
        if not isinstance(blueprint, dict):
            return []
        fields = blueprint.get("fields", [])
        if not isinstance(fields, list):
            return []
        return [field for field in fields if isinstance(field, dict) and bool(field.get("countable", False))]

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        portfolio, org = self._require_scope(payload or {})
        query_pattern = normalize_query_pattern(get_query_pattern(payload or {}))

        involved_rings: Set[str] = {query_pattern["target"]}
        for constraint in query_pattern.get("constraints", []):
            involved_rings.add(constraint["node"])
        for rel in query_pattern.get("relationships", []):
            involved_rings.add(rel["from"])
            involved_rings.add(rel["to"])

        node_counts: Dict[str, int] = {}
        for ring in sorted(involved_rings):
            node_counts[ring] = self._count_ring(portfolio, org, ring)

        # Count only fields explicitly marked as countable in ring blueprints.
        property_cardinality_by_ring: Dict[str, Dict[str, Dict[str, int]]] = {}
        for ring in sorted(involved_rings):
            field_map: Dict[str, Dict[str, int]] = {}
            for field_cfg in self._get_countable_fields(ring):
                field_name = str(field_cfg.get("name", "")).strip()
                if not field_name:
                    continue
                field_map[field_name] = self._countable_field_stats(portfolio, org, ring, field_cfg)
            property_cardinality_by_ring[ring] = field_map

        # Keep flattened constraint keys for current optimizer API compatibility.
        property_cardinality: Dict[str, int] = {}
        for constraint in query_pattern.get("constraints", []):
            ring = constraint.get("node")
            field = constraint.get("property")
            value = constraint.get("value")
            key = make_constraint_key(constraint)
            ring_stats = property_cardinality_by_ring.get(str(ring), {})
            value_stats = ring_stats.get(str(field), {})
            if str(value) in value_stats:
                property_cardinality[key] = value_stats[str(value)]
            else:
                property_cardinality[key] = self._count_constraint(portfolio, org, constraint)

        edge_fanout: Dict[str, Dict[str, Any]] = {}
        edge_types = sorted({rel["edge"] for rel in query_pattern.get("relationships", [])})
        for edge_type in edge_types:
            edge_fanout[edge_type] = self._edge_fanout(portfolio, org, edge_type)

        timestamp = datetime.now(timezone.utc).isoformat()

        persistence: Dict[str, List[Dict[str, Any]]] = {
            self.NODE_COUNTS_RING: [],
            self.PROPERTY_CARDINALITY_RING: [],
            self.EDGE_FANOUT_RING: [],
        }

        for ring, count in node_counts.items():
            persistence[self.NODE_COUNTS_RING].append(
                self._upsert_stats_doc(
                    portfolio,
                    org,
                    self.NODE_COUNTS_RING,
                    ring,
                    {
                        "node_type": ring,
                        "count": int(count),
                        "updated_at": timestamp,
                    },
                    timestamp,
                )
            )

        for ring, field_counts in property_cardinality_by_ring.items():
            persistence[self.PROPERTY_CARDINALITY_RING].append(
                self._upsert_stats_doc(
                    portfolio,
                    org,
                    self.PROPERTY_CARDINALITY_RING,
                    ring,
                    {
                        "node_type": ring,
                        "property_counts": field_counts,
                        "updated_at": timestamp,
                    },
                    timestamp,
                )
            )

        for edge_type, metrics in edge_fanout.items():
            persistence[self.EDGE_FANOUT_RING].append(
                self._upsert_stats_doc(
                    portfolio,
                    org,
                    self.EDGE_FANOUT_RING,
                    edge_type,
                    {
                        "edge_type": edge_type,
                        "total_edges": int(metrics.get("total_edges", 0)),
                        "distinct_sources": int(metrics.get("distinct_sources", 0)),
                        "avg_fanout": float(metrics.get("avg_fanout", 0.0)),
                        "max_fanout": int(metrics.get("max_fanout", 0)),
                        "updated_at": timestamp,
                    },
                    timestamp,
                )
            )

        return {
            "success": True,
            "component": "graph_statistics_registry",
            "stats": {
                "node_counts": node_counts,
                "property_cardinality": property_cardinality,
                "property_cardinality_by_ring": property_cardinality_by_ring,
                "edge_fanout": edge_fanout,
                "updated_at": timestamp,
            },
            "persistence": persistence,
        }
