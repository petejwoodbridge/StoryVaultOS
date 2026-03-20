"""
StoryVault Agent Teams
Defines deliberation team configurations. Each team is a curated set
of agents that work together on a specific type of creative problem.
"""

# Each team entry:
#   label       - display name shown in UI
#   description - what this team is best for
#   agents      - ordered list of agent keys (from AGENT_REGISTRY)
#                 showrunner opens and closes every deliberation
#   temperature - default LLM temperature for this team
#   max_tokens  - default max tokens per agent turn

TEAMS: dict[str, dict] = {

    # ── FULL ROOMS ────────────────────────────────────────────────────────── #

    "the_room": {
        "label":       "THE ROOM",
        "description": "Full writers room. All creative voices. Best for big-picture story problems and early development.",
        "agents":      ["showrunner", "writer", "character", "structure", "lore", "dialogue", "producer"],
        "temperature": 0.75,
        "max_tokens":  1200,
    },

    "development_pipeline": {
        "label":       "DEVELOPMENT PIPELINE",
        "description": "Complete development pass from concept to packaged project. Every specialist in sequence.",
        "agents":      ["showrunner", "producer", "marketing", "logline", "treatment", "structure", "character", "lore", "writer"],
        "temperature": 0.72,
        "max_tokens":  1200,
    },

    # ── CREATIVE ──────────────────────────────────────────────────────────── #

    "creative_table": {
        "label":       "CREATIVE TABLE",
        "description": "Pure craft. Story, character, world, voice — no commercial pressure. Best for creative breakthroughs.",
        "agents":      ["showrunner", "writer", "character", "lore", "dialogue"],
        "temperature": 0.82,
        "max_tokens":  1200,
    },

    "script_room": {
        "label":       "SCRIPT ROOM",
        "description": "Write, critique, revise. Focused on the page — drafting, notes, and polish.",
        "agents":      ["showrunner", "writer", "critic", "editor", "dialogue"],
        "temperature": 0.75,
        "max_tokens":  1400,
    },

    "structure_session": {
        "label":       "STRUCTURE SESSION",
        "description": "Beat sheets, act breaks, and story spine. Pure structure work.",
        "agents":      ["showrunner", "structure", "writer", "critic"],
        "temperature": 0.65,
        "max_tokens":  1500,
    },

    "character_workshop": {
        "label":       "CHARACTER WORKSHOP",
        "description": "Deep character work. Psychology, want/need, arc, voice, and castability.",
        "agents":      ["showrunner", "character", "dialogue", "writer", "audience"],
        "temperature": 0.80,
        "max_tokens":  1200,
    },

    "world_architect": {
        "label":       "WORLD ARCHITECT",
        "description": "World-building and lore. Rules, history, factions, sensory detail, internal logic.",
        "agents":      ["showrunner", "lore", "writer", "structure"],
        "temperature": 0.80,
        "max_tokens":  1200,
    },

    # ── COMMERCIAL ────────────────────────────────────────────────────────── #

    "greenlight_panel": {
        "label":       "GREENLIGHT PANEL",
        "description": "Commercial viability review. Is this worth making? Will it find an audience? Does it have a market?",
        "agents":      ["showrunner", "producer", "marketing", "logline"],
        "temperature": 0.68,
        "max_tokens":  1400,
    },

    "pitch_clinic": {
        "label":       "PITCH CLINIC",
        "description": "Package and sharpen the pitch. Logline to treatment, positioned to sell.",
        "agents":      ["showrunner", "logline", "treatment", "marketing", "producer"],
        "temperature": 0.70,
        "max_tokens":  1500,
    },

    "audience_test": {
        "label":       "AUDIENCE TEST",
        "description": "Does it land with real people? Emotional resonance, word-of-mouth, and market positioning.",
        "agents":      ["showrunner", "audience", "marketing", "character", "producer"],
        "temperature": 0.78,
        "max_tokens":  1200,
    },

}


def get_team(team_id: str) -> dict | None:
    return TEAMS.get(team_id)


def list_teams() -> list[dict]:
    return [{"id": k, **v} for k, v in TEAMS.items()]
