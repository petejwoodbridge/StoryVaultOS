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
        "label":     "Supporting Characters",
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
    "concept": {
        "label":     "Concepts",
        "folder":    "Concepts",
        "icon":      "CN",
        "extension": ".md",
    },
}

# Entity types that support explicit connections / relations
ENTITY_TYPES = {"character", "location", "object", "event", "creature", "concept"}


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

    def _meta_path(self, doc_type: str, slug: str) -> str:
        info = DOC_TYPES[doc_type]
        return os.path.join(self.docs_root, info["folder"], f"{slug}.meta.json")

    def _read_meta(self, doc_type: str, slug: str) -> dict:
        mp = self._meta_path(doc_type, slug)
        if os.path.exists(mp):
            try:
                with open(mp, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _write_meta(self, meta: dict, doc_type: str, slug: str) -> None:
        mp = self._meta_path(doc_type, slug)
        with open(mp, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------ #
    # CRUD
    # ------------------------------------------------------------------ #

    def save(self, doc_type: str, title: str, content: str) -> dict:
        """
        Save a document (create or overwrite by slug).
        Preserves existing metadata fields (relations, category, order) on update.
        Returns the document metadata dict.
        """
        if doc_type not in DOC_TYPES:
            raise ValueError(f"Unknown doc_type: {doc_type}")

        info   = DOC_TYPES[doc_type]
        slug   = _slug(title)
        folder = os.path.join(self.docs_root, info["folder"])
        path   = os.path.join(folder, f"{slug}.md")

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        # Preserve existing meta fields (relations, category, order, etc.)
        existing = self._read_meta(doc_type, slug)
        meta = {
            **existing,
            "doc_type":   doc_type,
            "title":      title,
            "slug":       slug,
            "created_at": existing.get("created_at", datetime.now().isoformat()),
            "path":       path,
        }
        self._write_meta(meta, doc_type, slug)
        return meta

    def get(self, doc_type: str, slug: str) -> dict | None:
        """Return {meta, content} or None if not found."""
        if doc_type not in DOC_TYPES:
            return None
        info   = DOC_TYPES[doc_type]
        folder = os.path.join(self.docs_root, info["folder"])
        path   = os.path.join(folder, f"{slug}.md")

        if not os.path.exists(path):
            return None

        with open(path, encoding="utf-8") as f:
            content = f.read()

        meta = self._read_meta(doc_type, slug)
        return {"meta": meta, "content": content}

    def list_all(self) -> list[dict]:
        """Return all documents across all types, sorted by order then newest first."""
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
                    # Always guarantee doc_type and slug (derive slug from filename if missing)
                    derived_slug = fname.replace(".meta.json", "")
                    docs.append({
                        **meta,
                        "doc_type":   doc_type,
                        "slug":       meta.get("slug") or derived_slug,
                        "type_label": info["label"],
                        "icon":       info["icon"],
                    })
                except Exception:
                    pass

        docs.sort(key=lambda d: (d.get("order", 9999), d.get("created_at", "")))
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
    # Metadata helpers
    # ------------------------------------------------------------------ #

    def update_meta(self, doc_type: str, slug: str, fields: dict) -> dict:
        """Merge `fields` into an existing document's meta.json."""
        if doc_type not in DOC_TYPES:
            raise ValueError(f"Unknown doc_type: {doc_type}")
        meta = self._read_meta(doc_type, slug)
        meta.update(fields)
        self._write_meta(meta, doc_type, slug)
        return meta

    def set_orders(self, doc_type: str, order_map: dict) -> None:
        """Set the `order` field for multiple documents. order_map: {slug: int}"""
        for slug, order in order_map.items():
            try:
                meta = self._read_meta(doc_type, slug)
                if meta:
                    meta["order"] = order
                    self._write_meta(meta, doc_type, slug)
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Explicit entity relations (for knowledge graph)
    # ------------------------------------------------------------------ #

    def add_relation(self, doc_type: str, slug: str, relation: dict) -> dict:
        """
        Add a relation to a document's metadata.
        relation = {target_type, target_slug, target_title, label}
        """
        meta = self._read_meta(doc_type, slug)
        if not meta:
            raise ValueError(f"Document {doc_type}/{slug} not found")
        relations = meta.get("relations", [])
        relations.append(relation)
        meta["relations"] = relations
        self._write_meta(meta, doc_type, slug)
        return meta

    def remove_relation(self, doc_type: str, slug: str, idx: int) -> dict:
        """Remove a relation by index from a document's metadata."""
        meta = self._read_meta(doc_type, slug)
        if not meta:
            raise ValueError(f"Document {doc_type}/{slug} not found")
        relations = meta.get("relations", [])
        if 0 <= idx < len(relations):
            relations.pop(idx)
        meta["relations"] = relations
        self._write_meta(meta, doc_type, slug)
        return meta

    def list_all_relations(self) -> list[dict]:
        """
        Scan all entity-type documents and return every explicit relation as a
        flat list of edge dicts, suitable for injecting into the knowledge graph.
        Each dict: {source_type, source_slug, source_title, target_type,
                    target_slug, target_title, label}
        """
        edges = []
        for doc_type in ENTITY_TYPES:
            if doc_type not in DOC_TYPES:
                continue
            info   = DOC_TYPES[doc_type]
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
                    slug  = meta.get("slug", fname.replace(".meta.json", ""))
                    title = meta.get("title", slug)
                    for rel in meta.get("relations", []):
                        edges.append({
                            "source_type":  doc_type,
                            "source_slug":  slug,
                            "source_title": title,
                            "target_type":  rel.get("target_type", ""),
                            "target_slug":  rel.get("target_slug", ""),
                            "target_title": rel.get("target_title", ""),
                            "label":        rel.get("label", "related to"),
                        })
                except Exception:
                    pass
        return edges

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
                current_lines.append(line)
            else:
                current_lines.append(line)

        if current_lines or current_heading:
            sections.append({
                "index":   idx,
                "heading": current_heading,
                "content": "\n".join(current_lines).strip(),
            })

        return sections
