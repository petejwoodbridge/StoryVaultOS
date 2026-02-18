"""
StoryVault Critic Agent
Analyses content for narrative coherence, character consistency,
dramatic effectiveness, and canon fidelity.
Output is ALWAYS a proposal — never a direct write.
"""

from ..agent import BaseAgent


class CriticAgent(BaseAgent):
    name = "CriticAgent"

    role = """\
You are a rigorous story analyst and script doctor working inside StoryVault.

Your responsibilities:
- Evaluate content with honesty and precision.
- Identify structural weaknesses, character inconsistencies, and canon violations.
- Propose concrete, actionable fixes — not vague suggestions.
- Be tough but fair. The goal is a great story, not comfort.

Constraints you must obey:
- Reference specific lines or passages when identifying problems.
- Use the canon as your ground truth for character and world facts.
- Do not suggest changes that contradict canon without flagging it explicitly.
- Output only your critique — no preamble or meta-commentary.
"""

    def get_task_prompt(self, task: str, context: dict) -> str:
        section = context.get("section_content", "")
        heading = context.get("section_heading", "")
        section_block = f"\n## SECTION UNDER REVIEW: {heading}\n\n{section}\n" if section else ""
        prior = context.get("prior_deliberation", "")
        prior_block = f"\n## PRIOR DELIBERATION\n\n{prior}\n" if prior else ""
        content = context.get("current_content", "")
        content_block = f"\n## CONTENT TO CRITIQUE\n\n{content}\n" if content else ""

        return f"""\
## TASK

{task}

---

## CANON MEMORY

{context.get('canon', 'No canon loaded.')}

---

## WORKING MEMORY

{context.get('working_memory', 'No working memory.')}
{content_block}{section_block}{prior_block}
---

## CRITIQUE FORMAT

Structure your critique as follows:

### STRENGTHS
[What works — be specific, cite names/details from the material]

### PROBLEMS
[Numbered list of specific issues with references where possible]

### CANON VIOLATIONS
[Any facts that contradict established canon — or NONE]

### PROPOSED FIXES
[Concrete revision suggestions for each problem — reference prior deliberation where relevant]

### VERDICT
[APPROVE / REVISE / REJECT — with one-line justification]
"""
