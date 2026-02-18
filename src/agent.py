"""
StoryVault Base Agent
All agents inherit from BaseAgent. No agent may write directly to any file.
All output goes through the proposal system.
"""

import os
import json
from abc import ABC, abstractmethod

# Maximum total characters of KB content injected per agent call
_KB_MAX_CHARS    = 6000   # reduced to make room for WorldBible
_KB_MAX_PER_DOC  = 1000

# WorldBible context limits
_WB_MAX_CHARS    = 5000   # narrative sections (overview, lore, logic, tone, structure)
_RULES_MAX_CHARS = 2000   # world rules — always injected in full (should be concise)

# ──────────────────────────────────────────────────────────────────────────────
# Agent role overrides — stored globally in ~/.storyvault/agent_overrides.json
# Lets users customise any agent's system prompt without editing source files.
# ──────────────────────────────────────────────────────────────────────────────
_OVERRIDES_PATH = os.path.join(os.path.expanduser("~"), ".storyvault", "agent_overrides.json")


def _load_overrides() -> dict:
    if os.path.exists(_OVERRIDES_PATH):
        try:
            with open(_OVERRIDES_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def get_role_override(agent_name: str) -> str | None:
    """Return the custom role for agent_name, or None if using default."""
    overrides = _load_overrides()
    val = overrides.get(agent_name, "")
    return val if val else None


def save_role_override(agent_name: str, role: str) -> None:
    """Persist a custom role for agent_name. Empty string clears override."""
    overrides = _load_overrides()
    overrides[agent_name] = role.strip()
    os.makedirs(os.path.dirname(_OVERRIDES_PATH), exist_ok=True)
    with open(_OVERRIDES_PATH, "w", encoding="utf-8") as f:
        json.dump(overrides, f, indent=2)


# ──────────────────────────────────────────────────────────────────────────────
# Shared cinematic methodology injected into every agent's system prompt.
# Grounds all agents in McKee, Syd Field, Save the Cat, Hero's Journey.
# ──────────────────────────────────────────────────────────────────────────────
CINEMATIC_METHODOLOGY = """
════════════════════════════════════════════════════════════
CINEMATIC CRAFT FOUNDATIONS
────────────────────────────────────────────────────────────
This is FEATURE FILM. Not television. Not episodic series.
A single, complete, 90-120 minute cinematic experience.
Every creative decision serves that singular vision.

McKEE — STORY
• Every scene must turn on a value charge (positive ↔ negative).
• The gap between expectation and outcome is where drama lives.
• Story is structured conflict — not coincidence, not incident.
• Climax: the protagonist must make the greatest possible sacrifice.

SYD FIELD — THREE-ACT PARADIGM
• Act I (pp 1-30): Establish world → Inciting Incident →
  Plot Point I: the event that spins the story into Act II.
• Act II (pp 30-90): Confrontation. Rising stakes. Midpoint
  (false peak or false valley) → Plot Point II: darkest moment,
  spinning into Act III.
• Act III (pp 90-120): Climax. Resolution. New equilibrium.
• Write in pictures. This is a visual medium. Show, don't tell.

BLAKE SNYDER — SAVE THE CAT (BEAT SHEET)
• Opening Image (p.1): snapshot of the world before transformation.
• Theme Stated (p.5): someone tells the hero what the film is about.
• Catalyst / Inciting Incident (p.12): the world changes forever.
• Break Into Two (p.25): protagonist enters the upside-down world.
• Midpoint (p.55): false victory or false defeat — stakes double.
• All Is Lost (p.75): whiff of death. The hero's lowest moment.
• Dark Night of the Soul (pp 75-85): the hero must transform.
• Break Into Three (p.85): synthesis of new understanding.
• Finale (pp 85-110): the hero proves the theme by acting on it.

JOSEPH CAMPBELL / CHRISTOPHER VOGLER — THE HERO'S JOURNEY
Ordinary World → Call to Adventure → Refusal of the Call →
Mentor → Crossing the Threshold → Tests, Allies, Enemies →
Approach to the Inmost Cave → The Ordeal → Reward →
The Road Back → Resurrection → Return with the Elixir.
The hero must die and be reborn — carrying what the world needs.

CINEMATIC WRITING STANDARDS
• Visual storytelling: if it can't be filmed, it doesn't belong on the page.
• Subtext is everything: characters rarely say what they mean.
• Economy: every scene, every word earns its place or is cut.
• Emotional logic drives the story — feeling first, plot second.
• Hollywood-level craft: every scene must justify its runtime.
════════════════════════════════════════════════════════════
"""


def _build_kb_system_block(kb_text: str) -> str:
    """Format KB documents for injection into the agent system prompt."""
    if not kb_text.strip():
        return ""
    return f"""

════════════════════════════════════════════════════════════
KNOWLEDGE BASE — ENTITY DETAILS
────────────────────────────────────────────────────────────
Specific characters, locations, creatures, objects and events in this storyworld.
These are ground-truth facts. Do NOT contradict them.
All changes go through the proposal system — you never write directly.
────────────────────────────────────────────────────────────

{kb_text}

════════════════════════════════════════════════════════════
"""


def _build_world_rules_block(rules_text: str) -> str:
    """Format World Rules for injection as mandatory constraints."""
    if not rules_text.strip():
        return ""
    return f"""

████████████████████████████████████████████████████████████
MANDATORY WORLD RULES — NON-NEGOTIABLE
────────────────────────────────────────────────────────────
These rules define the absolute laws of this storyworld.
You MUST follow them in every output, no exceptions.
If a task would require violating these rules, flag it explicitly.
────────────────────────────────────────────────────────────

{rules_text[:_RULES_MAX_CHARS]}

████████████████████████████████████████████████████████████
"""


def _build_world_bible_block(wb_text: str) -> str:
    """Format WorldBible narrative context for injection into agent system prompts."""
    if not wb_text.strip():
        return ""
    return f"""

════════════════════════════════════════════════════════════
STORY WORLD BIBLE — PRIMARY NARRATIVE REFERENCE
────────────────────────────────────────────────────────────
This is the master narrative framework for this storyworld.
All agent output must be consistent with this reference.
────────────────────────────────────────────────────────────

{wb_text}

════════════════════════════════════════════════════════════
"""


class BaseAgent(ABC):
    name  = "BaseAgent"
    role  = "You are a helpful assistant."

    def __init__(self, openai_client, project_path: str, config):
        self.client       = openai_client
        self.project_path = project_path
        self.config       = config

    # ------------------------------------------------------------------ #
    # Abstract interface - subclasses implement task prompt
    # ------------------------------------------------------------------ #

    @abstractmethod
    def get_task_prompt(self, task: str, context: dict) -> str:
        """Return the user-turn message for this agent given task + context."""

    # ------------------------------------------------------------------ #
    # Context loaders
    # ------------------------------------------------------------------ #

    def _load_canon(self) -> str:
        p = os.path.join(self.project_path, "Canon", "Canon.md")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return f.read()
        return "No canon established yet."

    def _load_working_memory(self) -> str:
        p = os.path.join(self.project_path, "Memory", "WorkingMemory.md")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return f.read()
        return "No working memory yet."

    def _load_kb_documents(self) -> str:
        """
        Load all Knowledge Base documents and return as a structured string.
        Capped per-document and in total to control token usage.
        Priority order: character, creature, location, world, bible, object, event, others.
        """
        docs_root = os.path.join(self.project_path, "Documents")
        if not os.path.isdir(docs_root):
            return ""

        # Priority-ordered folder map
        _PRIORITY = [
            ("Characters",    "Character"),
            ("Creatures",     "Supporting Character"),
            ("Locations",     "Location"),
            ("WorldBuilding", "World Building"),
            ("Bible",         "Story Bible"),
            ("Objects",       "Object"),
            ("Events",        "Event"),
            ("Treatments",    "Treatment"),
            ("BeatSheets",    "Beat Sheet"),
            ("Loglines",      "Logline"),
            ("Episodes",      "Episode"),
        ]

        parts = []
        total_chars = 0

        for folder_name, type_label in _PRIORITY:
            folder = os.path.join(docs_root, folder_name)
            if not os.path.isdir(folder):
                continue
            for fname in sorted(os.listdir(folder)):
                if not fname.endswith(".meta.json"):
                    continue
                slug = fname[:-len(".meta.json")]
                md_path = os.path.join(folder, f"{slug}.md")
                if not os.path.exists(md_path):
                    continue
                try:
                    with open(os.path.join(folder, fname), encoding="utf-8") as f:
                        meta = json.load(f)
                    with open(md_path, encoding="utf-8") as f:
                        content = f.read()
                    title = meta.get("title", slug)
                    if len(content) > _KB_MAX_PER_DOC:
                        content = content[:_KB_MAX_PER_DOC] + "\n[...truncated]"
                    block = f"### {title} ({type_label})\n{content}"
                    if total_chars + len(block) > _KB_MAX_CHARS:
                        break
                    parts.append(block)
                    total_chars += len(block)
                except Exception:
                    pass

        return "\n\n---\n\n".join(parts)

    def _load_world_bible(self) -> str:
        """Load WorldBible narrative sections for agent context."""
        try:
            from src.world_bible import WorldBibleManager
            wbm = WorldBibleManager(self.project_path)
            return wbm.get_context_for_agents(max_chars=_WB_MAX_CHARS)
        except Exception:
            return ""

    def _load_world_rules(self) -> str:
        """Load WorldBible World Rules — injected as mandatory constraints."""
        try:
            from src.world_bible import WorldBibleManager
            wbm = WorldBibleManager(self.project_path)
            return wbm.get_world_rules()
        except Exception:
            return ""

    def _load_file(self, filepath: str) -> str:
        if os.path.exists(filepath):
            with open(filepath, encoding="utf-8") as f:
                return f.read()
        return ""

    # ------------------------------------------------------------------ #
    # Run (read-only — returns content + usage, writes nothing)
    # ------------------------------------------------------------------ #

    def run(
        self,
        task: str,
        context: dict | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> tuple[str, dict]:
        """
        Call the LLM and return (content, usage).
        Does NOT write to any file.
        """
        ctx = dict(context or {})
        ctx.setdefault("canon",          self._load_canon())
        ctx.setdefault("working_memory", self._load_working_memory())
        ctx.setdefault("kb_documents",   self._load_kb_documents())
        ctx.setdefault("world_bible",    self._load_world_bible())
        ctx.setdefault("world_rules",    self._load_world_rules())

        # Inject character focus into working memory if provided
        if ctx.get("character_focus"):
            ctx["working_memory"] = (
                ctx["working_memory"]
                + f"\n\n## CHARACTER IN FOCUS\n\n{ctx['character_focus']}"
            )

        effective_role   = get_role_override(self.name) or self.role
        rules_block      = _build_world_rules_block(ctx.get("world_rules", ""))
        wb_block         = _build_world_bible_block(ctx.get("world_bible", ""))
        kb_block         = _build_kb_system_block(ctx.get("kb_documents", ""))
        messages = [
            {"role": "system", "content": effective_role + "\n" + CINEMATIC_METHODOLOGY + rules_block + wb_block + kb_block},
            {"role": "user",   "content": self.get_task_prompt(task, ctx)},
        ]

        content, usage = self.client.complete(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return content, usage

    def run_stream(
        self,
        task: str,
        context: dict | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ):
        """
        Stream LLM output. Yields str chunks, then a final usage dict.
        Does NOT write to any file.
        """
        ctx = dict(context or {})
        ctx.setdefault("canon",          self._load_canon())
        ctx.setdefault("working_memory", self._load_working_memory())
        ctx.setdefault("kb_documents",   self._load_kb_documents())
        ctx.setdefault("world_bible",    self._load_world_bible())
        ctx.setdefault("world_rules",    self._load_world_rules())

        # Inject character focus into working memory if provided
        if ctx.get("character_focus"):
            ctx["working_memory"] = (
                ctx["working_memory"]
                + f"\n\n## CHARACTER IN FOCUS\n\n{ctx['character_focus']}"
            )

        effective_role   = get_role_override(self.name) or self.role
        rules_block      = _build_world_rules_block(ctx.get("world_rules", ""))
        wb_block         = _build_world_bible_block(ctx.get("world_bible", ""))
        kb_block         = _build_kb_system_block(ctx.get("kb_documents", ""))
        messages = [
            {"role": "system", "content": effective_role + "\n" + CINEMATIC_METHODOLOGY + rules_block + wb_block + kb_block},
            {"role": "user",   "content": self.get_task_prompt(task, ctx)},
        ]

        yield from self.client.complete_stream(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    # ------------------------------------------------------------------ #
    # Propose (runs agent, creates a proposal — still writes nothing final)
    # ------------------------------------------------------------------ #

    def propose(
        self,
        task: str,
        target_file: str,
        proposal_manager,
        context: dict | None = None,
        proposal_type: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> tuple[str, dict, dict]:
        """
        Run the agent and submit output as a proposal.

        Returns:
            (proposal_id, proposal_data, usage)
        """
        content, usage = self.run(task, context, temperature, max_tokens)
        rationale = f"Generated by {self.name}.\nTask: {task}"
        p_type = proposal_type or f"{self.name.lower().replace('agent','')}-update"

        prop_id, prop_data = proposal_manager.create(
            agent_name=self.name,
            proposal_type=p_type,
            target_file=target_file,
            new_content=content,
            rationale=rationale,
        )
        return prop_id, prop_data, usage
