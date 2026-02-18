"""
StoryVault Deliberation Engine
Orchestrates multi-agent deliberation with streaming SSE output.

Each deliberation:
1. Showrunner opens the room (frames the problem)
2. Each specialist agent contributes in turn (streaming)
3. Showrunner synthesizes (decision + next action)

Yields SSE event dicts throughout.
"""

from .agents import AGENT_REGISTRY
from .teams  import get_team


class DeliberationEngine:
    def __init__(self, openai_client, project_path: str, config):
        self.client       = openai_client
        self.project_path = project_path
        self.config       = config

    # ------------------------------------------------------------------ #
    # Public — yields SSE event dicts
    # ------------------------------------------------------------------ #

    def run(self, task: str, team_id: str, context: dict | None = None, rounds: int = 1):
        """
        Run a full deliberation for the given team.

        Yields dicts:
          {'type': 'session_start', 'team': str, 'agents': list[str]}
          {'type': 'round_start',   'round': int, 'total': int}
          {'type': 'agent_start',   'agent': str, 'key': str}
          {'type': 'chunk',         'agent': str, 'content': str}
          {'type': 'agent_done',    'agent': str, 'tokens': int, 'cost': float}
          {'type': 'synthesis_start'}
          {'type': 'done',          'total_tokens': int, 'total_cost': float}
          {'type': 'error',         'message': str}
        """
        team = get_team(team_id)
        if not team:
            yield {"type": "error", "message": f"Unknown team: {team_id}"}
            return

        ctx         = dict(context or {})
        temperature = team.get("temperature", 0.75)
        max_tokens  = team.get("max_tokens",  1200)
        agent_keys  = team["agents"]
        rounds      = max(1, min(int(rounds), 5))

        yield {
            "type":   "session_start",
            "team":   team["label"],
            "agents": [self._role_label(k) for k in agent_keys],
        }

        # Mutable state shared across turns
        state = {"transcript": "", "total_tokens": 0, "total_cost": 0.0}

        # 1. Showrunner opens
        yield from self._agent_turn(
            agent_key   = "showrunner",
            task        = task,
            ctx         = {**ctx, "showrunner_mode": "open"},
            temperature = temperature,
            max_tokens  = max_tokens,
            state       = state,
        )

        # 2. Specialists — repeated for each round
        for round_num in range(rounds):
            if rounds > 1:
                yield {"type": "round_start", "round": round_num + 1, "total": rounds}
            for key in agent_keys:
                if key == "showrunner":
                    continue
                yield from self._agent_turn(
                    agent_key   = key,
                    task        = task,
                    ctx         = {**ctx, "prior_deliberation": state["transcript"]},
                    temperature = temperature,
                    max_tokens  = max_tokens,
                    state       = state,
                )

        # 3. Showrunner synthesizes
        yield {"type": "synthesis_start"}
        yield from self._agent_turn(
            agent_key   = "showrunner",
            task        = task,
            ctx         = {**ctx,
                           "showrunner_mode":    "synthesize",
                           "prior_deliberation": state["transcript"]},
            temperature = max(0.5, temperature - 0.1),
            max_tokens  = max_tokens + 400,
            state       = state,
        )

        yield {
            "type":         "done",
            "total_tokens": state["total_tokens"],
            "total_cost":   round(state["total_cost"], 6),
        }

    # ------------------------------------------------------------------ #
    # Single agent turn — streams chunks, updates state
    # ------------------------------------------------------------------ #

    def _agent_turn(
        self,
        agent_key:   str,
        task:        str,
        ctx:         dict,
        temperature: float,
        max_tokens:  int,
        state:       dict,
    ):
        AgentClass = AGENT_REGISTRY.get(agent_key)
        if not AgentClass:
            yield {"type": "error", "message": f"Unknown agent: {agent_key}"}
            return

        agent      = AgentClass(self.client, self.project_path, self.config)
        role_label = getattr(agent, "role_label", agent_key.upper())

        yield {"type": "agent_start", "agent": role_label, "key": agent_key}

        parts = []
        usage = {}

        try:
            for chunk in agent.run_stream(task, ctx, temperature, max_tokens):
                if isinstance(chunk, str):
                    parts.append(chunk)
                    yield {"type": "chunk", "agent": role_label, "content": chunk}
                elif isinstance(chunk, dict):
                    usage = chunk

            full_text = "".join(parts)
            state["transcript"]   += f"\n\n---\n**{role_label}:**\n\n{full_text}"
            state["total_tokens"] += usage.get("total_tokens", 0)
            state["total_cost"]   += usage.get("cost", 0.0)

            yield {
                "type":   "agent_done",
                "agent":  role_label,
                "tokens": usage.get("total_tokens", 0),
                "cost":   round(usage.get("cost", 0.0), 6),
            }

        except Exception as exc:
            yield {"type": "error", "message": f"{role_label}: {str(exc)}"}

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _role_label(self, key: str) -> str:
        cls = AGENT_REGISTRY.get(key)
        if cls:
            obj = cls.__new__(cls)
            return getattr(obj, "role_label", key.upper())
        return key.upper()
