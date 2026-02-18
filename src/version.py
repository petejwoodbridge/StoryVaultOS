"""
StoryVault Version Tracker
Records every approved/rejected proposal as an immutable commit log entry.
"""

import os
import json
from datetime import datetime


class VersionTracker:
    def __init__(self, project_path: str):
        self.project_path  = project_path
        self.history_path  = os.path.join(project_path, "History")
        self.commits_path  = os.path.join(self.history_path, "commits.json")
        os.makedirs(self.history_path, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Commit
    # ------------------------------------------------------------------ #

    def commit(self, proposal_data: dict, usage: dict | None = None) -> str:
        """Record the outcome of a proposal. Returns commit_id."""
        ts = datetime.now()
        commit_id = f"commit_{ts.strftime('%Y%m%d_%H%M%S')}"

        entry = {
            "id":           commit_id,
            "timestamp":    ts.isoformat(),
            "agent":        proposal_data.get("agent", "unknown"),
            "proposal_id":  proposal_data.get("id", ""),
            "type":         proposal_data.get("type", ""),
            "target_file":  proposal_data.get("target_file", ""),
            "status":       proposal_data.get("status", ""),
            "tokens": {
                "prompt":     (usage or {}).get("prompt_tokens", 0),
                "completion": (usage or {}).get("completion_tokens", 0),
                "total":      (usage or {}).get("total_tokens", 0),
            },
            "cost": (usage or {}).get("cost", 0.0),
        }

        commits = self._load()
        commits.append(entry)
        self._save(commits)
        return commit_id

    # ------------------------------------------------------------------ #
    # Query
    # ------------------------------------------------------------------ #

    def list_commits(self, limit: int = 20) -> list[dict]:
        commits = self._load()
        return commits[-limit:]

    def get_stats(self) -> dict:
        commits = self._load()
        approved = sum(1 for c in commits if c.get("status") == "APPROVED")
        rejected = sum(1 for c in commits if c.get("status") == "REJECTED")
        total_cost = sum(c.get("cost", 0.0) for c in commits)
        total_tokens = sum(c.get("tokens", {}).get("total", 0) for c in commits)

        return {
            "total_commits":  len(commits),
            "approved":       approved,
            "rejected":       rejected,
            "total_tokens":   total_tokens,
            "total_cost":     total_cost,
        }

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def _load(self) -> list[dict]:
        if not os.path.exists(self.commits_path):
            return []
        with open(self.commits_path, encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []

    def _save(self, commits: list[dict]):
        with open(self.commits_path, "w", encoding="utf-8") as f:
            json.dump(commits, f, indent=2)
