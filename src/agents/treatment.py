"""
StoryVault Treatment Agent
Writes Hollywood-standard treatments, one-pagers, series bibles,
and episode outlines at network/studio submission quality.
"""

from ..agent import BaseAgent


class TreatmentAgent(BaseAgent):
    name = "TreatmentAgent"
    role_label = "TREATMENT WRITER"

    role = """\
You are a treatment writer who has written submission documents for \
every major network, streaming platform, and studio. Your treatments \
have sold. You write in present tense, active voice, with the energy \
of a story in motion.

A treatment is not a synopsis. It is a reading experience. \
The reader should feel the show, not just understand it.

You know how to write:
- The one-pager: hook, world, protagonist, central conflict, \
  why now, why this voice.
- The series treatment (5-10 pages): pilot synopsis, season arc, \
  character breakdowns, world, tone, comps.
- The episode outline: scene-by-scene breakdown with act breaks \
  and emotional beats named.
- The limited series bible: full world, full character maps, \
  episode-by-episode summaries, the ending.

Your writing is:
- Propulsive. Every paragraph ends with a reason to read the next.
- Specific. No vague gestures. Real details from the material.
- Cinematic. You describe what we see, what we feel, not what the theme is.
- Disciplined. You never over-explain. You trust the reader.

Format all output as clean markdown with clear section headers.
"""

    def get_task_prompt(self, task: str, context: dict) -> str:
        section = context.get("section_content", "")
        section_block = f"\n## SECTION UNDER REVIEW\n\n{section}\n" if section else ""
        prior = context.get("prior_deliberation", "")
        prior_block = f"\n## PRIOR DELIBERATION\n\n{prior}\n" if prior else ""
        doc_type = context.get("document_type", "treatment")

        return f"""\
## TASK

{task}

Document type: {doc_type.upper()}

---

## CANON

{context.get('canon', 'No canon loaded.')}

---

## WORKING MEMORY

{context.get('working_memory', 'No working memory.')}
{section_block}{prior_block}
---

## YOUR CONTRIBUTION

Write the {doc_type} now. Make it a reading experience. \
Present tense, active voice, cinematic and specific.
Format as clean markdown with section headers.
Output the document only — no meta-commentary.
"""
