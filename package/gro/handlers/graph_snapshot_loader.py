from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from renglo.common import load_config
from renglo.graph.graph_controller import GraphController

from gro.handlers.ontology_mapper import OntologyMapper


@dataclass
class SnapshotStats:
    edge_types_scanned: list[str]
    edges_loaded: int
    nodes_loaded: int
    stopped_reason: Optional[str] = None


@dataclass
class SnapshotManifest:
    nodes: Dict[str, Dict[str, Any]]
    edges: List[Dict[str, Any]]


class GraphSnapshotLoader:
    """
    Builds an in-memory Cypher graph from Arbitium graph edge projections.
    """

    DEFAULT_EDGE_TYPES = ["infrastructure_elements:links:infrastructure_elements:_id"]

    def __init__(
        self,
        *,
        graph_controller: Optional[GraphController] = None,
        ontology: Optional[OntologyMapper] = None,
    ):
        self.GRC = graph_controller or GraphController(config=load_config())
        self.ontology = ontology or OntologyMapper.default()

    def load(
        self,
        portfolio: str,
        org: str,
        *,
        edge_types: Optional[Iterable[str]] = None,
        max_edges: int = 50_000,
    ) -> Tuple[Any, SnapshotStats, SnapshotManifest]:
        engine = self._create_engine()
        if engine is None:
            raise RuntimeError(
                "GraphForge is required for Cypher execution. Install with: pip install 'graphforge>=0.4.0'"
            )

        selected_edge_types = [
            str(edge_type).strip()
            for edge_type in (edge_types or self.DEFAULT_EDGE_TYPES)
            if str(edge_type).strip()
        ]
        if not selected_edge_types:
            raise ValueError("At least one edge_type is required to build a graph snapshot")

        node_refs: Dict[str, Any] = {}
        node_attrs: Dict[str, Dict[str, Any]] = {}
        edge_records: List[Dict[str, Any]] = []
        edges_loaded = 0
        stopped_reason: Optional[str] = None

        for edge_type in selected_edge_types:
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
                    if edges_loaded >= max_edges:
                        stopped_reason = "max_edges_reached"
                        break

                    from_id = edge_row.from_node_id
                    to_id = edge_row.to_node_id
                    properties = edge_row.properties if isinstance(edge_row.properties, dict) else {}

                    rel_type = self._resolve_relationship_type(properties, edge_type)
                    edge_props = self._extract_edge_properties(properties)

                    from_ring, _ = self._split_node_id(from_id)
                    to_ring, _ = self._split_node_id(to_id)
                    from_attrs = self._extract_node_attrs(from_id, from_ring, properties, prefix="from.")
                    to_attrs = self._extract_node_attrs(to_id, to_ring, properties, prefix="to.")

                    from_ref = self._ensure_node(engine, node_refs, node_attrs, from_id, from_ring, from_attrs)
                    to_ref = self._ensure_node(engine, node_refs, node_attrs, to_id, to_ring, to_attrs)
                    self._create_relationship(engine, from_ref, to_ref, rel_type, edge_props)
                    edge_records.append(
                        {
                            "from_node_id": from_id,
                            "to_node_id": to_id,
                            "relationship_type": rel_type,
                            "label_forward_raw": properties.get("label_forward"),
                            "storage_edge_type": edge_type,
                            "properties": edge_props,
                        }
                    )
                    edges_loaded += 1

                if stopped_reason or not page.last_evaluated_key:
                    break
                last_key = page.last_evaluated_key

            if stopped_reason:
                break

        stats = SnapshotStats(
            edge_types_scanned=selected_edge_types,
            edges_loaded=edges_loaded,
            nodes_loaded=len(node_refs),
            stopped_reason=stopped_reason,
        )
        manifest = SnapshotManifest(nodes=node_attrs, edges=edge_records)
        return engine, stats, manifest

    @classmethod
    def build_inspection(
        cls,
        manifest: SnapshotManifest,
        *,
        node_limit: int = 25,
        edge_limit: int = 25,
        universal_type: Optional[str] = None,
        provider_type: Optional[str] = None,
        relationship_type: Optional[str] = None,
        node_id_contains: Optional[str] = None,
    ) -> Dict[str, Any]:
        node_limit = max(1, min(int(node_limit), 500))
        edge_limit = max(1, min(int(edge_limit), 500))

        def _matches_node(node_id: str, attrs: Dict[str, Any]) -> bool:
            if universal_type and str(attrs.get("universal_type", "")).lower() != universal_type.strip().lower():
                return False
            if provider_type and str(attrs.get("provider_type", "")).lower() != provider_type.strip().lower():
                return False
            if node_id_contains and node_id_contains.strip().lower() not in node_id.lower():
                return False
            return True

        def _matches_edge(edge: Dict[str, Any]) -> bool:
            if relationship_type and str(edge.get("relationship_type", "")).upper() != relationship_type.strip().upper():
                return False
            if universal_type or provider_type or node_id_contains:
                from_attrs = manifest.nodes.get(str(edge.get("from_node_id", "")), {})
                to_attrs = manifest.nodes.get(str(edge.get("to_node_id", "")), {})
                if universal_type or provider_type or node_id_contains:
                    return _matches_node(str(edge.get("from_node_id", "")), from_attrs) or _matches_node(
                        str(edge.get("to_node_id", "")),
                        to_attrs,
                    )
            return True

        nodes_by_universal_type: Dict[str, int] = {}
        provider_types_seen: Dict[str, int] = {}
        unmapped_provider_types: Set[str] = set()
        edges_by_relationship: Dict[str, int] = {}

        sample_nodes: List[Dict[str, Any]] = []
        for node_id, attrs in manifest.nodes.items():
            universal = str(attrs.get("universal_type") or "Resource")
            nodes_by_universal_type[universal] = nodes_by_universal_type.get(universal, 0) + 1
            provider = attrs.get("provider_type")
            if provider:
                provider_key = str(provider)
                provider_types_seen[provider_key] = provider_types_seen.get(provider_key, 0) + 1
                if universal == "Resource":
                    unmapped_provider_types.add(provider_key)

            if len(sample_nodes) >= node_limit:
                continue
            if not _matches_node(node_id, attrs):
                continue
            sample_nodes.append(
                {
                    "node_id": node_id,
                    "labels": attrs.get("_labels", []),
                    "universal_type": attrs.get("universal_type"),
                    "provider_type": attrs.get("provider_type"),
                    "name": attrs.get("name"),
                    "properties": {
                        key: value
                        for key, value in attrs.items()
                        if key not in {"_labels"}
                    },
                }
            )

        sample_edges: List[Dict[str, Any]] = []
        for edge in manifest.edges:
            rel = str(edge.get("relationship_type") or "UNKNOWN")
            edges_by_relationship[rel] = edges_by_relationship.get(rel, 0) + 1
            if len(sample_edges) >= edge_limit:
                continue
            if not _matches_edge(edge):
                continue
            sample_edges.append(edge)

        return {
            "summary": {
                "total_nodes": len(manifest.nodes),
                "total_edges": len(manifest.edges),
                "nodes_by_universal_type": dict(sorted(nodes_by_universal_type.items())),
                "edges_by_relationship_type": dict(sorted(edges_by_relationship.items())),
                "provider_types_seen": dict(sorted(provider_types_seen.items())),
                "unmapped_provider_types": sorted(unmapped_provider_types),
            },
            "filters": {
                "universal_type": universal_type,
                "provider_type": provider_type,
                "relationship_type": relationship_type,
                "node_id_contains": node_id_contains,
                "node_limit": node_limit,
                "edge_limit": edge_limit,
            },
            "sample_nodes": sample_nodes,
            "sample_edges": sample_edges,
            "returned_nodes": len(sample_nodes),
            "returned_edges": len(sample_edges),
        }

    def _create_engine(self) -> Any:
        try:
            from graphforge import GraphForge
        except ImportError:
            return None
        return GraphForge()

    @staticmethod
    def _split_node_id(node_id: str) -> Tuple[str, str]:
        parts = str(node_id).split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid node id '{node_id}'")
        return parts[0], parts[1]

    def _resolve_relationship_type(self, properties: Dict[str, Any], edge_type: str) -> str:
        label = properties.get("label_forward")
        if isinstance(label, str) and label.strip():
            return self.ontology.canonical_relationship(label.strip())
        return self.ontology.canonical_relationship(edge_type)

    def _extract_edge_properties(self, properties: Dict[str, Any]) -> Dict[str, Any]:
        edge_props: Dict[str, Any] = {}
        raw_props = properties.get("properties")
        if isinstance(raw_props, dict):
            actions = raw_props.get("actions")
            if actions is not None:
                edge_props["actions"] = actions
            for key, value in raw_props.items():
                if key == "actions":
                    continue
                if isinstance(value, (str, int, float, bool)) or value is None:
                    edge_props[key] = value

        qualifiers = properties.get("qualifiers")
        if isinstance(qualifiers, dict):
            for key, value in qualifiers.items():
                if isinstance(value, (str, int, float, bool)) or value is None:
                    edge_props[f"qualifier_{key.replace('.', '_')}"] = value
        return edge_props

    def _extract_node_attrs(
        self,
        node_id: str,
        ring: str,
        properties: Dict[str, Any],
        *,
        prefix: str,
    ) -> Dict[str, Any]:
        attrs: Dict[str, Any] = {"node_id": node_id, "ring": ring}
        projection = properties.get("projection")
        if isinstance(projection, dict):
            for key, value in projection.items():
                if not isinstance(key, str) or not key.startswith(prefix):
                    continue
                field = key[len(prefix) :]
                if field:
                    attrs[field] = value

        provider_type = attrs.get("provider_type")
        attrs["universal_type"] = self.ontology.universal_type_for_provider(
            str(provider_type) if provider_type is not None else None
        )
        return self._json_safe_attrs(attrs)

    def _ensure_node(
        self,
        engine: Any,
        node_refs: Dict[str, Any],
        node_attrs: Dict[str, Dict[str, Any]],
        node_id: str,
        ring: str,
        attrs: Dict[str, Any],
    ) -> Any:
        if node_id in node_refs:
            existing = node_attrs.get(node_id, {})
            merged = {**existing, **attrs}
            if "_labels" not in merged:
                merged["_labels"] = self.ontology.labels_for_node(
                    ring=ring,
                    provider_type=merged.get("provider_type"),
                )
            node_attrs[node_id] = merged
            return node_refs[node_id]

        labels = self.ontology.labels_for_node(ring=ring, provider_type=attrs.get("provider_type"))
        attrs_with_labels = {**attrs, "_labels": labels}
        ref = self._create_node(engine, labels, attrs)
        node_refs[node_id] = ref
        node_attrs[node_id] = attrs_with_labels
        return ref

    @staticmethod
    def _create_node(engine: Any, labels: List[str], attrs: Dict[str, Any]) -> Any:
        if hasattr(engine, "create_node"):
            return engine.create_node(labels if labels else None, **attrs)
        if hasattr(engine, "add_node"):
            primary_label = labels[0] if labels else "Resource"
            ref = engine.add_node(primary_label, **attrs)
            for label in labels[1:]:
                if hasattr(engine, "add_label"):
                    engine.add_label(ref, label)
            return ref
        raise RuntimeError("GraphForge engine missing create_node/add_node")

    @staticmethod
    def _create_relationship(
        engine: Any,
        from_ref: Any,
        to_ref: Any,
        rel_type: str,
        props: Dict[str, Any],
    ) -> None:
        if hasattr(engine, "create_relationship"):
            engine.create_relationship(from_ref, to_ref, rel_type, **props)
            return
        if hasattr(engine, "add_edge"):
            engine.add_edge(from_ref, rel_type, to_ref, **props)
            return
        raise RuntimeError("GraphForge engine missing create_relationship/add_edge")

    @staticmethod
    def _json_safe_attrs(attrs: Dict[str, Any]) -> Dict[str, Any]:
        safe: Dict[str, Any] = {}
        for key, value in attrs.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                safe[key] = value
            elif isinstance(value, list):
                safe[key] = [
                    item
                    for item in value
                    if isinstance(item, (str, int, float, bool)) or item is None
                ]
            elif isinstance(value, dict):
                nested = {
                    nested_key: nested_value
                    for nested_key, nested_value in value.items()
                    if isinstance(nested_value, (str, int, float, bool)) or nested_value is None
                }
                if nested:
                    safe[key] = nested
        return safe
