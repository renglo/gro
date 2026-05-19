from __future__ import annotations

from typing import Any, Dict, List

from renglo.auth.auth_controller import AuthController
from renglo.common import load_config


class GroOnboardings:
    """
    Installs Gro in an existing portfolio.
    """

    def __init__(self):
        config = load_config()
        self.AUC = AuthController(config=config)

    def _create_tool(self, portfolio: str) -> Dict[str, Any]:
        kwargs = {
            "name": "Gro",
            "handle": "gro",
            "portfolio_id": portfolio,
        }
        response = self.AUC.create_entity("tool", **kwargs)
        return {
            "success": bool(response.get("success")),
            "action": "create_tool",
            "input": kwargs,
            "output": response,
        }

    def _refresh_tree(self) -> Dict[str, Any]:
        response = self.AUC.refresh_tree()
        return {
            "success": bool(response.get("success")),
            "action": "refresh_tree",
            "input": {},
            "output": response,
        }

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload = payload or {}
        portfolio = str(payload.get("portfolio", "")).strip()
        if not portfolio:
            return {"success": False, "message": "No portfolio selected", "input": payload}

        results: List[Dict[str, Any]] = []

        step_tool = self._create_tool(portfolio)
        results.append(step_tool)
        if not step_tool["success"]:
            return {"success": False, "message": "Could not install Gro tool", "input": payload, "output": results}

        step_tree = self._refresh_tree()
        results.append(step_tree)
        if not step_tree["success"]:
            return {"success": False, "message": "Gro installed but tree refresh failed", "input": payload, "output": results}

        return {
            "success": True,
            "message": "Gro onboarding completed",
            "input": payload,
            "output": results,
        }
