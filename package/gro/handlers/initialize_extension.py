from typing import Any, Dict

from renglo.auth.auth_controller import AuthController
from renglo.common import load_config


class InitializeExtension:
    """
    Per-org setup when a team is assigned to Gro.

    Gro has no singleton config today. Add org-scoped steps here as needed.
    """

    def __init__(self):
        config = load_config()
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
        return {
            "success": True,
            "action": "initialize_extension",
            "message": "Gro has no org initialization steps",
            "input": payload,
            "output": [],
        }
