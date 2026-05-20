# Productora Query Catalog for Gro

This file lists practical Productora graph queries and their copy/paste JSON payloads for:

- `POST /_schd/{portfolio}/{org}/call/gro/execute_plan`

The `gro/execute_plan` handler accepts a `query_pattern`, runs the planner, then executes using the default reference executor.

## How to use

1. Copy one request body below.
2. Replace placeholder values (for example `<project_id>`, `<delivery_id>`).
3. `POST` to `/_schd/{portfolio}/{org}/call/gro/execute_plan` (or another `gro/*` handler). The path supplies `portfolio` and `org`; do not put them in the JSON body.

Each example is the full scheduler request body. The only top-level field required for planning is `query_pattern`.

---

## Productora edge types (important)

Use these edge strings in `relationships[*].edge`:

- `productora_candidates:talent_id:productora_talent:_id`
- `productora_candidates:request_id:productora_talent_request:_id`
- `productora_candidates:delivery_id:productora_deliveries:_id`
- `productora_talent_request:project:productora_project:_id`
- `productora_deliveries:talent_request:productora_talent_request:_id`

---

## 1) Candidates for a specific project

General idea:
- Anchor on `productora_talent_request.project`
- Traverse to `productora_candidates` through `request_id`

```json
{
  "query_pattern": {
    "target": "productora_candidates",
    "constraints": [
      {
        "node": "productora_talent_request",
        "property": "project",
        "operator": "=",
        "value": "<project_id>"
      }
    ],
    "relationships": [
      {
        "from": "productora_candidates",
        "edge": "productora_candidates:request_id:productora_talent_request:_id",
        "to": "productora_talent_request"
      }
    ]
  }
}
```

## 2) Candidates submitted to a delivery

General idea:
- Filter candidate docs directly by `delivery_id`

```json
{
  "query_pattern": {
    "target": "productora_candidates",
    "constraints": [
      {
        "node": "productora_candidates",
        "property": "delivery_id",
        "operator": "=",
        "value": "<delivery_id>"
      }
    ],
    "relationships": []
  }
}
```

## 3) Talent requests for a project

General idea:
- Filter requests by `project`

```json
{
  "query_pattern": {
    "target": "productora_talent_request",
    "constraints": [
      {
        "node": "productora_talent_request",
        "property": "project",
        "operator": "=",
        "value": "<project_id>"
      }
    ],
    "relationships": []
  }
}
```

## 4) Deliveries for a talent request

General idea:
- Filter deliveries by `talent_request`

```json
{
  "query_pattern": {
    "target": "productora_deliveries",
    "constraints": [
      {
        "node": "productora_deliveries",
        "property": "talent_request",
        "operator": "=",
        "value": "<request_id>"
      }
    ],
    "relationships": []
  }
}
```

## 5) Candidates for a specific talent

General idea:
- Filter candidates by `talent_id`

```json
{
  "query_pattern": {
    "target": "productora_candidates",
    "constraints": [
      {
        "node": "productora_candidates",
        "property": "talent_id",
        "operator": "=",
        "value": "<talent_id>"
      }
    ],
    "relationships": []
  }
}
```

## 6) Talent involved in a project (multi-hop)

General idea:
- Filter request by project
- Traverse request <- candidates -> talent

```json
{
  "query_pattern": {
    "target": "productora_talent",
    "constraints": [
      {
        "node": "productora_talent_request",
        "property": "project",
        "operator": "=",
        "value": "<project_id>"
      }
    ],
    "relationships": [
      {
        "from": "productora_candidates",
        "edge": "productora_candidates:request_id:productora_talent_request:_id",
        "to": "productora_talent_request"
      },
      {
        "from": "productora_candidates",
        "edge": "productora_candidates:talent_id:productora_talent:_id",
        "to": "productora_talent"
      }
    ]
  }
}
```

## 7) Requests by gender

General idea:
- Segment requests using `gender`

```json
{
  "query_pattern": {
    "target": "productora_talent_request",
    "constraints": [
      {
        "node": "productora_talent_request",
        "property": "gender",
        "operator": "=",
        "value": "female"
      }
    ],
    "relationships": []
  }
}
```

## 8) Requests by nationality bucket

General idea:
- Segment by `nationality` field values (`1` Mexico, `0` Non Mexico)

```json
{
  "query_pattern": {
    "target": "productora_talent_request",
    "constraints": [
      {
        "node": "productora_talent_request",
        "property": "nationality",
        "operator": "=",
        "value": "1"
      }
    ],
    "relationships": []
  }
}
```

## 9) Requests by age bucket

General idea:
- Use normalized `age_bucket` (added for countability)

```json
{
  "query_pattern": {
    "target": "productora_talent_request",
    "constraints": [
      {
        "node": "productora_talent_request",
        "property": "age_bucket",
        "operator": "=",
        "value": "25-34"
      }
    ],
    "relationships": []
  }
}
```

## 10) Requests by budget bucket

General idea:
- Use normalized `budget_bucket` (low/mid/high/premium)

```json
{
  "query_pattern": {
    "target": "productora_talent_request",
    "constraints": [
      {
        "node": "productora_talent_request",
        "property": "budget_bucket",
        "operator": "=",
        "value": "high"
      }
    ],
    "relationships": []
  }
}
```

## 11) Talent by ethnicity

General idea:
- Filter talent profiles by `ethnicity`

```json
{
  "query_pattern": {
    "target": "productora_talent",
    "constraints": [
      {
        "node": "productora_talent",
        "property": "ethnicity",
        "operator": "=",
        "value": "<ethnicity_value>"
      }
    ],
    "relationships": []
  }
}
```

## 12) Talent by availability status

General idea:
- Use normalized `availability_status`

```json
{
  "query_pattern": {
    "target": "productora_talent",
    "constraints": [
      {
        "node": "productora_talent",
        "property": "availability_status",
        "operator": "=",
        "value": "available"
      }
    ],
    "relationships": []
  }
}
```

## 13) Candidates by pipeline status

General idea:
- Query candidate funnel stage via normalized `status`

```json
{
  "query_pattern": {
    "target": "productora_candidates",
    "constraints": [
      {
        "node": "productora_candidates",
        "property": "status",
        "operator": "=",
        "value": "submitted"
      }
    ],
    "relationships": []
  }
}
```

## 14) Deliveries by month

General idea:
- Use normalized `delivery_month` for calendar aggregation windows

```json
{
  "query_pattern": {
    "target": "productora_deliveries",
    "constraints": [
      {
        "node": "productora_deliveries",
        "property": "delivery_month",
        "operator": "=",
        "value": "2026-05"
      }
    ],
    "relationships": []
  }
}
```

## 15) Requests due in a month

General idea:
- Use normalized `deadline_month`

```json
{
  "query_pattern": {
    "target": "productora_talent_request",
    "constraints": [
      {
        "node": "productora_talent_request",
        "property": "deadline_month",
        "operator": "=",
        "value": "2026-06"
      }
    ],
    "relationships": []
  }
}
```

## 16) Project -> requests -> candidates by request gender

General idea:
- Filter requests by project + gender
- Pull connected candidates

```json
{
  "query_pattern": {
    "target": "productora_candidates",
    "constraints": [
      {
        "node": "productora_talent_request",
        "property": "project",
        "operator": "=",
        "value": "<project_id>"
      },
      {
        "node": "productora_talent_request",
        "property": "gender",
        "operator": "=",
        "value": "male"
      }
    ],
    "relationships": [
      {
        "from": "productora_candidates",
        "edge": "productora_candidates:request_id:productora_talent_request:_id",
        "to": "productora_talent_request"
      }
    ]
  }
}
```

---

## Notes

- Request bodies must use a top-level `query_pattern` object (not a bare `target` / `constraints` object, and not `portfolio` / `org` in the body).
- These payloads are planner inputs, not prebuilt `execution_plan` payloads.
- Some analytics-style queries (e.g. "top N", anti-joins like "requests without deliveries") require post-processing over results.
- Keep field values aligned with your controlled vocab (`status`, `age_bucket`, `budget_bucket`, `availability_status`) for reliable counts.
