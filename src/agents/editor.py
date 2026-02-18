"""
StoryVault Editor Agent
Revises content based on critique notes.
Applies changes surgically — preserves what works, fixes what is broken.
Output is ALWAYS a proposal — never a direct write.
"""

from ..agent import BaseAgent


class EditorAgent(BaseAgent):
    name = "EditorAgent"

    role = """\
You are a professional developmental editor and script doctor working inside StoryVault.

Your responsibilities:
- Revise content based on the provided critique notes.
- Fix what is broken. Preserve what works. Maintain the author's voice.
- Apply changes surgically — do not rewrite for its own sake.
- The output must be the complete revised content, not a list of changes.
- All edits must remain canon-compliant.

Constraints you must obey:
- Never contradict canon facts.
- Output only the revised content — no commentary, no change logs.
- The output must be a complete, standalone document, ready to replace the original.
"""

    def get_task_prompt(self, task: str, context: dict) -> str:
        critique = context.get("critique", "No critique notes provided.")

        return f"""\
## TASK

{task}

---

## CANON MEMORY

{context.get('canon', 'No canon loaded.')}

---

## WORKING MEMORY

{context.get('working_memory', 'No working memory.')}

---

## ORIGINAL CONTENT

{context.get('current_content', 'No original content provided.')}

---

## CRITIQUE NOTES

{critique}

---

## INSTRUCTIONS

Revise the original content based on the critique notes above.
Output only the complete revised content — no preamble, no change log.
The output will directly replace the original file.
"""
