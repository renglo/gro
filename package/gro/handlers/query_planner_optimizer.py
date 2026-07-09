from __future__ import annotations

from typing import Any, Dict

from gro.handlers.query_parser import QueryParser
from gro.handlers.constraint_extractor import ConstraintExtractor
from gro.handlers.candidate_plan_generator import CandidatePlanGenerator
from gro.handlers.cost_estimator import CostEstimator
from gro.handlers.plan_ranker import PlanRanker
from gro.handlers.execution_plan_builder import ExecutionPlanBuilder


class QueryPlannerOptimizer:
    """
    End-to-end orchestrator for the Gro query planner and optimizer pipeline.
    """

    def __init__(self):
        self.query_parser = QueryParser()
        self.constraint_extractor = ConstraintExtractor()
        self.candidate_plan_generator = CandidatePlanGenerator()
        self.cost_estimator = CostEstimator()
        self.plan_ranker = PlanRanker()
        self.execution_plan_builder = ExecutionPlanBuilder()

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        parsed = self.query_parser.run(payload)
        shared_payload: Dict[str, Any] = {
            **payload,
            "query_pattern": parsed["query_pattern"],
        }
        if isinstance(parsed.get("force_anchor"), dict):
            shared_payload["force_anchor"] = parsed["force_anchor"]
        if isinstance(parsed.get("return_spec"), dict):
            shared_payload["return_spec"] = parsed["return_spec"]
        if isinstance(parsed.get("query_v1"), dict):
            shared_payload["query_v1"] = parsed["query_v1"]
        extracted = self.constraint_extractor.run(
            shared_payload
        )
        generated = self.candidate_plan_generator.run(
            {
                **shared_payload,
                "query_pattern": parsed["query_pattern"],
                "anchors": extracted["anchors"],
            }
        )
        if not generated.get("success"):
            return {
                "success": False,
                "component": "query_planner_optimizer",
                "message": generated.get("message", "Candidate plan generation failed"),
                "pipeline": {
                    "query_parser": parsed,
                    "constraint_extractor": extracted,
                    "candidate_plan_generator": generated,
                },
            }

        estimated = self.cost_estimator.run(
            {
                **shared_payload,
                "candidate_plans": generated["candidate_plans"],
            }
        )
        ranked = self.plan_ranker.run(
            {
                **shared_payload,
                "estimated_plans": estimated["estimated_plans"],
            }
        )
        built = self.execution_plan_builder.run(
            {
                **shared_payload,
                "query_pattern": parsed["query_pattern"],
                "best_plan": ranked["best_plan"],
            }
        )

        response: Dict[str, Any] = {
            "success": True,
            "component": "query_planner_optimizer",
            "query_pattern": parsed["query_pattern"],
            "stats": estimated.get("stats", {}),
            "candidate_plans": generated["candidate_plans"],
            "ranked_plans": ranked["ranked_plans"],
            "best_plan": ranked["best_plan"],
            "execution_plan": built["execution_plan"],
            "pipeline": {
                "query_parser": parsed,
                "constraint_extractor": extracted,
                "candidate_plan_generator": generated,
                "cost_estimator": estimated,
                "plan_ranker": ranked,
                "execution_plan_builder": built,
            },
        }
        if parsed.get("query_v1"):
            response["query_v1"] = parsed["query_v1"]
        if parsed.get("return_spec"):
            response["return_spec"] = parsed["return_spec"]
        if parsed.get("input_kind"):
            response["input_kind"] = parsed["input_kind"]
        return response
