"""
StoryVault World Bible Manager

Manages the Story World Bible — the primary storyworld reference document.
Structured as individual markdown files per section under Projects/<name>/WorldBible/

Sections:
    overview   — Logline, premise, theme, genre, emotional core
    lore       — World history, mythology, backstory
    logic      — Rules: magic, technology, physics
    tone       — Visual language, cinematic approach, mood
    structure  — Three-act breakdown, key sequences
    rules      — Non-negotiable world rules injected into all agent calls
"""

import os
import json
from datetime import datetime


class WorldBibleManager:
    """
    Manages the Story World Bible — a structured set of markdown sections
    that serve as the primary canonical reference for the storyworld.

    Each section lives at: WorldBible/<section_id>.md
    The 'rules' section is injected into every agent call as mandatory law.
    """

    SECTIONS: dict[str, dict] = {
        "overview": {
            "label":       "Overview",
            "description": "Logline, premise, theme, genre, emotional core — the complete pitch",
            "icon":        "OV",
            "order":       0,
        },
        "lore": {
            "label":       "Lore & History",
            "description": "World history, mythology, backstory — the deep past that shapes the story",
            "icon":        "LR",
            "order":       1,
        },
        "logic": {
            "label":       "World Logic",
            "description": "Rules: magic, technology, physics — how this world fundamentally works",
            "icon":        "WL",
            "order":       2,
        },
        "tone": {
            "label":       "Tone & Style",
            "description": "Visual language, cinematic approach, genre influences, mood, atmosphere",
            "icon":        "TS",
            "order":       3,
        },
        "structure": {
            "label":       "Structure",
            "description": "Three-act breakdown, inciting incident, midpoint, climax, key sequences",
            "icon":        "ST",
            "order":       4,
        },
        "rules": {
            "label":       "World Rules",
            "description": "Non-negotiable constraints — injected into EVERY agent call as mandatory law",
            "icon":        "WR",
            "order":       5,
        },
    }

    def __init__(self, project_path: str):
        self.project_path = project_path
        self.bible_root   = os.path.join(project_path, "WorldBible")
        os.makedirs(self.bible_root, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Internal paths
    # ------------------------------------------------------------------ #

    def _path(self, section_id: str) -> str:
        return os.path.join(self.bible_root, f"{section_id}.md")

    def _meta_path(self, section_id: str) -> str:
        return os.path.join(self.bible_root, f"{section_id}.meta.json")

    def section_path(self, section_id: str) -> str:
        """Public: absolute path to a section file (for proposals)."""
        return self._path(section_id)

    # ------------------------------------------------------------------ #
    # CRUD
    # ------------------------------------------------------------------ #

    def get_section(self, section_id: str) -> str:
        """Return content of a section, or '' if not yet written."""
        if section_id not in self.SECTIONS:
            raise ValueError(f"Unknown WorldBible section: {section_id}")
        p = self._path(section_id)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return f.read()
        return ""

    def save_section(self, section_id: str, content: str) -> dict:
        """Directly save section content (for manual edits — no proposal)."""
        if section_id not in self.SECTIONS:
            raise ValueError(f"Unknown WorldBible section: {section_id}")
        os.makedirs(self.bible_root, exist_ok=True)
        with open(self._path(section_id), "w", encoding="utf-8") as f:
            f.write(content)
        meta = {
            "section_id": section_id,
            "updated_at": datetime.now().isoformat(),
        }
        with open(self._meta_path(section_id), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        return meta

    def get_all_sections(self) -> list[dict]:
        """Return all sections with content + meta, sorted by order."""
        result = []
        for sid, info in sorted(self.SECTIONS.items(), key=lambda x: x[1]["order"]):
            p       = self._path(sid)
            content = ""
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    content = f.read()
            meta_p  = self._meta_path(sid)
            updated = ""
            if os.path.exists(meta_p):
                try:
                    with open(meta_p, encoding="utf-8") as f:
                        updated = json.load(f).get("updated_at", "")
                except Exception:
                    pass
            words = len(content.split()) if content.strip() else 0
            result.append({
                **info,
                "section_id":  sid,
                "content":     content,
                "updated_at":  updated,
                "has_content": bool(content.strip()),
                "word_count":  words,
            })
        return result

    # ------------------------------------------------------------------ #
    # Agent context helpers
    # ------------------------------------------------------------------ #

    def get_world_rules(self) -> str:
        """Return World Rules section (injected as mandatory constraints)."""
        try:
            return self.get_section("rules")
        except Exception:
            return ""

    def get_context_for_agents(self, max_chars: int = 5000) -> str:
        """
        Return all non-empty WorldBible sections formatted for agent system prompts.
        Priority: overview, lore, logic, tone, structure.
        Rules are injected separately via get_world_rules().
        """
        priority    = ["overview", "lore", "logic", "tone", "structure"]
        parts       = []
        total       = 0
        per_section = max_chars // max(len(priority), 1)

        for sid in priority:
            try:
                content = self.get_section(sid)
            except Exception:
                continue
            if not content.strip():
                continue
            info  = self.SECTIONS[sid]
            chunk = content[:per_section]
            if len(content) > per_section:
                chunk += "\n[...truncated]"
            block = f"### {info['label'].upper()}\n{chunk}"
            parts.append(block)
            total += len(block)
            if total >= max_chars:
                break

        return "\n\n---\n\n".join(parts)
