"""StoryVault Session Logger — persists all deliberation sessions to JSONL."""
import os
import json
from datetime import datetime
from typing import Dict, List


LOG_FILE = "History/session_log.jsonl"


class SessionLogger:
    """
    Appends deliberation session records to a JSONL file.
    Each line is a complete session: team, task, all agent turns, usage totals.
    """

    @staticmethod
    def append(project_path: str, session: Dict) -> None:
        """Append a completed session record to the JSONL log."""
        path = os.path.join(project_path, LOG_FILE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(session, ensure_ascii=False) + "\n")

    @staticmethod
    def load(project_path: str, n: int = 200) -> List[Dict]:
        """Return the most recent n sessions, newest first."""
        path = os.path.join(project_path, LOG_FILE)
        if not os.path.exists(path):
            return []
        try:
            with open(path, encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
            sessions = []
            for line in lines:
                try:
                    sessions.append(json.loads(line))
                except Exception:
                    pass
            return list(reversed(sessions[-n:]))
        except Exception:
            return []
