"""
StoryVault Canon Manager
Canon.md is immutable when Canon.lock exists.
All modifications must go through the proposal system.
"""

import os
from datetime import datetime


class CanonManager:
    def __init__(self, project_path: str):
        self.project_path = project_path
        self.canon_path   = os.path.join(project_path, "Canon", "Canon.md")
        self.lock_path    = os.path.join(project_path, "Canon", "Canon.lock")

    # ------------------------------------------------------------------ #
    # Lock state
    # ------------------------------------------------------------------ #

    def is_locked(self) -> bool:
        return os.path.exists(self.lock_path)

    def lock(self) -> tuple[bool, str]:
        if self.is_locked():
            return False, "Canon is already locked."
        if not os.path.exists(self.canon_path):
            return False, "Canon.md does not exist. Create it first."

        timestamp = datetime.now().isoformat()
        with open(self.lock_path, "w", encoding="utf-8") as f:
            f.write(f"CANON LOCKED\n")
            f.write(f"Timestamp : {timestamp}\n")
            f.write(f"\n")
            f.write(f"To unlock  : python storyvault.py unlock-canon\n")

        return True, f"Canon locked at {timestamp}"

    def unlock(self) -> tuple[bool, str]:
        if not self.is_locked():
            return False, "Canon is not locked."
        os.remove(self.lock_path)
        return True, "Canon unlocked."

    def get_lock_info(self) -> str | None:
        if not self.is_locked():
            return None
        with open(self.lock_path, encoding="utf-8") as f:
            return f.read()

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #

    def read(self) -> tuple[str | None, str | None]:
        """Returns (content, error_message). One of them will be None."""
        if not os.path.exists(self.canon_path):
            return None, "Canon.md not found."
        with open(self.canon_path, encoding="utf-8") as f:
            return f.read(), None

    def can_write(self) -> bool:
        """Proposals targeting Canon.md are only allowed when unlocked."""
        return not self.is_locked()
