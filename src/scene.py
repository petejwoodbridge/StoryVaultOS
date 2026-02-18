"""
StoryVault Scene Manager
Scene pipeline: CREATED → DRAFTED → CRITIQUED → REVISED → APPROVED (LOCKED)
"""

import os
import json
from datetime import datetime


SCENE_PHASES = ["CREATED", "DRAFTED", "CRITIQUED", "REVISED", "APPROVED"]

SCENE_CARD_TEMPLATE = """\
# SCENE {num:02d}

**Title       :** {title}
**Location    :** {location}
**Time of Day :** {time_of_day}
**Phase       :** CREATED

---

## Goal of Scene

[What must this scene accomplish dramatically?]

---

## Description

{description}

---

## Characters Present

-

---

## Key Story Beat

[The single most important thing that happens.]

---

## Notes

-
"""


class SceneManager:
    def __init__(self, project_path: str):
        self.project_path = project_path
        self.scenes_path  = os.path.join(project_path, "Scenes")
        os.makedirs(self.scenes_path, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Path helpers
    # ------------------------------------------------------------------ #

    def scene_dir(self, num: int) -> str:
        return os.path.join(self.scenes_path, f"scene_{int(num):02d}")

    def scene_file(self, num: int, filename: str) -> str:
        return os.path.join(self.scene_dir(num), filename)

    # ------------------------------------------------------------------ #
    # Meta
    # ------------------------------------------------------------------ #

    def get_meta(self, num: int) -> dict | None:
        p = self.scene_file(num, "meta.json")
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def set_meta(self, num: int, meta: dict):
        d = self.scene_dir(num)
        os.makedirs(d, exist_ok=True)
        meta["modified"] = datetime.now().isoformat()
        with open(self.scene_file(num, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

    def update_phase(self, num: int, phase: str):
        meta = self.get_meta(num)
        if meta:
            meta["phase"] = phase
            self.set_meta(num, meta)

    # ------------------------------------------------------------------ #
    # Lock
    # ------------------------------------------------------------------ #

    def is_locked(self, num: int) -> bool:
        return os.path.exists(self.scene_file(num, "SCENE.LOCK"))

    def lock(self, num: int):
        p = self.scene_file(num, "SCENE.LOCK")
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"SCENE {num:02d} APPROVED AND LOCKED\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write(f"\nThis scene is canon. Create a new revision branch to modify it.\n")

    # ------------------------------------------------------------------ #
    # Create
    # ------------------------------------------------------------------ #

    def create(
        self,
        num: int,
        title: str = "",
        location: str = "",
        time_of_day: str = "",
        description: str = "",
    ) -> tuple[bool, str]:
        if self.get_meta(num) is not None:
            return False, f"Scene {num:02d} already exists."

        d = self.scene_dir(num)
        os.makedirs(d, exist_ok=True)

        card = SCENE_CARD_TEMPLATE.format(
            num=num,
            title=title or f"Scene {num:02d}",
            location=location or "TBD",
            time_of_day=time_of_day or "TBD",
            description=description or "[Describe the scene here.]",
        )
        with open(self.scene_file(num, "scene_card.md"), "w", encoding="utf-8") as f:
            f.write(card)

        meta = {
            "scene_num":  int(num),
            "title":      title or f"Scene {num:02d}",
            "phase":      "CREATED",
            "locked":     False,
            "created":    datetime.now().isoformat(),
        }
        self.set_meta(num, meta)

        return True, f"Scene {num:02d} created."

    # ------------------------------------------------------------------ #
    # Content loaders (for agents)
    # ------------------------------------------------------------------ #

    def get_card(self, num: int) -> str:
        return self._read(num, "scene_card.md")

    def get_draft(self, num: int) -> str:
        return self._read(num, "draft.md")

    def get_critique(self, num: int) -> str:
        return self._read(num, "critique.md")

    def get_revision(self, num: int) -> str:
        return self._read(num, "revision.md")

    def get_best_content(self, num: int) -> str:
        """Return the most advanced content available for this scene."""
        for fname in ["revision.md", "draft.md", "scene_card.md"]:
            content = self._read(num, fname)
            if content:
                return content
        return ""

    def _read(self, num: int, filename: str) -> str:
        p = self.scene_file(num, filename)
        if not os.path.exists(p):
            return ""
        with open(p, encoding="utf-8") as f:
            return f.read()

    # ------------------------------------------------------------------ #
    # List
    # ------------------------------------------------------------------ #

    def list_scenes(self) -> list[dict]:
        scenes = []
        if not os.path.exists(self.scenes_path):
            return scenes
        for d in sorted(os.listdir(self.scenes_path)):
            if d.startswith("scene_") and os.path.isdir(
                os.path.join(self.scenes_path, d)
            ):
                try:
                    num = int(d.replace("scene_", ""))
                except ValueError:
                    continue
                meta = self.get_meta(num)
                if meta:
                    meta["locked"] = self.is_locked(num)
                    scenes.append(meta)
        return scenes
