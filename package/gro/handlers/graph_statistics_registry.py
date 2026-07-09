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
    make_edge_fanout_doc_key,
    make_edge_fanout_key,
    normalize_blueprint_name,
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

    def _node_ring(self, node_id: str) -> Optional[str]:
        if not isinstance(node_id, str) or "/" not in node_id:
            return None
        ring, _ = node_id.split("/", 1)
        return ring.strip() or None

    def _edge_fanout(
        self,
        portfolio: str,
        org: str,
        edge_type: str,
        from_ring: str,
        to_ring: str,
    ) -> Dict[str, Any]:
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
                source_ring = self._node_ring(edge.from_node_id)
                target_ring = self._node_ring(edge.to_node_id)
                if source_ring != from_ring or target_ring != to_ring:
                    continue
                total_edges += 1
                source_counts[edge.from_node_id] = source_counts.get(edge.from_node_id, 0) + 1

            last_key = page.last_evaluated_key
            if not last_key:
                break

        distinct_sources = len(source_counts)
        avg_fanout = (total_edges / distinct_sources) if distinct_sources > 0 else 0.0
        max_fanout = max(source_counts.values()) if source_counts else 0

        return {
            "from_node": from_ring,
            "to_node": to_ring,
            "edge_type": edge_type,
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

    def _get_ring_blueprint(self, ring: str) -> Optional[Dict[str, Any]]:
        blueprint = self.BPC.get_blueprint("irma", ring, "last")
        if not isinstance(blueprint, dict):
            return None
        if blueprint.get("success") is False:
            return None
        if blueprint.get("error"):
            return None
        if not isinstance(blueprint.get("fields"), list):
            return None
        return blueprint

    def _ring_blueprint_exists(self, ring: str) -> bool:
        return self._get_ring_blueprint(ring) is not None

    def _filter_rings_with_blueprints(self, rings: Set[str]) -> Tuple[Set[str], List[str]]:
        valid: Set[str] = set()
        skipped: List[str] = []
        for ring in sorted(rings):
            if self._ring_blueprint_exists(ring):
                valid.add(ring)
            else:
                skipped.append(ring)
        return valid, skipped

    def _filter_relationships_with_blueprints(
        self,
        relationships: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        valid: List[Dict[str, Any]] = []
        skipped: List[str] = []
        seen: Set[str] = set()

        for rel in relationships:
            from_ring = str(rel.get("from", "")).strip()
            to_ring = str(rel.get("to", "")).strip()
            edge_type = str(rel.get("edge", "")).strip()
            if not from_ring or not to_ring or not edge_type:
                continue
            rel_key = make_edge_fanout_key(from_ring, to_ring, edge_type)
            if rel_key in seen:
                continue
            seen.add(rel_key)
            if self._ring_blueprint_exists(from_ring):
                valid.append(
                    {
                        "from": from_ring,
                        "to": to_ring,
                        "edge": edge_type,
                    }
                )
            else:
                skipped.append(rel_key)

        return valid, skipped

    def _get_countable_fields(self, ring: str) -> List[Dict[str, Any]]:
        blueprint = self._get_ring_blueprint(ring)
        if not blueprint:
            return []
        fields = blueprint.get("fields", [])
        if not isinstance(fields, list):
            return []
        return [field for field in fields if isinstance(field, dict) and bool(field.get("countable", False))]

    def _infer_relationships_from_blueprints(self, rings: Set[str]) -> List[Dict[str, Any]]:
        """
        Derive outgoing source-field relationships from ring blueprints.
        Uses the same implicit edge types persisted by GraphController.
        """
        relationships: List[Dict[str, Any]] = []
        seen: Set[str] = set()

        for ring in sorted(rings):
            blueprint = self._get_ring_blueprint(ring)
            if not blueprint:
                continue

            edge_specs = self.GRC._get_edge_specs_from_blueprint(blueprint, ring)
            for spec in edge_specs:
                if spec.get("kind") != "source":
                    continue

                to_ring = normalize_blueprint_name(str(spec.get("to_ring", "")))
                edge_type = str(spec.get("edge_type", "")).strip()
                if not to_ring or not edge_type:
                    continue

                rel_key = make_edge_fanout_key(ring, to_ring, edge_type)
                if rel_key in seen:
                    continue
                seen.add(rel_key)
                relationships.append(
                    {
                        "from": ring,
                        "to": to_ring,
                        "edge": edge_type,
                    }
                )

        return relationships

    def _merge_relationships(
        self,
        explicit: List[Dict[str, Any]],
        inferred: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        seen: Set[str] = set()

        for rel in explicit + inferred:
            from_ring = str(rel.get("from", "")).strip()
            to_ring = str(rel.get("to", "")).strip()
            edge_type = str(rel.get("edge", "")).strip()
            if not from_ring or not to_ring or not edge_type:
                continue
            rel_key = make_edge_fanout_key(from_ring, to_ring, edge_type)
            if rel_key in seen:
                continue
            seen.add(rel_key)
            merged.append(
                {
                    "from": from_ring,
                    "to": to_ring,
                    "edge": edge_type,
                }
            )

        return merged

    def _persisted_scope(self, portfolio: str, org: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        rings: Set[str] = set()
        for doc in self._scan_ring_documents(portfolio, org, self.NODE_COUNTS_RING):
            node_type = str(doc.get("node_type", "")).strip()
            if node_type:
                rings.add(node_type)

        for doc in self._scan_ring_documents(portfolio, org, self.PROPERTY_CARDINALITY_RING):
            node_type = str(doc.get("node_type", "")).strip()
            if node_type:
                rings.add(node_type)

        relationships: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for doc in self._scan_ring_documents(portfolio, org, self.EDGE_FANOUT_RING):
            from_node = str(doc.get("from_node", "")).strip()
            to_node = str(doc.get("to_node", "")).strip()
            edge_type = str(doc.get("edge_type", "")).strip()
            if not from_node or not to_node or not edge_type:
                continue
            rel_key = make_edge_fanout_key(from_node, to_node, edge_type)
            if rel_key in seen:
                continue
            seen.add(rel_key)
            relationships.append(
                {
                    "from": from_node,
                    "to": to_node,
                    "edge": edge_type,
                }
            )
            rings.add(from_node)
            rings.add(to_node)

        return sorted(rings), relationships

    def _flatten_property_cardinality(
        self,
        property_cardinality_by_ring: Dict[str, Dict[str, Dict[str, int]]],
    ) -> Dict[str, int]:
        flattened: Dict[str, int] = {}
        for ring, field_map in property_cardinality_by_ring.items():
            for field_name, values_map in field_map.items():
                for value_key, count in values_map.items():
                    flattened[f"{ring}.{field_name}={value_key}"] = int(count)
        return flattened

    def _parse_sync_scope(
        self,
        scope: Dict[str, Any],
    ) -> Tuple[Set[str], List[Dict[str, Any]]]:
        involved_rings: Set[str] = set()
        relationships: List[Dict[str, Any]] = []

        nodes_raw = scope.get("nodes", [])
        if isinstance(nodes_raw, list):
            for node in nodes_raw:
                name = normalize_blueprint_name(str(node))
                if name:
                    involved_rings.add(name)

        relationships_raw = scope.get("relationships", [])
        if isinstance(relationships_raw, list):
            for raw in relationships_raw:
                if not isinstance(raw, dict):
                    continue
                rel = {
                    "from": normalize_blueprint_name(str(raw.get("from", ""))),
                    "to": normalize_blueprint_name(str(raw.get("to", ""))),
                    "edge": str(raw.get("edge", "")).strip(),
                }
                if not rel["from"] or not rel["to"] or not rel["edge"]:
                    continue
                relationships.append(rel)
                involved_rings.add(rel["from"])
                involved_rings.add(rel["to"])

        return involved_rings, relationships

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        portfolio, org = self._require_scope(payload or {})
        constraints: List[Dict[str, Any]] = []
        relationships_for_edges: List[Dict[str, Any]] = []

        sync_scope = payload.get("sync_scope")
        inferred_relationships: List[Dict[str, Any]] = []
        if isinstance(sync_scope, dict):
            involved_rings, relationships_for_edges = self._parse_sync_scope(sync_scope)
            if not involved_rings:
                return {
                    "success": False,
                    "component": "graph_statistics_registry",
                    "message": "sync_scope requires at least one node",
                }
            inferred_relationships = self._infer_relationships_from_blueprints(involved_rings)
            relationships_for_edges = self._merge_relationships(
                relationships_for_edges,
                inferred_relationships,
            )
        elif payload.get("recalculate_persisted"):
            involved_rings_list, _persisted_relationships = self._persisted_scope(portfolio, org)
            involved_rings = set(involved_rings_list)
            inferred_relationships = self._infer_relationships_from_blueprints(involved_rings)
            relationships_for_edges = self._merge_relationships(
                _persisted_relationships,
                inferred_relationships,
            )
            if not involved_rings and not relationships_for_edges:
                return {
                    "success": True,
                    "component": "graph_statistics_registry",
                    "message": "No persisted statistics to recalculate",
                    "stats": {
                        "node_counts": {},
                        "property_cardinality": {},
                        "property_cardinality_by_ring": {},
                        "edge_fanout": {},
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                    "persistence": {
                        self.NODE_COUNTS_RING: [],
                        self.PROPERTY_CARDINALITY_RING: [],
                        self.EDGE_FANOUT_RING: [],
                    },
                }
        else:
            query_pattern = normalize_query_pattern(get_query_pattern(payload or {}))
            involved_rings = {query_pattern["target"]}
            for constraint in query_pattern.get("constraints", []):
                involved_rings.add(constraint["node"])
            for rel in query_pattern.get("relationships", []):
                involved_rings.add(rel["from"])
                involved_rings.add(rel["to"])
            relationships_for_edges = query_pattern.get("relationships", [])
            inferred_relationships = self._infer_relationships_from_blueprints(involved_rings)
            relationships_for_edges = self._merge_relationships(
                relationships_for_edges,
                inferred_relationships,
            )
            constraints = query_pattern.get("constraints", [])

        involved_rings, skipped_rings = self._filter_rings_with_blueprints(involved_rings)
        sync_relationships, skipped_edges = self._filter_relationships_with_blueprints(
            relationships_for_edges
        )

        if not involved_rings and not sync_relationships:
            return {
                "success": True,
                "component": "graph_statistics_registry",
                "message": "No rings or edges with registered blueprints to synchronize",
                "skipped": {
                    "rings": skipped_rings,
                    "edges": skipped_edges,
                },
                "stats": {
                    "node_counts": {},
                    "property_cardinality": {},
                    "property_cardinality_by_ring": {},
                    "edge_fanout": {},
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                "persistence": {
                    self.NODE_COUNTS_RING: [],
                    self.PROPERTY_CARDINALITY_RING: [],
                    self.EDGE_FANOUT_RING: [],
                },
            }

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
        if constraints:
            for constraint in constraints:
                ring = constraint.get("node")
                if ring not in involved_rings:
                    continue
                field = constraint.get("property")
                value = constraint.get("value")
                key = make_constraint_key(constraint)
                ring_stats = property_cardinality_by_ring.get(str(ring), {})
                value_stats = ring_stats.get(str(field), {})
                if str(value) in value_stats:
                    property_cardinality[key] = value_stats[str(value)]
                else:
                    property_cardinality[key] = self._count_constraint(portfolio, org, constraint)
        else:
            property_cardinality = self._flatten_property_cardinality(property_cardinality_by_ring)

        edge_fanout: Dict[str, Dict[str, Any]] = {}
        for rel in sync_relationships:
            from_ring = rel["from"]
            to_ring = rel["to"]
            edge_type = rel["edge"]
            edge_fanout[make_edge_fanout_key(from_ring, to_ring, edge_type)] = self._edge_fanout(
                portfolio,
                org,
                edge_type,
                from_ring,
                to_ring,
            )

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

        for fanout_key, metrics in edge_fanout.items():
            from_ring = str(metrics.get("from_node", "")).strip()
            to_ring = str(metrics.get("to_node", "")).strip()
            edge_type = str(metrics.get("edge_type", "")).strip()
            persistence[self.EDGE_FANOUT_RING].append(
                self._upsert_stats_doc(
                    portfolio,
                    org,
                    self.EDGE_FANOUT_RING,
                    make_edge_fanout_doc_key(from_ring, to_ring, edge_type),
                    {
                        "from_node": from_ring,
                        "to_node": to_ring,
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
            "skipped": {
                "rings": skipped_rings,
                "edges": skipped_edges,
            },
            "inferred_relationships": inferred_relationships,
            "stats": {
                "node_counts": node_counts,
                "property_cardinality": property_cardinality,
                "property_cardinality_by_ring": property_cardinality_by_ring,
                "edge_fanout": edge_fanout,
                "updated_at": timestamp,
            },
            "persistence": persistence,
        }
