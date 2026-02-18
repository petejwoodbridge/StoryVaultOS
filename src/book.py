"""
StoryVault Book Manager
Manages a long-form novel project: chapter outline, individual chapters,
word count tracking, and full-book export.

Storage layout:
  {project_path}/Book/
    outline.md          — chapter-by-chapter plan
    chapter_01.md       — written chapters
    chapter_02.md
    ...
"""

import os
import re
from datetime import datetime


class BookManager:
    def __init__(self, project_path: str):
        self.project_path = project_path
        self.book_root    = os.path.join(project_path, "Book")
        os.makedirs(self.book_root, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Paths
    # ------------------------------------------------------------------ #

    def outline_path(self) -> str:
        return os.path.join(self.book_root, "outline.md")

    def chapter_path(self, n: int) -> str:
        return os.path.join(self.book_root, f"chapter_{n:02d}.md")

    # ------------------------------------------------------------------ #
    # Outline
    # ------------------------------------------------------------------ #

    def has_outline(self) -> bool:
        return os.path.exists(self.outline_path())

    def get_outline(self) -> str:
        p = self.outline_path()
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return f.read()
        return ""

    def save_outline(self, content: str) -> None:
        with open(self.outline_path(), "w", encoding="utf-8") as f:
            f.write(content)

    def get_chapter_brief(self, n: int) -> str:
        """
        Extract the brief for chapter N from the outline.
        Looks for ## CHAPTER N: or ## Chapter N: headings.
        """
        outline = self.get_outline()
        if not outline:
            return ""
        pattern = re.compile(
            rf"^##\s+CHAPTER\s+{n}\b[^\n]*\n(.*?)(?=^##\s+CHAPTER\s+\d+|\Z)",
            re.MULTILINE | re.DOTALL | re.IGNORECASE,
        )
        m = pattern.search(outline)
        if m:
            return m.group(0).strip()
        return ""

    def count_planned_chapters(self) -> int:
        """Count how many chapters are listed in the outline."""
        outline = self.get_outline()
        if not outline:
            return 0
        matches = re.findall(r"^##\s+CHAPTER\s+(\d+)", outline, re.MULTILINE | re.IGNORECASE)
        if matches:
            return max(int(m) for m in matches)
        return 0

    # ------------------------------------------------------------------ #
    # Chapters
    # ------------------------------------------------------------------ #

    def get_chapter(self, n: int) -> str | None:
        p = self.chapter_path(n)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return f.read()
        return None

    def save_chapter(self, n: int, content: str) -> None:
        with open(self.chapter_path(n), "w", encoding="utf-8") as f:
            f.write(content)

    def _chapter_title(self, content: str) -> str:
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("#"):
                return line.lstrip("#").strip()
        return "Untitled"

    def list_chapters(self) -> list[dict]:
        """Return all written chapters sorted by number."""
        chapters = []
        for fname in sorted(os.listdir(self.book_root)):
            m = re.match(r"chapter_(\d+)\.md$", fname)
            if not m:
                continue
            n    = int(m.group(1))
            path = os.path.join(self.book_root, fname)
            try:
                with open(path, encoding="utf-8") as f:
                    content = f.read()
                wc = len(content.split())
                chapters.append({
                    "number":     n,
                    "title":      self._chapter_title(content),
                    "word_count": wc,
                    "path":       path,
                })
            except Exception:
                pass
        return chapters

    def total_word_count(self) -> int:
        return sum(c["word_count"] for c in self.list_chapters())

    def next_unwritten_chapter(self) -> int:
        """Return the number of the next chapter that hasn't been written yet."""
        written = {c["number"] for c in self.list_chapters()}
        planned = self.count_planned_chapters()
        for n in range(1, max(planned + 1, 31)):
            if n not in written:
                return n
        return max(written) + 1 if written else 1

    def previous_chapter_tail(self, n: int, chars: int = 2500) -> str:
        """Return the last `chars` characters of chapter n-1 (for context)."""
        if n <= 1:
            return ""
        prev = self.get_chapter(n - 1)
        if not prev:
            return ""
        return prev[-chars:] if len(prev) > chars else prev

    # ------------------------------------------------------------------ #
    # Export
    # ------------------------------------------------------------------ #

    def export_full_book(self) -> str:
        """Combine all written chapters into one document."""
        chapters = self.list_chapters()
        if not chapters:
            return "No chapters written yet."
        parts = []
        for ch in chapters:
            content = self.get_chapter(ch["number"]) or ""
            parts.append(content)
        total_wc = sum(len(p.split()) for p in parts)
        header = (
            f"# BOOK EXPORT\n"
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"Chapters: {len(parts)} · Total words: {total_wc:,}\n\n"
            f"---\n\n"
        )
        return header + "\n\n---\n\n".join(parts)

    def status(self) -> dict:
        chapters     = self.list_chapters()
        total_wc     = sum(c["word_count"] for c in chapters)
        planned      = self.count_planned_chapters()
        next_ch      = self.next_unwritten_chapter()
        return {
            "outline_exists":    self.has_outline(),
            "chapters":          chapters,
            "total_words":       total_wc,
            "target_words":      85000,
            "planned_chapters":  planned,
            "next_chapter":      next_ch,
        }
