from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, Iterable, Optional

from gro.handlers.cypher_engine import CypherEngine
from gro.handlers.graph_snapshot_loader import GraphSnapshotLoader, SnapshotManifest


class CypherQuery:
    """
    Executes cybersecurity-style Cypher queries against an Arbitium graph snapshot.

    Request body:
      {
        "query_text": "MATCH ... RETURN ...",
        "params": { "resource_id": "..." },
        "options": {
          "edge_types": ["infrastructure_elements:links:infrastructure_elements:_id"],
          "max_edges": 50000,
          "reuse_snapshot": false,
          "inspect_only": false,
          "inspect": {
            "node_limit": 25,
            "edge_limit": 25,
            "universal_type": "Function",
            "provider_type": "lambda_function",
            "relationship_type": "GRANTS",
            "node_id_contains": "infra"
          }
        }
      }

    Set options.inspect_only=true to return a sample of loaded snapshot nodes/edges
    without running Cypher. Useful for ontology and projection troubleshooting.
    """

    _SNAPSHOT_CACHE: Dict[str, Dict[str, Any]] = {}

    def __init__(self):
        self.loader = GraphSnapshotLoader()
        self.engine = CypherEngine()

    def _cache_key(self, portfolio: str, org: str, edge_types: Iterable[str]) -> str:
        edge_key = "|".join(sorted(str(edge_type).strip() for edge_type in edge_types))
        return f"{portfolio}::{org}::{edge_key}"

    def _get_or_load_snapshot(
        self,
        *,
        portfolio: str,
        org: str,
        edge_types: Iterable[str],
        max_edges: int,
        reuse_snapshot: bool,
    ) -> tuple[Any, Optional[Dict[str, Any]], Optional[SnapshotManifest], bool]:
        cache_key = self._cache_key(portfolio, org, edge_types)
        cached = self._SNAPSHOT_CACHE.get(cache_key) if reuse_snapshot else None
        if cached:
            return cached["engine"], cached.get("stats"), cached["manifest"], True

        snapshot_engine, stats, manifest = self.loader.load(
            portfolio,
            org,
            edge_types=edge_types,
            max_edges=max_edges,
        )
        if reuse_snapshot:
            self._SNAPSHOT_CACHE[cache_key] = {
                "engine": snapshot_engine,
                "stats": asdict(stats),
                "manifest": manifest,
            }
        return snapshot_engine, asdict(stats), manifest, False

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = payload or {}
        portfolio = str(body.get("portfolio", "")).strip()
        org = str(body.get("org", "")).strip()
        if not portfolio or not org:
            return {
                "success": False,
                "component": "cypher_query",
                "message": "portfolio and org are required",
            }

        options = body.get("options", {})
        if options is not None and not isinstance(options, dict):
            return {
                "success": False,
                "component": "cypher_query",
                "message": "options must be an object when provided",
            }
        options = options or {}

        inspect_only = bool(options.get("inspect_only"))
        query_text = str(body.get("query_text") or body.get("cypher") or "").strip()
        if not inspect_only and not query_text:
            return {
                "success": False,
                "component": "cypher_query",
                "message": "query_text/cypher is required unless options.inspect_only is true",
            }

        params = body.get("params")
        if params is not None and not isinstance(params, dict):
            return {
                "success": False,
                "component": "cypher_query",
                "message": "params must be an object when provided",
            }

        edge_types = options.get("edge_types") or GraphSnapshotLoader.DEFAULT_EDGE_TYPES
        max_edges = int(options.get("max_edges", 50_000))
        reuse_snapshot = bool(options.get("reuse_snapshot", False))

        try:
            snapshot_engine, stats, manifest, cache_hit = self._get_or_load_snapshot(
                portfolio=portfolio,
                org=org,
                edge_types=edge_types,
                max_edges=max_edges,
                reuse_snapshot=reuse_snapshot,
            )

            inspect_options = options.get("inspect", {})
            if inspect_options is not None and not isinstance(inspect_options, dict):
                inspect_options = {}

            if inspect_only:
                inspection = GraphSnapshotLoader.build_inspection(
                    manifest,
                    node_limit=int(inspect_options.get("node_limit", 25)),
                    edge_limit=int(inspect_options.get("edge_limit", 25)),
                    universal_type=inspect_options.get("universal_type"),
                    provider_type=inspect_options.get("provider_type"),
                    relationship_type=inspect_options.get("relationship_type"),
                    node_id_contains=inspect_options.get("node_id_contains"),
                )
                response: Dict[str, Any] = {
                    "success": True,
                    "component": "cypher_query",
                    "mode": "inspect_snapshot",
                    "result": inspection,
                    "meta": {
                        "engine": "graphforge",
                        "cache_hit": cache_hit,
                        "return_format": "snapshot_inspection",
                    },
                }
                if stats is not None:
                    response["meta"]["snapshot"] = stats
                return response

            rows = self.engine.execute(snapshot_engine, query_text, params=params or {})
            response = {
                "success": True,
                "component": "cypher_query",
                "mode": "execute_cypher",
                "query": {
                    "text": query_text,
                    "prepared": self.engine.prepare_query(query_text),
                    "params": params or {},
                },
                "result": {
                    "rows": rows,
                    "row_count": len(rows),
                },
                "meta": {
                    "engine": "graphforge",
                    "cache_hit": cache_hit,
                    "return_format": "rows",
                },
            }
            if stats is not None:
                response["meta"]["snapshot"] = stats
            return response
        except RuntimeError as exc:
            return {
                "success": False,
                "component": "cypher_query",
                "message": str(exc),
                "hint": "Install GraphForge with: pip install 'graphforge>=0.4.0'",
            }
        except Exception as exc:
            return {
                "success": False,
                "component": "cypher_query",
                "message": str(exc),
            }
