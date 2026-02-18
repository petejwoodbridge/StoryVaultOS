"""
StoryVault Project Manager
Handles project creation, folder scaffolding, and status reporting.
"""

import os
import json
from datetime import datetime


PROJECT_DIRS = [
    "Canon",
    "Characters",
    "World",
    "Structure",
    "Scenes",
    "Drafts",
    "Memory/Episodic",
    "History/proposals",
]

CANON_TEMPLATE = """\
# CANON

*Project: {name}*
*Created: {date}*

---

## Story Premise

[Write the core premise of this story here.]

---

## Core Themes

-
-
-

---

## The World

[Describe the setting, time period, rules of the world.]

---

## Core Characters

[List characters with one-line descriptions.]

---

## Story Rules

[Immutable facts about this storyworld that agents must respect.]

---

*This file is the source of truth for the storyworld.*
*Lock it when stable: python storyvault.py lock-canon*
"""

WORKING_MEMORY_TEMPLATE = """\
# WORKING MEMORY

*Project: {name}*
*Last updated: {date}*

---

## Current Focus

[What the story is actively developing right now.]

---

## Recent Decisions

-

---

## Active Story Threads

-

---

## Character States

-

---

## Open Questions

-

---

*This file is maintained by agents.*
*Compress when large: python storyvault.py compress-memory*
"""


class ProjectManager:
    def __init__(self, vault_path: str):
        self.vault_path = vault_path
        self.projects_path = os.path.join(vault_path, "Projects")
        os.makedirs(self.projects_path, exist_ok=True)

    # ------------------------------------------------------------------ #
    # CRUD
    # ------------------------------------------------------------------ #

    def create(self, name: str) -> tuple[bool, str]:
        project_path = os.path.join(self.projects_path, name)

        if os.path.exists(project_path):
            return False, f"Project already exists: {name}"

        # Create all required directories
        for folder in PROJECT_DIRS:
            os.makedirs(os.path.join(project_path, folder), exist_ok=True)

        date = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Canon.md
        canon_path = os.path.join(project_path, "Canon", "Canon.md")
        with open(canon_path, "w", encoding="utf-8") as f:
            f.write(CANON_TEMPLATE.format(name=name, date=date))

        # WorkingMemory.md
        mem_path = os.path.join(project_path, "Memory", "WorkingMemory.md")
        with open(mem_path, "w", encoding="utf-8") as f:
            f.write(WORKING_MEMORY_TEMPLATE.format(name=name, date=date))

        # commits.json
        commits_path = os.path.join(project_path, "History", "commits.json")
        with open(commits_path, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)

        return True, f"Project created: {project_path}"

    def exists(self, name: str) -> bool:
        return os.path.isdir(os.path.join(self.projects_path, name))

    def list_projects(self) -> list[str]:
        if not os.path.exists(self.projects_path):
            return []
        return [
            d for d in sorted(os.listdir(self.projects_path))
            if os.path.isdir(os.path.join(self.projects_path, d))
        ]

    # ------------------------------------------------------------------ #
    # Status
    # ------------------------------------------------------------------ #

    def get_status(self, project_path: str) -> dict:
        canon_path = os.path.join(project_path, "Canon", "Canon.md")
        lock_path  = os.path.join(project_path, "Canon", "Canon.lock")
        mem_path   = os.path.join(project_path, "Memory", "WorkingMemory.md")
        scenes_path = os.path.join(project_path, "Scenes")
        proposals_path = os.path.join(project_path, "History", "proposals")

        def fsize(p):
            return os.path.getsize(p) if os.path.exists(p) else 0

        scene_count = 0
        if os.path.exists(scenes_path):
            scene_count = len([
                d for d in os.listdir(scenes_path)
                if d.startswith("scene_") and
                   os.path.isdir(os.path.join(scenes_path, d))
            ])

        pending_proposals = 0
        if os.path.exists(proposals_path):
            import json as _json
            for fname in os.listdir(proposals_path):
                if fname.endswith(".json"):
                    try:
                        with open(os.path.join(proposals_path, fname)) as f:
                            d = _json.load(f)
                        if d.get("status") == "PENDING":
                            pending_proposals += 1
                    except Exception:
                        pass

        return {
            "canon_locked":       os.path.exists(lock_path),
            "canon_size_bytes":   fsize(canon_path),
            "memory_size_bytes":  fsize(mem_path),
            "scene_count":        scene_count,
            "pending_proposals":  pending_proposals,
        }
