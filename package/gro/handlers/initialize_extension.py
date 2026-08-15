from typing import Any, Dict

from renglo.auth.auth_controller import AuthController
from renglo.blueprint.extension_blueprints import ensure_extension_blueprints
from renglo.common import load_config


class InitializeExtension:
    """
    Per-org setup when a team is assigned to Gro.
    """

    def __init__(self):
        config = load_config()
        self.config = config
        self.AUC = AuthController(config=config)

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload = payload or {}
        org = str(payload.get("org") or "").strip()
        if not org:
            return {
                "success": False,
                "action": "initialize_extension",
                "message": "org is required",
                "input": payload,
            }

        results = [self.ensure_blueprints()]
        if not results[0].get("success"):
            return {
                "success": False,
                "action": "initialize_extension",
                "message": "Gro initialization failed",
                "input": payload,
                "output": results,
            }
        return {
            "success": True,
            "action": "initialize_extension",
            "message": "Gro initialized",
            "input": payload,
            "output": results,
        }

    def ensure_blueprints(self):
        return ensure_extension_blueprints(self.config, module_file=__file__)
