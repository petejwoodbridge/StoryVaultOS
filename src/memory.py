"""
StoryVault Memory Manager
Three-tier memory: Canon (locked) | Working (rolling) | Episodic (archive)
All writes go through the proposal system except archival operations.
"""

import os
import shutil
from datetime import datetime


class MemoryManager:
    def __init__(self, project_path: str):
        self.project_path  = project_path
        self.memory_path   = os.path.join(project_path, "Memory")
        self.working_path  = os.path.join(self.memory_path, "WorkingMemory.md")
        self.episodic_path = os.path.join(self.memory_path, "Episodic")
        os.makedirs(self.episodic_path, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Working Memory
    # ------------------------------------------------------------------ #

    def read_working(self) -> str:
        if not os.path.exists(self.working_path):
            return ""
        with open(self.working_path, encoding="utf-8") as f:
            return f.read()

    def write_working(self, content: str):
        """Called only by the proposal approval system."""
        with open(self.working_path, "w", encoding="utf-8") as f:
            f.write(content)

    def get_size_bytes(self) -> int:
        if not os.path.exists(self.working_path):
            return 0
        return os.path.getsize(self.working_path)

    def get_size_display(self) -> str:
        b = self.get_size_bytes()
        if b < 1024:
            return f"{b} B"
        if b < 1024 * 1024:
            return f"{b / 1024:.1f} KB"
        return f"{b / (1024*1024):.2f} MB"

    # ------------------------------------------------------------------ #
    # Episodic Archive
    # ------------------------------------------------------------------ #

    def archive_working(self) -> str:
        """
        Snapshot current WorkingMemory.md into Episodic/ before compression.
        Returns the archive file path.
        """
        if not os.path.exists(self.working_path):
            return ""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"episodic_{timestamp}.md"
        archive_path = os.path.join(self.episodic_path, archive_name)
        shutil.copy2(self.working_path, archive_path)
        return archive_path

    def list_episodic(self) -> list[str]:
        if not os.path.exists(self.episodic_path):
            return []
        return sorted(
            f for f in os.listdir(self.episodic_path)
            if f.endswith(".md")
        )

    def read_episodic(self, filename: str) -> str:
        p = os.path.join(self.episodic_path, filename)
        if not os.path.exists(p):
            return ""
        with open(p, encoding="utf-8") as f:
            return f.read()
