# Gro: Graph Query Planner and Optimizer

Gro is an extension that converts a logical graph query into an executable
traversal plan by running a deterministic, handler-based optimization pipeline.

It is implemented as an external extension (not inside `renglo-lib`) so it can
evolve independently and so alternative planners can be added later.

## What Gro does

Given a query pattern (target, constraints, relationships), Gro:

1. normalizes the query structure
2. extracts anchors and traversal constraints
3. computes and persists graph statistics
4. generates candidate traversal plans
5. estimates cost for each plan
6. ranks plans
7. builds the final executable traversal operations

## Point of entry

Primary entrypoint handler:

- `gro/query_planner_optimizer`
- `gro/execute_plan` (default reference executor)

Implementation class:

- `gro.handlers.query_planner_optimizer.QueryPlannerOptimizer`

This is the orchestrator that calls every stage handler in sequence.

## Internal architecture

Gro handlers live in `package/gro/handlers/`:

- `query_parser.py` -> `QueryParser`
- `constraint_extractor.py` -> `ConstraintExtractor`
- `graph_statistics_registry.py` -> `GraphStatisticsRegistry`
- `candidate_plan_generator.py` -> `CandidatePlanGenerator`
- `cost_estimator.py` -> `CostEstimator`
- `plan_ranker.py` -> `PlanRanker`
- `execution_plan_builder.py` -> `ExecutionPlanBuilder`
- `execute_plan.py` -> `ExecutePlan` (execution facade)
- `query_planner_optimizer.py` -> `QueryPlannerOptimizer` (orchestrator)

## Handler sequence (orchestrated flow)

The orchestrator runs this exact sequence:

1. `QueryParser.run(payload)`
2. `ConstraintExtractor.run(payload + query_pattern)`
3. `GraphStatisticsRegistry.run(payload + query_pattern)`
4. `CandidatePlanGenerator.run(payload + query_pattern + anchors)`
5. `CostEstimator.run(payload + candidate_plans + stats)`
6. `PlanRanker.run(payload + estimated_plans)`
7. `ExecutionPlanBuilder.run(payload + query_pattern + best_plan)`

## Stage-by-stage success criteria

Each stage returns `{"success": true, ...}` plus stage-specific output.

### 1) Query Parser

Handler: `gro/query_parser`

Success means:

- `query_pattern` is present and normalized
- `target` is non-empty
- constraints and relationships are normalized into canonical shape

Expected output keys:

- `success`
- `component: "query_parser"`
- `query_pattern`

### 2) Constraint Extractor

Handler: `gro/constraint_extractor`

Success means:

- anchors are extracted from constraints
- property filters are identified
- traversal edges are collected

Expected output keys:

- `success`
- `component: "constraint_extractor"`
- `anchors`
- `property_filters`
- `traversal_edges`

### 3) Graph Statistics Registry

Handler: `gro/graph_statistics_registry`

Success means:

- live stats are computed using `GraphController` and `DataController`
- stats are persisted in Gro rings

Expected output keys:

- `success`
- `component: "graph_statistics_registry"`
- `stats.node_counts`
- `stats.property_cardinality`
- `stats.edge_fanout`
- `persistence` (write results per stats ring)

### 4) Candidate Plan Generator

Handler: `gro/candidate_plan_generator`

Success means:

- one or more candidate plans are produced
- each plan has anchor, edge steps, and traversal depth

Expected output keys:

- `success`
- `component: "candidate_plan_generator"`
- `candidate_plans`

### 5) Cost Estimator

Handler: `gro/cost_estimator`

Success means:

- each candidate plan receives `estimated_cost`
- cost breakdown exists (`candidate_count`, `cumulative_fanout`, `traversal_depth`)

Expected output keys:

- `success`
- `component: "cost_estimator"`
- `estimated_plans`

### 6) Plan Ranker

Handler: `gro/plan_ranker`

Success means:

- plans are sorted by primary and secondary criteria
- best plan is selected

Expected output keys:

- `success`
- `component: "plan_ranker"`
- `ranked_plans`
- `best_plan`

### 7) Execution Plan Builder

Handler: `gro/execution_plan_builder`

Success means:

- best logical plan is converted into executable operations
- output includes `find_nodes`, traversal ops, and filters

Expected output keys:

- `success`
- `component: "execution_plan_builder"`
- `execution_plan`

## Final success criteria (end-to-end)

A successful orchestrated run (`gro/query_planner_optimizer`) returns:

- `success: true`
- normalized `query_pattern`
- computed `stats`
- `candidate_plans`
- `ranked_plans`
- `best_plan`
- final `execution_plan`
- `pipeline` (full stage-by-stage outputs for debugging/inspection)

In short: success at the end means Gro selected one plan and produced executable
operations for graph traversal.

## Example input

```json
{
  "portfolio": "p1",
  "org": "o1",
  "query_pattern": {
    "target": "Hotel",
    "constraints": [
      { "node": "City", "property": "name", "operator": "=", "value": "Rio" },
      { "node": "Review", "property": "stars", "operator": "=", "value": 5 }
    ],
    "relationships": [
      { "from": "Hotel", "edge": "LOCATED_IN", "to": "City" },
      { "from": "Review", "edge": "REVIEWS", "to": "Hotel" }
    ]
  }
}
```

## Example call

Through scheduler handler call route:

- `POST /_schd/{portfolio}/{org}/call/gro/query_planner_optimizer`

Body can include the same `query_pattern` payload above.

## Who runs the plan

Gro does not execute traversal results itself. It produces:

- a selected logical plan (`best_plan`)
- an executable operations list (`execution_plan`)

The component that calls Gro (typically an API/application service) is expected
to pass `execution_plan` to the graph execution layer.

In practical terms:

1. Caller invokes `gro/query_planner_optimizer`
2. Gro returns `execution_plan`
3. Caller executes those operations using graph primitives (`find_nodes`,
   traversal ops, filters, aggregation/ranking if applicable)
4. Caller returns final query results to the user

### Default executor vs custom executors

Gro now includes a **reference execution design** that also works as the
**default executor**:

- handler: `gro/execute_plan`
- class: `ExecutePlan`
- default runtime: `ReferencePlanExecutor`

This creates a clear distinction:

- **Planner handlers** (`query_planner_optimizer`, `execution_plan_builder`) define
  what to run
- **Executor handlers** (`execute_plan`) define how to run it

Custom implementations can replace the default by passing:

- `executor_path: "package.module:ClassName"`

The custom class must expose:

- `execute(payload: dict) -> dict`

## Example output (orchestrator response)

```json
{
  "success": true,
  "component": "query_planner_optimizer",
  "query_pattern": {
    "target": "Hotel",
    "constraints": [
      { "node": "City", "property": "name", "operator": "=", "value": "Rio" },
      { "node": "Review", "property": "stars", "operator": "=", "value": 5 }
    ],
    "relationships": [
      { "from": "Hotel", "to": "City", "edge": "LOCATED_IN" },
      { "from": "Review", "to": "Hotel", "edge": "REVIEWS" }
    ]
  },
  "best_plan": {
    "plan_id": "plan_1",
    "anchor_node": "City",
    "traversal_depth": 2,
    "estimated_cost": 300000
  },
  "execution_plan": [
    {
      "op": "find_nodes",
      "type": "City",
      "filter": { "name": "Rio" }
    },
    {
      "op": "traverse_reverse",
      "edge": "LOCATED_IN",
      "target_type": "Hotel"
    },
    {
      "op": "traverse_reverse",
      "edge": "REVIEWS",
      "target_type": "Review"
    },
    {
      "op": "filter",
      "node": "Review",
      "property": "stars",
      "operator": "=",
      "value": 5
    }
  ],
  "stats": {
    "node_counts": { "Hotel": 1000000, "Review": 100000000, "City": 50000 },
    "property_cardinality": { "City.name=Rio": 1, "Review.stars=5": 30000000 },
    "edge_fanout": {
      "LOCATED_IN": { "avg_fanout": 1200.0 },
      "REVIEWS": { "avg_fanout": 250.0 }
    }
  },
  "pipeline": {
    "query_parser": { "success": true },
    "constraint_extractor": { "success": true },
    "graph_statistics_registry": { "success": true },
    "candidate_plan_generator": { "success": true },
    "cost_estimator": { "success": true },
    "plan_ranker": { "success": true },
    "execution_plan_builder": { "success": true }
  }
}
```

## Example execution call (default reference executor)

```json
{
  "portfolio": "p1",
  "org": "o1",
  "execution_plan": [
    {
      "op": "find_nodes",
      "type": "City",
      "filter": { "name": "Rio" }
    },
    {
      "op": "traverse_reverse",
      "edge": "LOCATED_IN",
      "target_type": "Hotel"
    }
  ]
}
```

Call:

- `POST /_schd/{portfolio}/{org}/call/gro/execute_plan`

Default execution output includes:

- `execution.result.final_node_ids`
- `execution.result.final_documents`
- `execution.trace` (step-level before/after counts)

## Example custom executor call

```json
{
  "portfolio": "p1",
  "org": "o1",
  "execution_plan": [
    { "op": "find_nodes", "type": "City", "filter": { "name": "Rio" } }
  ],
  "executor_name": "fast_graph_executor",
  "executor_path": "my_extension.executors.fast:FastExecutor"
}
```

## Persisted data (blueprints)

Gro persists optimizer stats in these blueprint rings:

- `gro_node_counts` (singleton)
- `gro_property_cardinality` (singleton)
- `gro_edge_fanout` (singleton)

These are used by `CostEstimator` and can also be refreshed periodically by
calling `gro/graph_statistics_registry` from cron jobs.

## Preparing source blueprints for counting

Gro only computes property cardinality for fields explicitly marked as
countable in each source ring blueprint.

### Required field flag

Add this flag to any field you want included in property cardinality stats:

- `countable: true`

If `countable` is missing (or false), Gro skips that field for grouped
property counts.

### Optional value ranges (bucket control)

For discrete/range-limited fields, define allowed values with:

- `count_ranges: [ ... ]`

When `count_ranges` is present:

- values in the list are counted directly
- values outside the list are grouped into `__other__`

This is useful for controlled domains like ratings.

### Example: `Review.stars` as bounded countable field

```json
{
  "name": "stars",
  "type": "number",
  "countable": true,
  "count_ranges": [0, 1, 2, 3, 4, 5]
}
```

### Example: `City.name` as open countable field

```json
{
  "name": "name",
  "type": "string",
  "countable": true
}
```

No `count_ranges` means Gro counts all observed values as keys.

### What gets stored

After registry execution:

- `gro_node_counts`: one doc per node type (`node_type`, `count`)
- `gro_property_cardinality`: one doc per sampled ring
  (`node_type`, `property_counts`)
- `gro_edge_fanout`: one doc per edge label (`edge_type`, fanout metrics)

All these docs are scoped to the current `portfolio/org`.

### Practical recommendation

Start with a small set of high-impact countable fields (anchors and frequent
filters), then expand gradually. This keeps cardinality docs compact and makes
staleness refresh handlers cheaper to run.

## Installation

From `extensions/gro`:

1. Install package:

   ```bash
   pip install -e package/
   ```

2. Upload Gro blueprints:

   ```bash
   python installer/upload_blueprints.py <env> --aws-profile <profile> --aws-region <region>
   ```

3. Ensure runtime has required config for data/graph access (same config used
   by `DataController` and `GraphController`).

4. Invoke handlers via scheduler endpoints (`/_schd/.../call/gro/...`) or from
   job docs and cron rules.

## Notes

- Every logic component is implemented as a handler class with a `run(payload)`.
- The orchestrator is intentionally thin and deterministic.
- A future alternative planner can be added as another extension without
  changing Gro internals.
