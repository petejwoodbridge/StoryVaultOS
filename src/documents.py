"""
StoryVault Documents Manager
Manages generated development documents: treatments, beat sheets,
loglines, character profiles, and world-building docs.

All documents live under Projects/<name>/Documents/<type>/<slug>.md
"""

import os
import json
import re
from datetime import datetime


DOC_TYPES: dict[str, dict] = {
    "treatment": {
        "label":     "Treatments",
        "folder":    "Treatments",
        "icon":      "T",
        "extension": ".md",
    },
    "beat_sheet": {
        "label":     "Beat Sheets",
        "folder":    "BeatSheets",
        "icon":      "B",
        "extension": ".md",
    },
    "logline": {
        "label":     "Loglines",
        "folder":    "Loglines",
        "icon":      "L",
        "extension": ".md",
    },
    "character": {
        "label":     "Characters",
        "folder":    "Characters",
        "icon":      "C",
        "extension": ".md",
    },
    "world": {
        "label":     "World Building",
        "folder":    "WorldBuilding",
        "icon":      "W",
        "extension": ".md",
    },
    "creature": {
        "label":     "Creatures",
        "folder":    "Creatures",
        "icon":      "X",
        "extension": ".md",
    },
    "episode": {
        "label":     "Episodes",
        "folder":    "Episodes",
        "icon":      "E",
        "extension": ".md",
    },
    "location": {
        "label":     "Locations",
        "folder":    "Locations",
        "icon":      "P",
        "extension": ".md",
    },
    "bible": {
        "label":     "Story Bible",
        "folder":    "Bible",
        "icon":      "SB",
        "extension": ".md",
    },
    "object": {
        "label":     "Objects",
        "folder":    "Objects",
        "icon":      "O",
        "extension": ".md",
    },
    "event": {
        "label":     "Events",
        "folder":    "Events",
        "icon":      "EV",
        "extension": ".md",
    },
    "synopsis": {
        "label":     "Synopses",
        "folder":    "Synopses",
        "icon":      "SY",
        "extension": ".md",
    },
}


def _slug(title: str) -> str:
    s = re.sub(r"[^\w\s-]", "", title.lower())
    s = re.sub(r"[\s_]+", "_", s).strip("_")
    return s or "doc"


class DocumentsManager:
    def __init__(self, project_path: str):
        self.project_path = project_path
        self.docs_root    = os.path.join(project_path, "Documents")
        self._ensure_folders()

    def _ensure_folders(self):
        for info in DOC_TYPES.values():
            os.makedirs(
                os.path.join(self.docs_root, info["folder"]),
                exist_ok=True,
            )

    # ------------------------------------------------------------------ #
    # CRUD
    # ------------------------------------------------------------------ #

    def save(self, doc_type: str, title: str, content: str) -> dict:
        """
        Save a document (create or overwrite by slug).
        Returns the document metadata dict.
        """
        if doc_type not in DOC_TYPES:
            raise ValueError(f"Unknown doc_type: {doc_type}")

        info    = DOC_TYPES[doc_type]
        slug    = _slug(title)
        folder  = os.path.join(self.docs_root, info["folder"])
        path    = os.path.join(folder, f"{slug}.md")
        meta_p  = os.path.join(folder, f"{slug}.meta.json")

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        meta = {
            "doc_type":   doc_type,
            "title":      title,
            "slug":       slug,
            "created_at": datetime.now().isoformat(),
            "path":       path,
        }
        with open(meta_p, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        return meta

    def get(self, doc_type: str, slug: str) -> dict | None:
        """Return {meta, content} or None if not found."""
        if doc_type not in DOC_TYPES:
            return None
        info   = DOC_TYPES[doc_type]
        folder = os.path.join(self.docs_root, info["folder"])
        path   = os.path.join(folder, f"{slug}.md")
        meta_p = os.path.join(folder, f"{slug}.meta.json")

        if not os.path.exists(path):
            return None

        with open(path, encoding="utf-8") as f:
            content = f.read()

        meta = {}
        if os.path.exists(meta_p):
            with open(meta_p, encoding="utf-8") as f:
                meta = json.load(f)

        return {"meta": meta, "content": content}

    def list_all(self) -> list[dict]:
        """Return all documents across all types, sorted newest first."""
        docs = []
        for doc_type, info in DOC_TYPES.items():
            folder = os.path.join(self.docs_root, info["folder"])
            if not os.path.isdir(folder):
                continue
            for fname in os.listdir(folder):
                if not fname.endswith(".meta.json"):
                    continue
                meta_p = os.path.join(folder, fname)
                try:
                    with open(meta_p, encoding="utf-8") as f:
                        meta = json.load(f)
                    docs.append({**meta, "type_label": info["label"], "icon": info["icon"]})
                except Exception:
                    pass

        docs.sort(key=lambda d: d.get("created_at", ""), reverse=True)
        return docs

    def list_by_type(self, doc_type: str) -> list[dict]:
        return [d for d in self.list_all() if d.get("doc_type") == doc_type]

    def delete(self, doc_type: str, slug: str) -> bool:
        if doc_type not in DOC_TYPES:
            return False
        info   = DOC_TYPES[doc_type]
        folder = os.path.join(self.docs_root, info["folder"])
        path   = os.path.join(folder, f"{slug}.md")
        meta_p = os.path.join(folder, f"{slug}.meta.json")
        removed = False
        for p in [path, meta_p]:
            if os.path.exists(p):
                os.remove(p)
                removed = True
        return removed

    # ------------------------------------------------------------------ #
    # Canon section parsing
    # ------------------------------------------------------------------ #

    @staticmethod
    def parse_canon_sections(canon_text: str) -> list[dict]:
        """
        Split canon markdown by ## headings.
        Returns list of {heading, content, index}.
        """
        sections = []
        current_heading = "OVERVIEW"
        current_lines   = []
        idx = 0

        for line in canon_text.split("\n"):
            if line.startswith("## "):
                if current_lines:
                    sections.append({
                        "index":   idx,
                        "heading": current_heading,
                        "content": "\n".join(current_lines).strip(),
                    })
                    idx += 1
                current_heading = line[3:].strip()
                current_lines   = []
            elif line.startswith("# "):
                # Top-level heading goes into OVERVIEW
                current_lines.append(line)
            else:
                current_lines.append(line)

        # Last section
        if current_lines or current_heading:
            sections.append({
                "index":   idx,
                "heading": current_heading,
                "content": "\n".join(current_lines).strip(),
            })

        return sections
