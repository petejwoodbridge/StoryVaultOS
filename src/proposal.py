"""
StoryVault Proposal System
Every modification must be PROPOSED → REVIEWED → APPROVED/REJECTED → COMMITTED.
No agent may overwrite files directly.
"""

import os
import json
import difflib
from datetime import datetime


class ProposalManager:
    STATUS_PENDING  = "PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"

    def __init__(self, project_path: str):
        self.project_path  = project_path
        self.proposals_dir = os.path.join(project_path, "History", "proposals")
        os.makedirs(self.proposals_dir, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Create
    # ------------------------------------------------------------------ #

    def create(
        self,
        agent_name: str,
        proposal_type: str,
        target_file: str,
        new_content: str,
        rationale: str = "",
        current_content: str | None = None,
    ) -> tuple[str, dict]:
        """
        Create a new proposal file pair (.json + .proposal.md).
        Returns (proposal_id, proposal_data).
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prop_id   = f"prop_{timestamp}"

        # Read existing file content for diffing
        if current_content is None:
            if os.path.exists(target_file):
                with open(target_file, encoding="utf-8") as f:
                    current_content = f.read()
            else:
                current_content = ""

        diff = self._generate_diff(current_content, new_content, target_file)

        data = {
            "id":              prop_id,
            "agent":           agent_name,
            "type":            proposal_type,
            "target_file":     target_file,
            "status":          self.STATUS_PENDING,
            "created":         datetime.now().isoformat(),
            "rationale":       rationale,
            "current_content": current_content,
            "new_content":     new_content,
            "diff":            diff,
        }

        self._save_json(prop_id, data)
        self._save_markdown(prop_id, data)

        return prop_id, data

    # ------------------------------------------------------------------ #
    # Query
    # ------------------------------------------------------------------ #

    def list_pending(self) -> list[dict]:
        return [
            d for d in self._load_all()
            if d.get("status") == self.STATUS_PENDING
        ]

    def list_all(self, limit: int = 50) -> list[dict]:
        return self._load_all()[:limit]

    def get(self, prop_id: str) -> dict | None:
        p = self._json_path(prop_id)
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    # ------------------------------------------------------------------ #
    # Approve / Reject
    # ------------------------------------------------------------------ #

    def approve(self, prop_id: str) -> tuple[bool, str]:
        data = self.get(prop_id)
        if not data:
            return False, f"Proposal not found: {prop_id}"
        if data["status"] != self.STATUS_PENDING:
            return False, f"Proposal is {data['status']}, not PENDING."

        target = data["target_file"]
        os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(data["new_content"])

        data["status"]      = self.STATUS_APPROVED
        data["approved_at"] = datetime.now().isoformat()
        self._save_json(prop_id, data)
        self._save_markdown(prop_id, data)

        return True, f"Applied to {target}"

    def reject(self, prop_id: str, reason: str = "") -> tuple[bool, str]:
        data = self.get(prop_id)
        if not data:
            return False, f"Proposal not found: {prop_id}"
        if data["status"] != self.STATUS_PENDING:
            return False, f"Proposal is {data['status']}, not PENDING."

        data["status"]           = self.STATUS_REJECTED
        data["rejected_at"]      = datetime.now().isoformat()
        data["rejection_reason"] = reason
        self._save_json(prop_id, data)
        self._save_markdown(prop_id, data)

        return True, "Proposal rejected."

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _generate_diff(self, old: str, new: str, filename: str) -> str:
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{os.path.basename(filename)}",
            tofile=f"b/{os.path.basename(filename)}",
            n=3,
        )
        return "".join(diff)

    def _json_path(self, prop_id: str) -> str:
        return os.path.join(self.proposals_dir, f"{prop_id}.json")

    def _md_path(self, prop_id: str) -> str:
        return os.path.join(self.proposals_dir, f"{prop_id}.proposal.md")

    def _save_json(self, prop_id: str, data: dict):
        with open(self._json_path(prop_id), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _save_markdown(self, prop_id: str, data: dict):
        diff_block = data.get("diff", "")
        content = f"""\
# PROPOSAL: {data['id']}

**Agent   :** {data['agent']}
**Type    :** {data['type']}
**Status  :** {data['status']}
**Created :** {data['created']}
**Target  :** {data['target_file']}

## Rationale

{data['rationale']}

## Diff

```diff
{diff_block}
```

## Proposed Content

{data['new_content']}
"""
        with open(self._md_path(prop_id), "w", encoding="utf-8") as f:
            f.write(content)

    def _load_all(self) -> list[dict]:
        results = []
        for fname in os.listdir(self.proposals_dir):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.proposals_dir, fname), encoding="utf-8") as f:
                    results.append(json.load(f))
            except Exception:
                pass
        return sorted(results, key=lambda x: x.get("created", ""), reverse=True)
