from __future__ import annotations

from typing import Any, Dict, List


class PlanRanker:
    """
    Sorts candidate plans by estimated cost and secondary tie-breakers.
    """

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        estimated_plans: List[Dict[str, Any]] = payload.get("estimated_plans", [])
        ranked_plans = sorted(
            estimated_plans,
            key=lambda plan: (
                float(plan.get("estimated_cost", 10**18)),
                int(plan.get("traversal_depth", 10**6)),
                float(plan.get("cost_breakdown", {}).get("intermediate_explosion", 10**18)),
            ),
        )

        best_plan = ranked_plans[0] if ranked_plans else None
        return {
            "success": True,
            "component": "plan_ranker",
            "ranked_plans": ranked_plans,
            "best_plan": best_plan,
        }
