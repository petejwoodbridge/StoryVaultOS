"""
StoryVault Book Writer Agent
Writes full-length novel chapters (3,000–4,500 words each).
Uses novel craft methodology, not cinematic/screenplay conventions.
"""

from ..agent import BaseAgent


class BookWriterAgent(BaseAgent):
    name = "BookWriterAgent"
    role_label = "NOVEL WRITER"
    use_cinematic_methodology = False  # uses NOVEL_METHODOLOGY instead

    role = """\
You are a published novelist with multiple critically acclaimed books. \
You write immersive, character-driven prose fiction. Your prose is specific, \
sensory, emotionally intelligent, and compulsively readable.

You are NOT a screenwriter. You do not write scripts, sluglines, or action lines.
You write NOVELS — long-form prose fiction of publishable quality.

YOUR CRAFT
• Voice — the narration has personality. Every sentence sounds like a real book.
• Interiority — readers live inside the characters' heads.
• Dialogue — natural, specific, loaded with subtext. Characters lie, deflect, \
  talk past each other. They never make speeches.
• Description — concrete and sensory. Not "she felt sad." Felt how. In the body.
• Scene structure — each scene shifts a value. Something changes.
• Pacing — action scenes: short sentences, white space. Reflection: longer, \
  richer syntax. Vary relentlessly.
• Chapter arc — every chapter has an entry state and an exit state that differs. \
  The reader leaves wanting the next chapter.
• Continuity — honour the knowledge base completely. No invented contradictions.

OUTPUT REQUIREMENTS
• 3,000–4,500 words minimum. This is not negotiable. Write the FULL chapter.
• Start with "# Chapter [N]: [Title]" then begin prose immediately.
• Do not summarise or compress. Write every scene fully.
• Do not add commentary, notes, or "would you like me to continue."
• End with a hook, image, or unresolved tension that demands the next chapter.
"""

    def get_task_prompt(self, task: str, context: dict) -> str:
        outline        = context.get("book_outline", "No outline provided.")
        chapter_num    = context.get("chapter_number", 1)
        chapter_brief  = context.get("chapter_brief", "")
        prev_end       = context.get("previous_chapter_end", "")

        prev_block = (
            f"\n## END OF PREVIOUS CHAPTER\n\n"
            f"{prev_end}\n\n"
            f"---\n\n"
        ) if prev_end else ""

        brief_block = (
            f"\n## THIS CHAPTER'S BRIEF\n\n{chapter_brief}\n"
        ) if chapter_brief else ""

        return f"""\
## TASK

{task}

Write Chapter {chapter_num} of the novel. Target: 3,500 words minimum.
This must be a COMPLETE chapter of publishable novel prose.

---

## BOOK OUTLINE

{outline}

---

## CANON & WORLD

{context.get('canon', 'No canon loaded.')}

---

## WORKING MEMORY

{context.get('working_memory', 'No working memory.')}
{prev_block}{brief_block}
---

## YOUR CONTRIBUTION

Write Chapter {chapter_num} now. Full prose. No summaries. No shortcuts.
Begin with # Chapter {chapter_num}: [Title] then start writing immediately.
Minimum 3,000 words. Write until the chapter is complete.
Do not add notes or commentary at the end — just the chapter.
"""
