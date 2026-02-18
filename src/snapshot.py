"""StoryVault Snapshot Manager — rolling undo stack."""
import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple


class SnapshotManager:
    STACK_FILE = "History/undo_stack.json"
    MAX = 20

    @staticmethod
    def push(project_path: str, abs_file_path: str, label: str) -> Optional[str]:
        """Snapshot abs_file_path before it is overwritten. Returns snap id or None."""
        if not os.path.exists(abs_file_path):
            return None
        with open(abs_file_path, encoding="utf-8") as f:
            content = f.read()
        rel = os.path.relpath(abs_file_path, project_path)
        sid = "snap_{}".format(datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
        entry = {
            "id": sid,
            "timestamp": datetime.now().isoformat(),
            "label": label,
            "rel_path": rel,
            "content": content,
        }
        stack = SnapshotManager._load(project_path)
        stack.insert(0, entry)
        SnapshotManager._save(project_path, stack[: SnapshotManager.MAX])
        return sid

    @staticmethod
    def get_history(project_path: str, n: int = 15) -> List[Dict]:
        """Return recent snapshots without content (for display)."""
        return [
            {k: v for k, v in s.items() if k != "content"}
            for s in SnapshotManager._load(project_path)[:n]
        ]

    @staticmethod
    def restore(project_path: str, snap_id: str) -> Tuple[bool, str]:
        """Restore a snapshot. Saves current state first so the restore is itself undoable."""
        stack = SnapshotManager._load(project_path)
        snap = next((s for s in stack if s["id"] == snap_id), None)
        if not snap:
            return False, "Snapshot {} not found".format(snap_id)
        abs_path = os.path.join(project_path, snap["rel_path"])
        # Snapshot current state before restoring so the restore can be undone
        SnapshotManager.push(project_path, abs_path, "[pre-restore] {}".format(snap["label"]))
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(snap["content"])
        return True, "Restored: {}".format(snap["rel_path"])

    # ── internal ─────────────────────────────────────────────────────────────

    @staticmethod
    def _load(project_path: str) -> List[Dict]:
        path = os.path.join(project_path, SnapshotManager.STACK_FILE)
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    @staticmethod
    def _save(project_path: str, stack: List[Dict]) -> None:
        path = os.path.join(project_path, SnapshotManager.STACK_FILE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(stack, f, indent=2, ensure_ascii=False)
