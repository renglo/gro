"""
Gro handlers package.
"""

__version__ = "1.0.0"

from gro.handlers.query_parser import QueryParser
from gro.handlers.constraint_extractor import ConstraintExtractor
from gro.handlers.graph_statistics_registry import GraphStatisticsRegistry
from gro.handlers.graph_statistics_summary import GraphStatisticsSummary
from gro.handlers.candidate_plan_generator import CandidatePlanGenerator
from gro.handlers.cost_estimator import CostEstimator
from gro.handlers.plan_ranker import PlanRanker
from gro.handlers.execution_plan_builder import ExecutionPlanBuilder
from gro.handlers.execute_plan import ExecutePlan
from gro.handlers.gro_onboardings import GroOnboardings
from gro.handlers.initialize_extension import InitializeExtension
from gro.handlers.query_planner_optimizer import QueryPlannerOptimizer
from gro.handlers.graph_query_v1 import GraphQueryV1
from gro.handlers.natural_language_query import NaturalLanguageQuery
from gro.handlers.cypher_query import CypherQuery

__all__ = [
    "QueryParser",
    "ConstraintExtractor",
    "GraphStatisticsRegistry",
    "GraphStatisticsSummary",
    "CandidatePlanGenerator",
    "CostEstimator",
    "PlanRanker",
    "ExecutionPlanBuilder",
    "ExecutePlan",
    "GroOnboardings",
    "InitializeExtension",
    "QueryPlannerOptimizer",
    "GraphQueryV1",
    "NaturalLanguageQuery",
    "CypherQuery",
    "get_handler",
    "list_handlers",
]

HANDLERS = {
    "query_parser": QueryParser,
    "constraint_extractor": ConstraintExtractor,
    "graph_statistics_registry": GraphStatisticsRegistry,
    "graph_statistics_summary": GraphStatisticsSummary,
    "candidate_plan_generator": CandidatePlanGenerator,
    "cost_estimator": CostEstimator,
    "plan_ranker": PlanRanker,
    "execution_plan_builder": ExecutionPlanBuilder,
    "execute_plan": ExecutePlan,
    "gro_onboardings": GroOnboardings,
    "initialize_extension": InitializeExtension,
    "query_planner_optimizer": QueryPlannerOptimizer,
    "graph_query_v1": GraphQueryV1,
    "natural_language_query": NaturalLanguageQuery,
    "cypher_query": CypherQuery,
}


def get_handler(handler_name: str):
    if handler_name not in HANDLERS:
        available = ", ".join(HANDLERS.keys())
        raise KeyError(
            f"Handler '{handler_name}' not found. Available handlers: {available}"
        )
    return HANDLERS[handler_name]()


def list_handlers():
    return list(HANDLERS.keys())
