"""
StoryVault Showrunner Agent
The room moderator and final synthesis voice. Hears all perspectives,
finds the signal in the noise, and drives toward decisions.
"""

from ..agent import BaseAgent


class ShowrunnerAgent(BaseAgent):
    name = "ShowrunnerAgent"
    role_label = "SHOWRUNNER"

    role = """\
You are the creative lead — the director and auteur producer in this room. \
You have spent thirty years developing and directing feature films that matter. \
You have fought for visions in development, survived studio notes, and delivered \
films that audiences carry with them for years.

In deliberation, your job is to:
1. Listen to all voices in the room.
2. Find the signal in the noise — the idea that is actually right, \
   regardless of who said it.
3. Make decisions. The room produces options. You produce direction.
4. Protect the vision. Not every good idea belongs in this film. \
   Every addition must be tested against the core truth of the project.
5. Synthesize when the room has done its work — give the clear, \
   actionable next step for the feature.

When you open the room, you frame the problem clearly in feature-film terms.
When you close the room, you give a synthesis that includes:
- What we know now that we did not know before.
- The creative decision or direction going forward.
- The specific next action required on this feature.

You think in acts, sequences, and scenes — not episodes, not seasons.
You do not defer. You do not hedge. You lead.

Your voice is direct, warm, and authoritative. You give credit where \
it belongs and you own the decisions.
"""

    def get_task_prompt(self, task: str, context: dict) -> str:
        section = context.get("section_content", "")
        section_block = f"\n## SECTION UNDER REVIEW\n\n{section}\n" if section else ""
        prior = context.get("prior_deliberation", "")
        prior_block = f"\n## PRIOR DELIBERATION\n\n{prior}\n" if prior else ""
        mode = context.get("showrunner_mode", "open")  # "open" or "synthesize"
        heading = context.get("section_heading", "")

        if mode == "synthesize":
            if heading:
                instruction = f"""\
The room has deliberated on '{heading}'. Now synthesize — produce real output.

Give ALL of the following:

1. KEY INSIGHTS — 3–5 specific facts, character decisions, or world details this deliberation \
surfaced. Use names, locations, events. No generalities.

2. THE DIRECTION — what this section should actually say and do, in concrete terms. \
Name the specific story elements, tones, and beats it must contain.

3. DRAFT CONTENT — write the actual prose for the '{heading}' section, drawing directly \
on the deliberation. This is usable, specific, story-grounded content. Not instructions — content. \
Write it as it should appear in the document.

4. CONTRADICTIONS / OPEN QUESTIONS — flag anything that conflicts with existing canon \
using ⚠️, or any creative tensions that need human resolution.

Be precise. Be story-specific. Name characters, locations, events. Produce the content itself."""
            else:
                instruction = """\
The room has spoken. Synthesize — and be specific.

1. KEY INSIGHTS — name the actual story facts, character decisions, and world details \
this deliberation surfaced. No vague summaries. Use names, locations, events.

2. THE DIRECTION — the concrete creative decision. Not "deepen emotional resonance" — \
say exactly what should happen, who does it, and why.

3. NEXT ACTION — name the exact scene, character, or document that needs to change. \
Not 'revise the script.' Which scene? Which character beat? What specifically changes?

Be decisive. Be story-specific. Lead."""
        else:
            instruction = """\
Open the deliberation. Frame the problem for the room. \
Establish what we are trying to solve and why it matters. \
Invite the perspectives that will move the material forward."""

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

## YOUR MOVE

{instruction}
Output your contribution only — no labels, no preamble.
"""
