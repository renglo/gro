# Gro Graph Query v1 - Examples

This guide shows how to query the Renglo graph through Gro using:

- **Gro Query Schema v1** (JSON)
- **Cypher-like query text** (compiled by `query_parser`)

The execution path is graph-only:

- traversal uses graph edges
- filtering uses edge projections / edge attributes
- results return node ids (no document hydration)

---

## Handler

Use:

- `POST /_schd/{portfolio}/{org}/call/gro/graph_query_v1`

You can also call:

- `POST /_schd/{portfolio}/{org}/call/gro/execute_plan`

with the same input. `graph_query_v1` wraps `execute_plan` and formats a v1-style response.

---



## 1) JSON v1 - Subnets connected to VPCs



### Request body

```json
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
```



### Meaning

- Match `subnet -> vpc` over the selected edge type.
- Return only subnet node ids (`return.side = from`).

---



## 2) JSON v1 - Incoming direction

If your pattern is logically from VPC to subnet, but stored edges are subnet -> vpc, use `incoming`:

```json
{
  "version": "1.0",
  "match": {
    "edge_type": "infrastructure_elements:links:infrastructure_elements:_id",
    "from": { "ring": "infrastructure_elements", "alias": "vpc_side" },
    "to": { "ring": "infrastructure_elements", "alias": "subnet_side" },
    "direction": "incoming"
  },
  "where": {
    "from": {
      "provider_type": { "op": "=", "value": "vpc" }
    },
    "to": {
      "provider_type": { "op": "=", "value": "subnet" }
    }
  },
  "return": {
    "kind": "node_ids",
    "side": "to",
    "distinct": true
  }
}
```

---



## 3) JSON v1 - Edge predicates

Filter on edge fields (`qualifiers.*`, `properties.*`, `projection.*`, etc.):

```json
{
  "version": "1.0",
  "match": {
    "edge_type": "infrastructure_elements:links:infrastructure_elements:_id",
    "from": { "ring": "infrastructure_elements" },
    "to": { "ring": "infrastructure_elements" },
    "direction": "outgoing"
  },
  "where": {
    "from": {
      "provider_type": { "op": "=", "value": "subnet" }
    },
    "edge": {
      "qualifiers.to.universal_domain": { "op": "=", "value": "network" }
    }
  },
  "return": {
    "kind": "node_ids",
    "side": "to",
    "distinct": true
  }
}
```

---



## 4) Cypher-like input



### Request body



Inline props style
```json

{

  "query_text": "MATCH (s:infrastructure_elements {provider_type:'subnet'})-[:infrastructure_elements:links:infrastructure_elements:_id]->(v:infrastructure_elements {provider_type:'vpc'}) RETURN s"

}
```

WHERE style + relationship variable + LIMIT
```json
{

  "query_text": "MATCH (s:infrastructure_elements)-[r:infrastructure_elements:links:infrastructure_elements:_id]->(v:infrastructure_elements) WHERE s.provider_type = 'subnet' AND v.provider_type = 'vpc' RETURN s LIMIT 50;"

}
````


### Notes

- Current support is a **single-hop subset**:
  - one `MATCH (...) -[:EDGE]-> (...)`
  - one `RETURN` alias
- It is compiled into JSON v1 internally.

---



## 5) Response shape (`graph_query_v1`)

```json
{
  "success": true,
  "component": "graph_query_v1",
  "query": {
    "version": "1.0",
    "match": { "...": "..." },
    "where": { "...": "..." },
    "return": { "kind": "node_ids", "side": "from", "distinct": true },
    "options": { "trace": true }
  },
  "result": {
    "node_ids": [
      "infrastructure_elements/012fceae-943d-47eb-89f8-f38bdcf5ebf3"
    ]
  },
  "meta": {
    "returned_count": 1,
    "direction_resolved": "incoming"
  },
  "trace": {
    "stages": [
      {
        "step": 1,
        "op": "find_nodes",
        "before_count": 0,
        "after_count": 17
      }
    ]
  },
  "execution_plan": [
    {
      "op": "find_nodes",
      "type": "infrastructure_elements",
      "filter": { "provider_type": "vpc" }
    },
    {
      "op": "traverse_auto",
      "edge": "infrastructure_elements:links:infrastructure_elements:_id",
      "target_type": "infrastructure_elements"
    },
    {
      "op": "filter",
      "node": "infrastructure_elements",
      "property": "provider_type",
      "operator": "=",
      "value": "subnet"
    }
  ]
}
```

---



## 6) Supported operators (v1)

- `=`
- `!=`
- `in`
- `not_in`
- `exists`
- `not_exists`

---



## 7) Current v1 limits

- `return.kind` currently supports `node_ids` only.
- `return.side=both` is not yet supported.
- Multi-hop and branching patterns are not yet implemented in this handler.

---



## 8) Quick troubleshooting

- **"match.edge_type is required"**: missing edge type in `match`.
- **"return.side must be from, to, or both"**: invalid return side.
- **"find_nodes requires a subsequent traverse operation in graph-only mode"**:
the execution plan cannot fall back to ring scans.
- Empty `node_ids` usually means:
  - pattern is valid but no edge instances match current projections/filters, or
  - direction/side doesn't align with stored edges.

