"""
StoryVault Export Engine
Exports approved scenes as formatted screenplay .txt
Old-school Courier format. No modern styling.
"""

import os
import re
from datetime import datetime


class ExportEngine:
    LINE_WIDTH = 60
    ACTION_INDENT = 0
    DIALOG_INDENT = 20
    CHARACTER_INDENT = 25
    PAREN_INDENT = 22
    SLUG_INDENT = 0

    def __init__(self, project_path: str):
        self.project_path = project_path
        self.scenes_path  = os.path.join(project_path, "Scenes")
        self.drafts_path  = os.path.join(project_path, "Drafts")
        os.makedirs(self.drafts_path, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Public
    # ------------------------------------------------------------------ #

    def export(self, include_unapproved: bool = False) -> tuple[str, str]:
        """
        Collect scenes, format screenplay, write to Drafts/.
        Returns (output_path, content).
        """
        scenes = self._collect_scenes(include_unapproved)
        content = self._build_screenplay(scenes, include_unapproved)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenplay_{ts}.txt"
        output_path = os.path.join(self.drafts_path, filename)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        return output_path, content

    # ------------------------------------------------------------------ #
    # Collection
    # ------------------------------------------------------------------ #

    def _collect_scenes(self, include_unapproved: bool) -> list[dict]:
        scenes = []
        if not os.path.exists(self.scenes_path):
            return scenes

        for d in sorted(os.listdir(self.scenes_path)):
            if not (d.startswith("scene_") and
                    os.path.isdir(os.path.join(self.scenes_path, d))):
                continue

            scene_dir = os.path.join(self.scenes_path, d)
            lock_path = os.path.join(scene_dir, "SCENE.LOCK")
            locked    = os.path.exists(lock_path)

            if not include_unapproved and not locked:
                continue

            # Prefer revision → draft → scene_card
            content = ""
            for fname in ["revision.md", "draft.md", "scene_card.md"]:
                fp = os.path.join(scene_dir, fname)
                if os.path.exists(fp):
                    with open(fp, encoding="utf-8") as f:
                        content = f.read()
                    break

            if content:
                scenes.append({"name": d, "content": content, "locked": locked})

        return scenes

    # ------------------------------------------------------------------ #
    # Formatting
    # ------------------------------------------------------------------ #

    def _build_screenplay(self, scenes: list[dict], include_unapproved: bool) -> str:
        project_name = os.path.basename(self.project_path)
        lines = []

        # ---- Title block ----
        lines += self._title_block(project_name)

        if not scenes:
            lines.append("")
            lines.append("NO APPROVED SCENES TO EXPORT.")
            lines.append("")
            lines.append("Approve scenes first:")
            lines.append("  python storyvault.py approve-scene <num>")
            lines.append("")
            return "\n".join(lines)

        # ---- Scenes ----
        for sc in scenes:
            lines.append("")
            lines.append("=" * self.LINE_WIDTH)
            lines.append("")
            lines += self._format_scene_content(sc["content"])
            lines.append("")

        # ---- Footer ----
        lines.append("")
        lines.append("=" * self.LINE_WIDTH)
        lines.append(f"END OF DOCUMENT")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"StoryVault v0.1")
        lines.append("=" * self.LINE_WIDTH)

        return "\n".join(lines)

    def _title_block(self, project_name: str) -> list[str]:
        name_display = project_name.replace("_", " ")
        lines = [
            "",
            "=" * self.LINE_WIDTH,
            "",
            name_display.center(self.LINE_WIDTH),
            "",
            "Written with StoryVault".center(self.LINE_WIDTH),
            "",
            datetime.now().strftime("%Y-%m-%d").center(self.LINE_WIDTH),
            "",
            "=" * self.LINE_WIDTH,
            "",
            "",
        ]
        return lines

    def _format_scene_content(self, content: str) -> list[str]:
        """
        Light-touch formatting pass on raw markdown scene content.
        Converts markdown headings to sluglines, preserves dialogue blocks.
        """
        output = []
        for line in content.splitlines():
            stripped = line.strip()

            # Skip markdown meta lines
            if stripped.startswith("**") and ":" in stripped:
                continue

            # H1 headings → sluglines
            if stripped.startswith("# SCENE") or stripped.startswith("# Scene"):
                slug = stripped.lstrip("#").strip().upper()
                output.append("")
                output.append(slug)
                output.append("")
                continue

            # H2/H3 headings → scene beats (uppercase)
            if stripped.startswith("##"):
                beat = stripped.lstrip("#").strip().upper()
                output.append("")
                output.append(beat)
                output.append("")
                continue

            # Blank lines
            if not stripped:
                output.append("")
                continue

            # INT./EXT. slug lines
            if re.match(r'^(INT\.|EXT\.|INT\/EXT\.)', stripped, re.IGNORECASE):
                output.append("")
                output.append(stripped.upper())
                output.append("")
                continue

            # All-caps character cue (dialogue speaker)
            if stripped.isupper() and len(stripped.split()) <= 5 and len(stripped) < 40:
                output.append(" " * self.CHARACTER_INDENT + stripped)
                continue

            # Parenthetical
            if stripped.startswith("(") and stripped.endswith(")"):
                output.append(" " * self.PAREN_INDENT + stripped)
                continue

            # Default: action/dialogue line
            output.append(stripped)

        return output
