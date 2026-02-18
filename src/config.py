"""
StoryVault Configuration Manager
Manages config.json and vault-level state.
"""

import json
import os

CONFIG_TEMPLATE = {
    "current_project": None,
    "vault_path": "StoryVault",
    "openai_api_key": None,
    "model": "gpt-4o-mini",
    "token_tracking": {
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "total_cost": 0.0,
    },
}

VAULT_DIRS = ["Projects", "Agents", "Prompts", "Templates", "System"]


class Config:
    def __init__(self, base_path=None):
        self.base_path = base_path or os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        self.vault_path = os.path.join(self.base_path, "StoryVault")
        self.config_path = os.path.join(self.vault_path, "config.json")
        self._ensure_vault()
        self._data = self._load()

    # ------------------------------------------------------------------ #
    # Vault initialisation
    # ------------------------------------------------------------------ #

    def _ensure_vault(self):
        os.makedirs(self.vault_path, exist_ok=True)
        for folder in VAULT_DIRS:
            os.makedirs(os.path.join(self.vault_path, folder), exist_ok=True)

    # ------------------------------------------------------------------ #
    # Load / save
    # ------------------------------------------------------------------ #

    def _load(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                stored = json.load(f)
            # Merge in any new template keys
            merged = CONFIG_TEMPLATE.copy()
            merged.update(stored)
            # Merge nested token_tracking
            tt = CONFIG_TEMPLATE["token_tracking"].copy()
            tt.update(stored.get("token_tracking", {}))
            merged["token_tracking"] = tt
            return merged
        data = {k: v for k, v in CONFIG_TEMPLATE.items()}
        self._save(data)
        return data

    def _save(self, data=None):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data or self._data, f, indent=2)

    # ------------------------------------------------------------------ #
    # Generic accessors
    # ------------------------------------------------------------------ #

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value
        self._save()

    # ------------------------------------------------------------------ #
    # Properties
    # ------------------------------------------------------------------ #

    @property
    def current_project(self):
        return self._data.get("current_project")

    @current_project.setter
    def current_project(self, value):
        self._data["current_project"] = value
        self._save()

    @property
    def api_key(self):
        """Environment variable takes priority over stored value."""
        return os.environ.get("OPENAI_API_KEY") or self._data.get("openai_api_key")

    @api_key.setter
    def api_key(self, value):
        self._data["openai_api_key"] = value
        self._save()

    @property
    def model(self):
        return self._data.get("model", "gpt-4o-mini")

    @property
    def token_tracking(self):
        return self._data.get(
            "token_tracking",
            {"total_prompt_tokens": 0, "total_completion_tokens": 0, "total_cost": 0.0},
        )

    # ------------------------------------------------------------------ #
    # Token tracking
    # ------------------------------------------------------------------ #

    def add_tokens(self, prompt_tokens: int, completion_tokens: int, cost: float):
        t = self.token_tracking
        t["total_prompt_tokens"]     += prompt_tokens
        t["total_completion_tokens"] += completion_tokens
        t["total_cost"]              += cost
        self._data["token_tracking"] = t
        self._save()

    # ------------------------------------------------------------------ #
    # Project helpers
    # ------------------------------------------------------------------ #

    def project_path(self, project_name=None) -> str | None:
        name = project_name or self.current_project
        if not name:
            return None
        return os.path.join(self.vault_path, "Projects", name)

    def list_projects(self):
        p = os.path.join(self.vault_path, "Projects")
        if not os.path.exists(p):
            return []
        return [
            d for d in os.listdir(p)
            if os.path.isdir(os.path.join(p, d))
        ]
