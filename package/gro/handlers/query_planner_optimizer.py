from __future__ import annotations

from typing import Any, Dict

from gro.handlers.query_parser import QueryParser
from gro.handlers.constraint_extractor import ConstraintExtractor
from gro.handlers.graph_statistics_registry import GraphStatisticsRegistry
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
        self.graph_statistics_registry = GraphStatisticsRegistry()
        self.candidate_plan_generator = CandidatePlanGenerator()
        self.cost_estimator = CostEstimator()
        self.plan_ranker = PlanRanker()
        self.execution_plan_builder = ExecutionPlanBuilder()

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        parsed = self.query_parser.run(payload)
        extracted = self.constraint_extractor.run(
            {
                **payload,
                "query_pattern": parsed["query_pattern"],
            }
        )
        stats = self.graph_statistics_registry.run(
            {
                **payload,
                "query_pattern": parsed["query_pattern"],
            }
        )
        generated = self.candidate_plan_generator.run(
            {
                **payload,
                "query_pattern": parsed["query_pattern"],
                "anchors": extracted["anchors"],
            }
        )
        estimated = self.cost_estimator.run(
            {
                **payload,
                "candidate_plans": generated["candidate_plans"],
                "stats": stats["stats"],
            }
        )
        ranked = self.plan_ranker.run(
            {
                **payload,
                "estimated_plans": estimated["estimated_plans"],
            }
        )
        built = self.execution_plan_builder.run(
            {
                **payload,
                "query_pattern": parsed["query_pattern"],
                "best_plan": ranked["best_plan"],
            }
        )

        return {
            "success": True,
            "component": "query_planner_optimizer",
            "query_pattern": parsed["query_pattern"],
            "stats": stats["stats"],
            "candidate_plans": generated["candidate_plans"],
            "ranked_plans": ranked["ranked_plans"],
            "best_plan": ranked["best_plan"],
            "execution_plan": built["execution_plan"],
            "pipeline": {
                "query_parser": parsed,
                "constraint_extractor": extracted,
                "graph_statistics_registry": stats,
                "candidate_plan_generator": generated,
                "cost_estimator": estimated,
                "plan_ranker": ranked,
                "execution_plan_builder": built,
            },
        }
