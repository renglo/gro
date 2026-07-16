Gro Query Schema v1 (Draft)
This v1 is designed for your current runtime model:

graph-only execution
filter only on projected fields
return node IDs / edge IDs / paths (no hydration by default)


1) Top-level shape
{
  "version": "1.0",
  "match": { ... },
  "where": { ... },
  "return": { ... },
  "options": { ... }
}
Required
version
match
return
Optional
where
options


2) match (graph pattern declaration)
For v1, keep it simple: one edge pattern (single-hop). Multi-hop can be v1.1.

{
  "edge_type": "infrastructure_elements:links:infrastructure_elements:_id",
  "from": {
    "ring": "infrastructure_elements",
    "alias": "a"
  },
  "to": {
    "ring": "infrastructure_elements",
    "alias": "b"
  },
  "direction": "outgoing"
}
Fields
edge_type (string, required)
from (object, required)
ring (string, required)
alias (string, optional, default "from")
to (object, required)
ring (string, required)
alias (string, optional, default "to")
direction (enum, optional, default "outgoing")
"outgoing": from -> to
"incoming": to -> from
"either": match either direction (executor may evaluate both)


3) where (projection-only predicates)
where can include endpoint-scoped filters and edge-level filters.

{
  "from": {
    "provider_type": { "op": "=", "value": "subnet" },
    "provider": { "op": "=", "value": "aws" }
  },
  "to": {
    "provider_type": { "op": "=", "value": "vpc" }
  },
  "edge": {
    "extras.to.universal_domain": { "op": "=", "value": "network" }
  }
}
Rules
from.<field> and to.<field> must be present in edge projection schema for this edge_type.
edge.<field> can target edge fields (attributes.*, extras.*, etc.) that exist in edge row.
No document-only fields allowed.
Unsupported field -> validation error.
Supported operators (v1)
"="
"!="
"in"
"not_in"
"exists"
"not_exists"
(Keep >, <, >=, <= for v1.1 unless you’re sure all projected types are normalized.)



4) return (explicit output contract)
{
  "kind": "node_ids",
  "side": "from",
  "distinct": true
}
Fields
kind (enum, required)
"node_ids" (default v1 target)
"edges"
"pairs" (from/to tuples)
"paths" (reserved, single-hop in v1)
side (enum, optional, required when kind=node_ids)
"from", "to", "both"
distinct (bool, optional, default true)
limit (int, optional)
offset (int, optional)


5) options (execution + planner hints)
{
  "mode": "graph_only",
  "strict_projection": true,
  "prefer_direction": "auto",
  "timeout_ms": 5000,
  "trace": true
}
Fields
mode (enum, default "graph_only")
v1 allowed: "graph_only" only
strict_projection (bool, default true)
if true, unknown fields fail validation
prefer_direction (enum, default "auto")
"auto", "outgoing", "incoming"
timeout_ms (int, optional)
trace (bool, default false) include counts and chosen direction


6) Validation contract (important)
Before planning/execution:

edge_type must exist in graph metadata.
from.ring and to.ring must match the edge-type domain/codomain (or be compatible if either).
all where.from and where.to fields must be projected for this edge_type.
all operators must be supported.
return.kind/node_ids requires return.side.
Fail fast with typed errors (no silent fallback).


7) Response shape (v1)
{
  "success": true,
  "component": "graph_query_v1",
  "query": { ...normalized_query... },
  "result": {
    "node_ids": ["infrastructure_elements/abc", "infrastructure_elements/def"]
  },
  "meta": {
    "matched_edges": 2111,
    "returned_count": 2,
    "direction_resolved": "incoming"
  },
  "trace": {
    "stages": [
      { "name": "edge_scan", "count": 2111 },
      { "name": "where_filter", "count": 55 },
      { "name": "return_project", "count": 2 }
    ]
  }
}


8) Example for your subnet↔vpc case
{
  "version": "1.0",
  "match": {
    "edge_type": "infrastructure_elements:links:infrastructure_elements:_id",
    "from": { "ring": "infrastructure_elements", "alias": "subnet_side" },
    "to": { "ring": "infrastructure_elements", "alias": "vpc_side" },
    "direction": "outgoing"
  },
  "where": {
    "from": {
      "provider_type": { "op": "=", "value": "subnet" }
    },
    "to": {
      "provider_type": { "op": "=", "value": "vpc" }
    }
  },
  "return": {
    "kind": "node_ids",
    "side": "from",
    "distinct": true
  },
  "options": {
    "mode": "graph_only",
    "strict_projection": true,
    "trace": true
  }
}


That explicitly means:
return subnet node IDs where subnet -> vpc via this edge type.




9) Multi Hop

 Scalable shape: pattern as nodes + relationships
Instead of one match.edge_type, define:

{
  "version": "1.1",
  "nodes": [
    { "id": "subnet", "ring": "infrastructure_elements", "where": { "provider_type": { "op": "=", "value": "subnet" } } },
    { "id": "vpc", "ring": "infrastructure_elements", "where": { "provider_type": { "op": "=", "value": "vpc" } } },
    { "id": "acl", "ring": "infrastructure_elements", "where": { "provider_type": { "op": "=", "value": "network_acl" } } }
  ],
  "edges": [
    { "id": "e1", "from": "subnet", "to": "vpc", "edge_type": "infrastructure_elements:links:infrastructure_elements:_id", "direction": "outgoing" },
    { "id": "e2", "from": "subnet", "to": "acl", "edge_type": "infrastructure_elements:links:infrastructure_elements:_id", "direction": "outgoing" }
  ],
  "return": { "kind": "bindings", "nodes": ["subnet", "vpc", "acl"] }
}
This is graph-native and equivalent to multiple joins.

Multi-hop queries
Represent hops as chained edges across variables.

Example: Subnet -> RouteTable -> VPC (3 nodes, 2 hops):

{
  "nodes": [
    { "id": "s", "ring": "infrastructure_elements", "where": { "provider_type": { "op": "=", "value": "subnet" } } },
    { "id": "rt", "ring": "infrastructure_elements", "where": { "provider_type": { "op": "=", "value": "route_table" } } },
    { "id": "v", "ring": "infrastructure_elements", "where": { "provider_type": { "op": "=", "value": "vpc" } } }
  ],
  "edges": [
    { "from": "s", "to": "rt", "edge_type": "infrastructure_elements:links:infrastructure_elements:_id", "direction": "outgoing" },
    { "from": "rt", "to": "v", "edge_type": "infrastructure_elements:links:infrastructure_elements:_id", "direction": "outgoing" }
  ],
  "return": { "kind": "node_ids", "side": "s" }
}
Branching (multiple joins)
Branching is just multiple edges sharing a variable (star/join point), like above where subnet connects to both vpc and acl.

For larger branch patterns:

return.kind = "bindings" gives tuple-like rows ({subnet, vpc, acl, ...})
return.kind = "node_ids" can project one side only (subnet) with distinct.
What to add for real scalability
To avoid combinatorial explosion, schema should include planner hints:

options.max_hops (global safety)
options.max_results
options.join_order (auto default)
options.anchor (preferred start node var)
per-edge selectivity_hint (optional)
per-node required: true/false (future OPTIONAL MATCH semantics)
Also important: return model
Support these return kinds:

node_ids (single side)
bindings (join rows by var name)
edges (matched edge ids/types)
paths (ordered hops for explainability)
Without bindings, branching results are hard to interpret.

