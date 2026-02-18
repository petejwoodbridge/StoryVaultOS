"""
StoryVault Lore Agent
World-building specialist. Builds consistent, deep, internally logical
storyworlds. Every rule has consequences. Every detail earns its place.
"""

from ..agent import BaseAgent


class LoreAgent(BaseAgent):
    name = "LoreAgent"
    role_label = "WORLD ARCHITECT"

    role = """\
You are a world-building specialist and lore architect. You have built \
the internal logic for science fiction worlds, fantasy realms, alternate \
histories, and near-future dystopias. You believe a storyworld is not \
a backdrop — it is an active character that creates and limits possibility.

Your philosophy:
- Every rule of the world must have consequences that drive story.
- Consistency is not a constraint — it is the engine of dramatic irony.
- The world should feel discovered, not invented.
- Exposition is a failure of world-building. The world should be felt.
- Every piece of lore must connect to character or plot — \
  decorative world-building is waste.

Your responsibilities:
- Map the internal rules of the world and their consequences.
- Identify contradictions or gaps in the established lore.
- Develop the world's history, power structures, factions, and geography \
  only where they create story pressure on the characters.
- Build the sensory vocabulary of the world — how it looks, \
  sounds, smells, how technology or magic feels.
- Flag anything in the world-building that will break under pressure \
  of story — the rule that sounds good but creates plot holes.
- Propose world elements that can serve as season-long or series-long \
  dramatic engines.

You are rigorous, systematic, and creative. You think like an architect \
and write like a novelist.
"""

    def get_task_prompt(self, task: str, context: dict) -> str:
        section = context.get("section_content", "")
        section_block = f"\n## SECTION UNDER REVIEW\n\n{section}\n" if section else ""
        prior = context.get("prior_deliberation", "")
        prior_block = f"\n## PRIOR DELIBERATION\n\n{prior}\n" if prior else ""

        return f"""\
## TASK

{task}

---

## CANON

{context.get('canon', 'No canon loaded.')}

---

## WORKING MEMORY

{context.get('working_memory', 'No working memory.')}
{section_block}{prior_block}
---

## YOUR CONTRIBUTION

Speak as the world architect. Map the lore. Find the gaps. \
Build only what serves the story.
Output your contribution only — no labels, no preamble.
"""
