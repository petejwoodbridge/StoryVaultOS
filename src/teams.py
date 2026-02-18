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

    "the_room": {
        "label":       "THE ROOM",
        "description": "Full writers room. All voices. Best for big-picture story problems.",
        "agents":      ["showrunner", "producer", "structure", "character", "lore", "writer"],
        "temperature": 0.75,
        "max_tokens":  1200,
    },

    "pitch_team": {
        "label":       "PITCH TEAM",
        "description": "Package and sell. Best for loglines, treatments, and pitches.",
        "agents":      ["showrunner", "logline", "producer", "treatment"],
        "temperature": 0.70,
        "max_tokens":  1500,
    },

    "character_workshop": {
        "label":       "CHARACTER WORKSHOP",
        "description": "Deep dive on character. Psychology, want/need, arc, castability.",
        "agents":      ["showrunner", "character", "writer", "producer"],
        "temperature": 0.80,
        "max_tokens":  1200,
    },

    "world_team": {
        "label":       "WORLD TEAM",
        "description": "World-building and lore. Rules, factions, history, sensory detail.",
        "agents":      ["showrunner", "lore", "writer", "structure"],
        "temperature": 0.80,
        "max_tokens":  1200,
    },

    "structure_session": {
        "label":       "STRUCTURE SESSION",
        "description": "Beat sheets, act breaks, pilot spine, season engine.",
        "agents":      ["showrunner", "structure", "producer", "writer"],
        "temperature": 0.65,
        "max_tokens":  1500,
    },

    "development_pipeline": {
        "label":       "DEVELOPMENT PIPELINE",
        "description": "Full development pass. Concept → treatment → structure → notes.",
        "agents":      ["showrunner", "producer", "logline", "treatment", "structure", "character", "lore"],
        "temperature": 0.72,
        "max_tokens":  1200,
    },

    "audience_panel": {
        "label":       "AUDIENCE PANEL",
        "description": "Does this land? Will audiences care? Emotional resonance and clarity from a viewer's perspective.",
        "agents":      ["showrunner", "producer", "character", "writer"],
        "temperature": 0.80,
        "max_tokens":  1200,
    },
}


def get_team(team_id: str) -> dict | None:
    return TEAMS.get(team_id)


def list_teams() -> list[dict]:
    return [{"id": k, **v} for k, v in TEAMS.items()]
