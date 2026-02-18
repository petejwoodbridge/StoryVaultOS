"""
StoryVault Web API
Flask backend serving terminal-style UI and JSON API.
"""

import os
import re
import sys
import json

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, request, render_template, Response, stream_with_context, send_file

from src.config        import Config
from src.project       import ProjectManager
from src.proposal      import ProposalManager
from src.canon         import CanonManager
from src.memory        import MemoryManager
from src.scene         import SceneManager
from src.export        import ExportEngine
from src.version       import VersionTracker
from src.openai_client import OpenAIClient
from src.agents        import AGENT_REGISTRY
from src.deliberation  import DeliberationEngine
from src.teams         import list_teams, get_team
from src.documents     import DocumentsManager, DOC_TYPES
from src.graph         import CanonGraphExtractor
from src.world_bible   import WorldBibleManager

app = Flask(__name__, template_folder="templates")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def cfg() -> Config:
    return Config()

def ok(data: dict | None = None, **kw):
    d = data or {}
    d.update(kw)
    return jsonify(d)

def err(msg: str, code: int = 400):
    return jsonify({"error": msg}), code

def project_path(c: Config | None = None) -> str | None:
    c = c or cfg()
    return c.project_path()

def require_project():
    c = cfg()
    p = c.project_path()
    if not p or not os.path.isdir(p):
        return None, None, err("No active project. Select one first.", 400)
    return c, p, None


# ─── Main page ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ─── Projects ────────────────────────────────────────────────────────────────

@app.route("/api/projects")
def list_projects():
    c = cfg()
    pm = ProjectManager(c.vault_path)
    return ok(projects=pm.list_projects(), current=c.current_project)


@app.route("/api/project/switch", methods=["POST"])
def switch_project():
    name = (request.json or {}).get("name", "").strip()
    if not name:
        return err("Name required")
    c = cfg()
    pm = ProjectManager(c.vault_path)
    if not pm.exists(name):
        return err(f"Project not found: {name}")
    c.current_project = name
    return ok(current=name)


@app.route("/api/project/create", methods=["POST"])
def create_project():
    raw = (request.json or {}).get("name", "")
    name = "_".join(raw.upper().split())
    if not name:
        return err("Name required")
    c = cfg()
    pm = ProjectManager(c.vault_path)
    success, msg = pm.create(name)
    if not success:
        return err(msg)
    c.current_project = name
    return ok(name=name, msg=msg)


# ─── Status ──────────────────────────────────────────────────────────────────

@app.route("/api/status")
def status():
    c, p, e = require_project()
    if e:
        return ok(project=None, model=cfg().model, api_key_set=bool(cfg().api_key),
                  tracking=cfg().token_tracking)

    pm = ProjectManager(c.vault_path)
    s  = pm.get_status(p)
    vt = VersionTracker(p)
    return ok(
        project=c.current_project,
        model=c.model,
        api_key_set=bool(c.api_key),
        tracking=c.token_tracking,
        version_stats=vt.get_stats(),
        **s,
    )


# ─── Canon ───────────────────────────────────────────────────────────────────

@app.route("/api/canon")
def get_canon():
    c, p, e = require_project()
    if e: return e
    cm = CanonManager(p)
    content, error = cm.read()
    if error: return err(error)
    return ok(content=content, locked=cm.is_locked(), lock_info=cm.get_lock_info())


@app.route("/api/canon/save", methods=["POST"])
def save_canon():
    c, p, e = require_project()
    if e: return e
    cm = CanonManager(p)
    if cm.is_locked():
        return err("Canon is LOCKED. Unlock first.")
    content = (request.json or {}).get("content", "")
    pm = ProposalManager(p)
    prop_id, _ = pm.create("Manual-User", "canon-direct-edit", cm.canon_path,
                            content, "Direct edit via StoryVault web UI.")
    ok_r, msg = pm.approve(prop_id)
    if ok_r:
        VersionTracker(p).commit(pm.get(prop_id))
        return ok(prop_id=prop_id)
    return err(msg)


@app.route("/api/canon/lock", methods=["POST"])
def lock_canon():
    c, p, e = require_project()
    if e: return e
    success, msg = CanonManager(p).lock()
    return ok(msg=msg) if success else err(msg)


@app.route("/api/canon/unlock", methods=["POST"])
def unlock_canon():
    c, p, e = require_project()
    if e: return e
    success, msg = CanonManager(p).unlock()
    return ok(msg=msg) if success else err(msg)


# ─── Memory ──────────────────────────────────────────────────────────────────

@app.route("/api/memory")
def get_memory():
    c, p, e = require_project()
    if e: return e
    mm = MemoryManager(p)
    return ok(content=mm.read_working(), size_bytes=mm.get_size_bytes(),
              size_display=mm.get_size_display(), episodic_count=len(mm.list_episodic()))


@app.route("/api/memory/save", methods=["POST"])
def save_memory():
    c, p, e = require_project()
    if e: return e
    content = (request.json or {}).get("content", "")
    mm = MemoryManager(p)
    pm = ProposalManager(p)
    prop_id, _ = pm.create("Manual-User", "memory-direct-edit", mm.working_path,
                            content, "Direct edit via StoryVault web UI.")
    ok_r, msg = pm.approve(prop_id)
    if ok_r:
        VersionTracker(p).commit(pm.get(prop_id))
        return ok()
    return err(msg)


@app.route("/api/memory/append", methods=["POST"])
def append_memory():
    """Append text to the end of WorkingMemory.md."""
    c, p, e = require_project()
    if e: return e
    text = (request.json or {}).get("text", "").strip()
    if not text: return err("text required")
    mm = MemoryManager(p)
    current = mm.read_working() or ""
    new_content = current.rstrip() + "\n\n" + text
    pm = ProposalManager(p)
    prop_id, _ = pm.create("Manual-User", "memory-append", mm.working_path,
                            new_content, "Appended via StoryVault web UI.")
    ok_r, msg = pm.approve(prop_id)
    if ok_r:
        VersionTracker(p).commit(pm.get(prop_id))
        return ok()
    return err(msg)


# ─── Scenes ──────────────────────────────────────────────────────────────────

@app.route("/api/scenes")
def list_scenes():
    c, p, e = require_project()
    if e: return ok(scenes=[])
    return ok(scenes=SceneManager(p).list_scenes())


@app.route("/api/scenes/create", methods=["POST"])
def create_scene():
    c, p, e = require_project()
    if e: return e
    data = request.json or {}
    try:
        num = int(data.get("num", 0))
    except (ValueError, TypeError):
        return err("num must be an integer")
    if not num:
        return err("Scene number required")
    sm = SceneManager(p)
    success, msg = sm.create(num, data.get("title",""), data.get("location",""),
                              data.get("time_of_day",""), data.get("description",""))
    return ok(msg=msg) if success else err(msg)


@app.route("/api/scenes/<int:num>")
def get_scene(num):
    c, p, e = require_project()
    if e: return e
    sm   = SceneManager(p)
    meta = sm.get_meta(num)
    if not meta: return err(f"Scene {num} not found")
    return ok(meta=meta, locked=sm.is_locked(num), card=sm.get_card(num),
              draft=sm.get_draft(num), critique=sm.get_critique(num),
              revision=sm.get_revision(num))


@app.route("/api/scenes/<int:num>/approve", methods=["POST"])
def approve_scene_route(num):
    c, p, e = require_project()
    if e: return e
    sm = SceneManager(p)
    if not sm.get_meta(num): return err(f"Scene {num} not found")
    if sm.is_locked(num):    return err(f"Scene {num} already locked")
    if not sm.get_best_content(num): return err("No content to approve")
    sm.lock(num)
    sm.update_phase(num, "APPROVED")
    return ok(msg=f"Scene {num:02d} approved and locked")


# ─── Proposals ───────────────────────────────────────────────────────────────

@app.route("/api/proposals")
def list_proposals():
    c, p, e = require_project()
    if e: return ok(proposals=[])
    pm     = ProposalManager(p)
    status = request.args.get("status", "PENDING")
    raw    = pm.list_all() if status == "ALL" else pm.list_pending()

    compact = []
    for prop in raw:
        tf = prop.get("target_file", "")
        compact.append({
            "id":          prop["id"],
            "agent":       prop.get("agent", ""),
            "type":        prop.get("type", ""),
            "status":      prop.get("status", ""),
            "created":     prop.get("created", ""),
            "target_file": os.path.relpath(tf, p) if os.path.isabs(tf) else tf,
        })
    return ok(proposals=compact)


@app.route("/api/proposals/<prop_id>")
def get_proposal(prop_id):
    c, p, e = require_project()
    if e: return e
    data = ProposalManager(p).get(prop_id)
    if not data: return err("Proposal not found")
    tf = data.get("target_file", "")
    data["target_file_rel"] = os.path.relpath(tf, p) if os.path.isabs(tf) else tf
    return ok(**data)


@app.route("/api/proposals/<prop_id>/approve", methods=["POST"])
def approve_proposal(prop_id):
    c, p, e = require_project()
    if e: return e
    pm   = ProposalManager(p)
    data = pm.get(prop_id)
    if not data: return err("Proposal not found")

    # Canon lock guard
    target     = data.get("target_file", "")
    canon_path = os.path.join(p, "Canon", "Canon.md")
    if os.path.normpath(target) == os.path.normpath(canon_path):
        if CanonManager(p).is_locked():
            return err("Canon is LOCKED. Unlock first.")

    success, msg = pm.approve(prop_id)
    if not success: return err(msg)
    commit_id = VersionTracker(p).commit(pm.get(prop_id))
    return ok(msg=msg, commit_id=commit_id)


@app.route("/api/proposals/<prop_id>/reject", methods=["POST"])
def reject_proposal(prop_id):
    c, p, e = require_project()
    if e: return e
    reason = (request.json or {}).get("reason", "")
    pm = ProposalManager(p)
    success, msg = pm.reject(prop_id, reason)
    if not success: return err(msg)
    VersionTracker(p).commit(pm.get(prop_id))
    return ok(msg=msg)


# ─── Agents ──────────────────────────────────────────────────────────────────

def _run_agent(agent_type, task, target_file, project_path, config,
               context=None, proposal_type=None):
    """Shared agent execution helper. Returns (prop_id, usage) or raises."""
    client = OpenAIClient(config.api_key, config.model)
    pm     = ProposalManager(project_path)
    agent  = AGENT_REGISTRY[agent_type](client, project_path, config)

    prop_id, _, usage = agent.propose(
        task=task, target_file=target_file, proposal_manager=pm,
        context=context, proposal_type=proposal_type,
    )
    config.add_tokens(usage.get("prompt_tokens", 0),
                      usage.get("completion_tokens", 0),
                      usage.get("cost", 0.0))
    return prop_id, usage


@app.route("/api/agents/run", methods=["POST"])
def run_agent():
    c, p, e = require_project()
    if e: return e
    if not c.api_key: return err("No API key configured")

    data       = request.json or {}
    agent_type = data.get("agent", "").lower()
    task       = data.get("task", "").strip()
    target_rel = data.get("target", "").strip()

    if agent_type not in AGENT_REGISTRY: return err(f"Unknown agent: {agent_type}")
    if not task:       return err("Task required")
    if not target_rel: return err("Target file required")

    try:
        prop_id, usage = _run_agent(
            agent_type, task, os.path.join(p, target_rel), p, c,
            context=data.get("context", {}),
            proposal_type=data.get("proposal_type"),
        )
        return ok(proposal_id=prop_id, usage=usage)
    except Exception as ex:
        return err(str(ex))


@app.route("/api/agents/draft-scene", methods=["POST"])
def draft_scene():
    c, p, e = require_project()
    if e: return e
    if not c.api_key: return err("No API key")
    num = int((request.json or {}).get("scene_num", 0))
    if not num: return err("scene_num required")
    try:
        sm = SceneManager(p)
        if not sm.get_meta(num):     return err(f"Scene {num} not found")
        if sm.is_locked(num):        return err(f"Scene {num} is locked")
        prop_id, usage = _run_agent(
            "writer",
            f"Draft scene {num:02d}. Write the full scene as a screenplay excerpt. "
            f"ANA narrates all dialogue. Keep it mostly visual.",
            sm.scene_file(num, "draft.md"), p, c,
            context={"current_content": sm.get_card(num)},
            proposal_type="scene-draft",
        )
        sm.update_phase(num, "DRAFTED")
        return ok(proposal_id=prop_id, usage=usage)
    except Exception as ex:
        return err(str(ex))


@app.route("/api/agents/critique-scene", methods=["POST"])
def critique_scene():
    c, p, e = require_project()
    if e: return e
    if not c.api_key: return err("No API key")
    num = int((request.json or {}).get("scene_num", 0))
    if not num: return err("scene_num required")
    try:
        sm = SceneManager(p)
        if not sm.get_meta(num): return err(f"Scene {num} not found")
        if sm.is_locked(num):    return err(f"Scene {num} is locked")
        content = sm.get_draft(num) or sm.get_card(num)
        prop_id, usage = _run_agent(
            "critic",
            f"Critique scene {num:02d} for dramatic effectiveness, visual storytelling, "
            f"and canon fidelity. Remember: ANA narrates all dialogue.",
            sm.scene_file(num, "critique.md"), p, c,
            context={"current_content": content},
            proposal_type="scene-critique",
        )
        sm.update_phase(num, "CRITIQUED")
        return ok(proposal_id=prop_id, usage=usage)
    except Exception as ex:
        return err(str(ex))


@app.route("/api/agents/revise-scene", methods=["POST"])
def revise_scene():
    c, p, e = require_project()
    if e: return e
    if not c.api_key: return err("No API key")
    num = int((request.json or {}).get("scene_num", 0))
    if not num: return err("scene_num required")
    try:
        sm = SceneManager(p)
        if not sm.get_meta(num): return err(f"Scene {num} not found")
        if sm.is_locked(num):    return err(f"Scene {num} is locked")
        prop_id, usage = _run_agent(
            "editor",
            f"Revise scene {num:02d} based on critique notes. Produce the complete revised scene.",
            sm.scene_file(num, "revision.md"), p, c,
            context={"current_content": sm.get_draft(num),
                     "critique": sm.get_critique(num)},
            proposal_type="scene-revision",
        )
        sm.update_phase(num, "REVISED")
        return ok(proposal_id=prop_id, usage=usage)
    except Exception as ex:
        return err(str(ex))


@app.route("/api/agents/compress-memory", methods=["POST"])
def compress_memory():
    c, p, e = require_project()
    if e: return e
    if not c.api_key: return err("No API key")
    try:
        mm      = MemoryManager(p)
        archive = mm.archive_working()
        prop_id, usage = _run_agent(
            "archivist",
            "Compress and restructure the working memory. Target 30–50% of original length.",
            mm.working_path, p, c,
            proposal_type="memory-compression",
        )
        return ok(proposal_id=prop_id, usage=usage,
                  archived_to=os.path.relpath(archive, p) if archive else "")
    except Exception as ex:
        return err(str(ex))


# ─── Export ──────────────────────────────────────────────────────────────────

@app.route("/api/export", methods=["POST"])
def export_screenplay():
    c, p, e = require_project()
    if e: return e
    include_all = (request.json or {}).get("include_all", False)
    try:
        output_path, content = ExportEngine(p).export(include_unapproved=include_all)
        return ok(path=output_path, content=content)
    except Exception as ex:
        return err(str(ex))


# ─── Tokens / History ────────────────────────────────────────────────────────

@app.route("/api/tokens")
def get_tokens():
    c   = cfg()
    res = {"tracking": c.token_tracking}
    if c.current_project:
        p = c.project_path()
        if p and os.path.isdir(p):
            res["stats"] = VersionTracker(p).get_stats()
    return ok(**res)


@app.route("/api/commits")
def get_commits():
    c, p, e = require_project()
    if e: return ok(commits=[])
    limit   = int(request.args.get("limit", 50))
    commits = VersionTracker(p).list_commits(limit)
    return ok(commits=list(reversed(commits)))


# ─── Teams ───────────────────────────────────────────────────────────────────

@app.route("/api/teams")
def get_teams():
    return ok(teams=list_teams())


# ─── Deliberation (SSE streaming) ────────────────────────────────────────────

@app.route("/api/deliberate/stream", methods=["POST"])
def deliberate_stream():
    c, p, e = require_project()
    if e:
        def error_gen():
            yield f"data: {json.dumps({'type': 'error', 'message': 'No active project'})}\n\n"
            yield "data: [DONE]\n\n"
        return Response(stream_with_context(error_gen()), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    if not c.api_key:
        def nokey_gen():
            yield f"data: {json.dumps({'type': 'error', 'message': 'No API key configured'})}\n\n"
            yield "data: [DONE]\n\n"
        return Response(stream_with_context(nokey_gen()), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    data    = request.json or {}
    task    = data.get("task", "").strip()
    team_id = data.get("team", "the_room")
    context = data.get("context", {})

    if not task:
        def notask_gen():
            yield f"data: {json.dumps({'type': 'error', 'message': 'Task required'})}\n\n"
            yield "data: [DONE]\n\n"
        return Response(stream_with_context(notask_gen()), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    rounds  = max(1, min(int(data.get("rounds", 1)), 5))
    client  = OpenAIClient(c.api_key, c.model)
    engine  = DeliberationEngine(client, p, c)

    def generate():
        total_tokens = 0
        total_cost   = 0.0
        try:
            for event in engine.run(task, team_id, context, rounds=rounds):
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") == "done":
                    total_tokens = event.get("total_tokens", 0)
                    total_cost   = event.get("total_cost", 0.0)
        except Exception as ex:
            yield f"data: {json.dumps({'type': 'error', 'message': str(ex)})}\n\n"
        finally:
            if total_tokens:
                c.add_tokens(0, 0, total_cost)
            yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─── Canon sections ──────────────────────────────────────────────────────────

def _extract_section(canon_text: str, heading: str) -> str | None:
    """Pull out the body of a ## section from canon text."""
    sections = DocumentsManager.parse_canon_sections(canon_text)
    for s in sections:
        if s["heading"].strip() == heading.strip():
            return s["content"]
    return None


def _replace_section(canon_text: str, heading: str, new_body: str) -> tuple[str, bool]:
    """Replace the body of ## heading in canon_text. Returns (new_text, success)."""
    new_lines  = []
    in_target  = False
    updated    = False
    for line in canon_text.split("\n"):
        if line.startswith("## ") and line[3:].strip() == heading.strip():
            in_target = True
            new_lines.append(line)
            new_lines.append("")
            new_lines.extend(new_body.split("\n"))
            new_lines.append("")
            updated = True
            continue
        if in_target and line.startswith("## "):
            in_target = False
        if not in_target:
            new_lines.append(line)
    return "\n".join(new_lines), updated


@app.route("/api/canon/sections")
def get_canon_sections():
    c, p, e = require_project()
    if e: return e
    cm = CanonManager(p)
    content, error = cm.read()
    if error: return err(error)
    sections = DocumentsManager.parse_canon_sections(content)
    return ok(sections=sections, locked=cm.is_locked())


@app.route("/api/canon/section/save", methods=["POST"])
def save_canon_section():
    """Save a single canon section back into Canon.md."""
    c, p, e = require_project()
    if e: return e
    cm = CanonManager(p)
    if cm.is_locked():
        return err("Canon is LOCKED. Unlock first.")

    data    = request.json or {}
    heading = data.get("heading", "").strip()
    content = data.get("content", "")

    if not heading:
        return err("Section heading required")

    canon_text, error = cm.read()
    if error: return err(error)

    new_canon, updated = _replace_section(canon_text, heading, content)
    if not updated:
        return err(f"Section '## {heading}' not found in canon")

    pm = ProposalManager(p)
    prop_id, _ = pm.create(
        "Manual-User", "canon-section-edit", cm.canon_path,
        new_canon, f"Section edit: ## {heading}"
    )
    ok_r, msg = pm.approve(prop_id)
    if ok_r:
        VersionTracker(p).commit(pm.get(prop_id))
        return ok(prop_id=prop_id)
    return err(msg)


@app.route("/api/agents/run-on-section", methods=["POST"])
def run_agent_on_section():
    """
    Run an agent scoped to a single canon section.
    The agent is instructed to output ONLY the new body for that section.
    Result is saved as a section-edit proposal (not a full-file overwrite).

    Body: {agent, heading, task}
    Returns: {proposal_id, usage, heading}
    """
    c, p, e = require_project()
    if e: return e
    if not c.api_key: return err("No API key configured")

    data       = request.json or {}
    agent_type = data.get("agent", "writer").lower()
    heading    = data.get("heading", "").strip()
    task       = data.get("task",    "").strip()

    if agent_type not in AGENT_REGISTRY: return err(f"Unknown agent: {agent_type}")
    if not heading: return err("heading required")
    if not task:    return err("task required")

    cm = CanonManager(p)
    canon_text, error = cm.read()
    if error: return err(error)

    if cm.is_locked():
        return err("Canon is LOCKED. Unlock first.")

    section_body = _extract_section(canon_text, heading)
    if section_body is None:
        return err(f"Section '## {heading}' not found in canon")

    # Build a scoped task — agent must output ONLY the section body
    scoped_task = (
        f"{task}\n\n"
        f"━━ SCOPE CONSTRAINT ━━\n"
        f"You are working ONLY on the '## {heading}' section of this document.\n"
        f"Output ONLY the new body text for this section.\n"
        f"Do NOT include the '## {heading}' heading in your output.\n"
        f"Do NOT output any other sections, headings, or content outside this scope.\n"
        f"The rest of the canon must remain untouched."
    )

    context = {
        "section_content": section_body,
        "section_heading": heading,
    }

    try:
        client = OpenAIClient(c.api_key, c.model)
        agent  = AGENT_REGISTRY[agent_type](client, p, c)
        new_body, usage = agent.run(scoped_task, context, temperature=0.72, max_tokens=2500)

        # Save as section-only proposal
        new_canon, updated = _replace_section(canon_text, heading, new_body.strip())
        if not updated:
            return err(f"Section replacement failed for '## {heading}'")

        pm = ProposalManager(p)
        prop_id, _ = pm.create(
            agent.name,
            "canon-section-agent",
            cm.canon_path,
            new_canon,
            f"{agent_type.upper()} agent on section: ## {heading}\nTask: {task}",
        )
        c.add_tokens(usage.get("prompt_tokens", 0),
                     usage.get("completion_tokens", 0),
                     usage.get("cost", 0.0))
        return ok(proposal_id=prop_id, usage=usage, heading=heading)

    except Exception as ex:
        return err(str(ex))


@app.route("/api/canon/sync-from-kb", methods=["POST"])
def canon_sync_from_kb():
    """
    Review all KB documents against the current canon and propose additions/updates.
    Any new characters, locations, events, world rules, etc. found in the KB but
    missing or outdated in canon are surfaced as a single reviewable proposal.

    Body: {} (no input needed — reads KB and canon automatically)
    Returns: {proposal_id, sections_updated, sections_created, usage}
    """
    c, p, e = require_project()
    if e: return e
    if not c.api_key: return err("No API key configured")

    cm = CanonManager(p)
    canon_text, error = cm.read()
    if error: return err(error)
    if cm.is_locked():
        return err("Canon is LOCKED. Unlock first.")

    # Load all KB documents
    dm = DocumentsManager(p)
    kb_parts = []
    for doc in dm.list_all():
        full = dm.get(doc["doc_type"], doc["slug"])
        if not full or not full.get("content"):
            continue
        type_label = DOC_TYPES.get(doc["doc_type"], {}).get("label", doc["doc_type"])
        snippet = full["content"][:1000].replace("\r", "")
        kb_parts.append(f"### {doc.get('title', doc['slug'])} ({type_label})\n{snippet}")

    if not kb_parts:
        return err("No KB documents found. Add characters, locations, or world documents first.")

    kb_context = "\n\n---\n\n".join(kb_parts)

    sections = DocumentsManager.parse_canon_sections(canon_text)
    sections_summary = "\n\n".join(
        f"## {s['heading']}\n{s['content'][:500]}" for s in sections
    )

    prompt = f"""\
You are synchronising a storyworld canon document with its knowledge base.

KNOWLEDGE BASE (characters, locations, world documents, etc.):
{kb_context}

CURRENT CANON SECTIONS:
{sections_summary}

Your job:
1. For each existing canon section, check if the KB contains information that should be reflected there but isn't.
   Update the section content to incorporate new characters, locations, events, and world details from the KB.
2. Identify any important topics in the KB that are entirely missing from the canon and should become new sections.

Return ONLY valid JSON — no explanation, no markdown fences:
{{
  "updates": [
    {{
      "heading": "exact heading from existing sections",
      "content": "full updated section content",
      "reason": "what was added/changed from the KB"
    }}
  ],
  "new_sections": [
    {{
      "heading": "New Section Heading",
      "content": "full section content",
      "reason": "what KB content this captures"
    }}
  ]
}}

Rules:
- Only update sections where the KB genuinely adds new information.
- Don't rewrite sections that already reflect the KB accurately.
- Preserve existing canon voice and style.
- If nothing needs updating in a section, omit it from the updates array.
"""

    client = OpenAIClient(c.api_key, c.model)
    raw, usage = client.complete(
        [{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=4000,
    )

    clean = raw.strip()
    if clean.startswith("```"):
        lines = clean.split("\n")
        clean = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

    try:
        mapped = json.loads(clean)
    except json.JSONDecodeError as ex:
        return err(f"Could not parse response: {ex}\n\nRaw: {raw[:300]}")

    updates      = mapped.get("updates", [])
    new_sections = mapped.get("new_sections", [])

    if not updates and not new_sections:
        return ok(proposal_id=None, message="Canon is already up to date with the knowledge base.")

    working_canon   = canon_text
    applied_updates = []
    applied_new     = []

    for upd in updates:
        heading = upd.get("heading", "").strip()
        content = upd.get("content", "").strip()
        reason  = upd.get("reason", "")
        if not heading or not content:
            continue
        new_c, ok_flag = _replace_section(working_canon, heading, content)
        if ok_flag:
            working_canon = new_c
            applied_updates.append({"heading": heading, "reason": reason})

    for ns in new_sections:
        heading = ns.get("heading", "").strip()
        content = ns.get("content", "").strip()
        reason  = ns.get("reason", "")
        if not heading or not content:
            continue
        working_canon = working_canon.rstrip() + f"\n\n## {heading}\n\n{content}\n"
        applied_new.append({"heading": heading, "reason": reason})

    if not applied_updates and not applied_new:
        return ok(proposal_id=None, message="Canon is already up to date with the knowledge base.")

    rationale_lines = ["KB SYNC — Canon updated from knowledge base\n"]
    for u in applied_updates:
        rationale_lines.append(f"UPDATED ## {u['heading']}: {u['reason']}")
    for n in applied_new:
        rationale_lines.append(f"CREATED ## {n['heading']}: {n['reason']}")

    pm = ProposalManager(p)
    prop_id, _ = pm.create(
        "KBSync", "canon-kb-sync",
        cm.canon_path, working_canon,
        "\n".join(rationale_lines),
    )

    c.add_tokens(usage.get("prompt_tokens", 0),
                 usage.get("completion_tokens", 0),
                 usage.get("cost", 0.0))

    return ok(
        proposal_id=prop_id,
        sections_updated=applied_updates,
        sections_created=applied_new,
        usage=usage,
    )


@app.route("/api/bible/sync-from-kb", methods=["POST"])
def bible_sync_from_kb():
    """
    Update a bible document to reflect the latest KB content.
    Body: {slug}
    Returns: {proposal_id, usage}
    """
    c, p, e = require_project()
    if e: return e
    if not c.api_key: return err("No API key configured")

    data = request.json or {}
    slug = data.get("slug", "").strip()
    if not slug:
        return err("slug required")

    dm = DocumentsManager(p)
    doc = dm.get("bible", slug)
    if not doc:
        return err(f"Bible document '{slug}' not found")

    current_content = doc.get("content", "")

    # Load KB
    kb_parts = []
    for kb_doc in dm.list_all():
        full = dm.get(kb_doc["doc_type"], kb_doc["slug"])
        if not full or not full.get("content") or kb_doc["doc_type"] == "bible":
            continue
        type_label = DOC_TYPES.get(kb_doc["doc_type"], {}).get("label", kb_doc["doc_type"])
        snippet = full["content"][:800].replace("\r", "")
        kb_parts.append(f"### {kb_doc.get('title', kb_doc['slug'])} ({type_label})\n{snippet}")

    if not kb_parts:
        return err("No KB documents to sync from.")

    kb_context = "\n\n---\n\n".join(kb_parts)

    prompt = f"""\
You are updating a Story Bible document to reflect the latest knowledge base content.

KNOWLEDGE BASE (characters, locations, world documents):
{kb_context}

CURRENT STORY BIBLE:
{current_content[:3000]}

Review the bible and update it to:
1. Reflect any new characters, locations, events, or world details from the KB that aren't yet in the bible
2. Correct any information in the bible that now conflicts with the KB
3. Expand sections that are incomplete relative to what the KB now contains

Output ONLY the full updated bible content — no explanation, no preamble.
Preserve the existing structure and headings. Maintain the same voice and style.
"""

    client = OpenAIClient(c.api_key, c.model)
    raw, usage = client.complete(
        [{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=4000,
    )

    # Save as a doc-revision proposal
    pm = ProposalManager(p)
    doc_path = os.path.join(p, "Documents", "Bible", f"{slug}.md")
    prop_id, _ = pm.create(
        "KBSync", "doc-revision-bible",
        doc_path, raw.strip(),
        f"Story Bible updated from knowledge base: {slug}",
    )

    c.add_tokens(usage.get("prompt_tokens", 0),
                 usage.get("completion_tokens", 0),
                 usage.get("cost", 0.0))

    return ok(proposal_id=prop_id, usage=usage)


@app.route("/api/agents/room-to-canon", methods=["POST"])
def room_to_canon():
    """
    Apply Agent Room synthesis to the full canon.
    Uses an LLM pass to map the synthesis onto every relevant existing section
    and to identify new sections that should be created.

    Body: {synthesis, task}
    Returns: {proposal_id, sections_updated: [...], sections_created: [...], usage}
    """
    c, p, e = require_project()
    if e: return e
    if not c.api_key: return err("No API key configured")

    data      = request.json or {}
    synthesis = data.get("synthesis", "").strip()
    task      = data.get("task",      "").strip()

    if not synthesis:
        return err("No synthesis content to apply")

    cm = CanonManager(p)
    canon_text, error = cm.read()
    if error: return err(error)
    if cm.is_locked():
        return err("Canon is LOCKED. Unlock first.")

    sections = DocumentsManager.parse_canon_sections(canon_text)
    sections_summary = "\n\n".join(
        f"## {s['heading']}\n{s['content'][:400]}" for s in sections
    )

    mapping_prompt = f"""\
You are applying a creative development team's session output to a storyworld canon document.

TEAM TASK: {task or '(no specific task recorded)'}

TEAM SYNTHESIS / OUTPUT:
{synthesis[:3000]}

EXISTING CANON SECTIONS:
{sections_summary}

Your job:
1. For each existing section that the team's output substantively addresses, provide updated content.
2. Identify any important new sections the synthesis establishes that are MISSING from the canon.

Return ONLY valid JSON in this exact structure — no explanation, no markdown fences:
{{
  "updates": [
    {{
      "heading": "exact heading name from existing sections above",
      "content": "full new content for this section (no heading line)",
      "reason": "one sentence: what changed and why"
    }}
  ],
  "new_sections": [
    {{
      "heading": "New Section Heading",
      "content": "full content for the new section",
      "reason": "one sentence: why this section should exist"
    }}
  ]
}}

Rules:
- ONLY update sections the synthesis clearly addresses with new or contradictory information.
- Do NOT invent updates — omit sections the synthesis doesn't touch.
- For new sections, only create them if the synthesis provides substantial content (not just a mention).
- Use the EXACT heading names from the existing sections list for updates.
- Preserve the storyworld's voice, tone, and style.
- Keep updated content at similar length/depth to the originals unless the synthesis expands them significantly.
"""

    client = OpenAIClient(c.api_key, c.model)
    raw, usage = client.complete(
        [{"role": "user", "content": mapping_prompt}],
        temperature=0.3,
        max_tokens=4000,
    )

    clean = raw.strip()
    if clean.startswith("```"):
        lines = clean.split("\n")
        clean = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

    try:
        mapped = json.loads(clean)
    except json.JSONDecodeError as ex:
        return err(f"Could not parse mapping response: {ex}\n\nRaw: {raw[:300]}")

    updates      = mapped.get("updates", [])
    new_sections = mapped.get("new_sections", [])

    # Apply all changes sequentially to build final canon state
    working_canon    = canon_text
    applied_updates  = []
    applied_new      = []

    for upd in updates:
        heading = upd.get("heading", "").strip()
        content = upd.get("content", "").strip()
        reason  = upd.get("reason",  "")
        if not heading or not content:
            continue
        new_c, ok_flag = _replace_section(working_canon, heading, content)
        if ok_flag:
            working_canon = new_c
            applied_updates.append({"heading": heading, "reason": reason})

    for ns in new_sections:
        heading = ns.get("heading", "").strip()
        content = ns.get("content", "").strip()
        reason  = ns.get("reason",  "")
        if not heading or not content:
            continue
        working_canon = working_canon.rstrip() + f"\n\n## {heading}\n\n{content}\n"
        applied_new.append({"heading": heading, "reason": reason})

    if not applied_updates and not applied_new:
        return err("No applicable updates or new sections identified from the session output.")

    # Build rationale summary
    rationale_lines = [f"Agent Room — APPLY TO CANON\nTask: {task or '—'}\n"]
    for u in applied_updates:
        rationale_lines.append(f"UPDATED ## {u['heading']}: {u['reason']}")
    for n in applied_new:
        rationale_lines.append(f"CREATED ## {n['heading']}: {n['reason']}")

    pm = ProposalManager(p)
    prop_id, _ = pm.create(
        "AgentRoom",
        "canon-room-multi",
        cm.canon_path,
        working_canon,
        "\n".join(rationale_lines),
    )

    c.add_tokens(usage.get("prompt_tokens", 0),
                 usage.get("completion_tokens", 0),
                 usage.get("cost", 0.0))

    return ok(
        proposal_id=prop_id,
        sections_updated=applied_updates,
        sections_created=applied_new,
        usage=usage,
    )


@app.route("/api/agents/impact-check", methods=["POST"])
def impact_check():
    """
    After a section changes, analyse which other sections may need updating.

    Body: {heading, old_content, new_content}
    Returns: {impacts: [{section, reason, urgency: 'high'|'medium'|'low'}]}
    """
    c, p, e = require_project()
    if e: return e
    if not c.api_key: return err("No API key configured")

    data        = request.json or {}
    heading     = data.get("heading", "").strip()
    old_content = data.get("old_content", "")
    new_content = data.get("new_content", "")

    if not heading: return err("heading required")

    cm = CanonManager(p)
    canon_text, error = cm.read()
    if error: return err(error)

    # Build the analysis prompt
    prompt = (
        f"You are a story analyst. A section of a story bible was just updated.\n\n"
        f"## CHANGED SECTION: {heading}\n\n"
        f"### OLD CONTENT:\n{old_content or '(empty)'}\n\n"
        f"### NEW CONTENT:\n{new_content}\n\n"
        f"## FULL CANON (for context):\n{canon_text}\n\n"
        f"## YOUR TASK\n"
        f"Identify which OTHER sections in this canon may need updating because of this change.\n"
        f"Return ONLY valid JSON — no explanation, no markdown fences:\n"
        f'{{"impacts": ['
        f'{{"section": "Section Heading", "reason": "Specific reason this section needs review", "urgency": "high|medium|low"}},'
        f'...'
        f']}}\n\n'
        f"Rules:\n"
        f"- Only list sections that genuinely need review — be selective.\n"
        f"- urgency 'high' = direct contradiction or dependency; 'medium' = consistency check; 'low' = minor touch.\n"
        f"- Do NOT include '## {heading}' itself.\n"
        f"- If no other sections need updating, return {{\"impacts\": []}}"
    )

    try:
        client = OpenAIClient(c.api_key, c.model)
        raw, usage = client.complete(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1000,
        )

        clean = raw.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

        result = json.loads(clean)
        c.add_tokens(usage.get("prompt_tokens", 0),
                     usage.get("completion_tokens", 0),
                     usage.get("cost", 0.0))
        return ok(impacts=result.get("impacts", []), usage=usage)

    except json.JSONDecodeError:
        return ok(impacts=[], usage={})
    except Exception as ex:
        return err(str(ex))


# ─── Knowledge Base Sync ─────────────────────────────────────────────────────

@app.route("/api/knowledge/mentions")
def knowledge_find_mentions():
    """
    Find all documents that mention a given entity name.
    Query params: name, exclude_type, exclude_slug
    Returns: {mentions: [{doc_type, slug, title, excerpt, type_label}]}
    """
    c, p, e = require_project()
    if e: return e

    name         = request.args.get("name", "").strip()
    exclude_type = request.args.get("exclude_type", "")
    exclude_slug = request.args.get("exclude_slug", "")

    if not name:
        return ok(mentions=[])

    dm       = DocumentsManager(p)
    all_docs = dm.list_all()
    mentions = []

    for doc in all_docs:
        if doc.get("doc_type") == exclude_type and doc.get("slug") == exclude_slug:
            continue
        full = dm.get(doc["doc_type"], doc["slug"])
        if not full:
            continue
        content = full.get("content") or ""
        idx = content.lower().find(name.lower())
        if idx == -1:
            continue
        start   = max(0, idx - 100)
        end     = min(len(content), idx + 150)
        excerpt = ("…" if start > 0 else "") + content[start:end].strip() + ("…" if end < len(content) else "")
        mentions.append({
            "doc_type":   doc["doc_type"],
            "slug":       doc["slug"],
            "title":      doc.get("title", doc["slug"]),
            "excerpt":    excerpt,
            "type_label": DOC_TYPES.get(doc["doc_type"], {}).get("label", doc["doc_type"]),
        })

    return ok(mentions=mentions, name=name)


@app.route("/api/knowledge/impact-check-doc", methods=["POST"])
def knowledge_impact_check_doc():
    """
    After a roster document changes, identify which other documents or canon
    sections may need updating.
    Body: {doc_type, slug, title, old_content, new_content}
    Returns: {impacts: [{target_type, doc_type?, slug?, title, section?, reason, urgency}]}
    """
    c, p, e = require_project()
    if e: return e
    if not c.api_key: return err("No API key configured")

    data        = request.json or {}
    doc_type    = data.get("doc_type", "")
    title       = data.get("title", doc_type)
    old_content = data.get("old_content", "")
    new_content = data.get("new_content", "")

    if not new_content:
        return ok(impacts=[])

    # Build KB summary
    dm      = DocumentsManager(p)
    kb_docs = dm.list_all()
    kb_lines = []
    for doc in kb_docs:
        if doc.get("doc_type") == doc_type and doc.get("slug") == data.get("slug", ""):
            continue  # skip source doc
        full = dm.get(doc["doc_type"], doc["slug"])
        snippet = (full.get("content") or "")[:300].replace("\n", " ") if full else ""
        kb_lines.append(f'[{doc.get("title","?")}] ({doc["doc_type"]}) — {snippet}')

    kb_block = "\n".join(kb_lines[:30]) if kb_lines else "(none)"

    # Canon sections
    cm         = CanonManager(p)
    canon_text, _ = cm.read()
    canon_block = canon_text[:3000] if canon_text else "(none)"

    prompt = (
        f"A knowledge base document was updated.\n\n"
        f"CHANGED: \"{title}\" ({doc_type})\n\n"
        f"OLD CONTENT (truncated):\n{old_content[:800] or '(new document)'}\n\n"
        f"NEW CONTENT (truncated):\n{new_content[:800]}\n\n"
        f"ALL OTHER KB DOCUMENTS:\n{kb_block}\n\n"
        f"CANON SECTIONS:\n{canon_block}\n\n"
        f"Which other documents or canon sections need updating because of this change?\n"
        f"Return ONLY valid JSON — no explanation, no markdown fences:\n"
        f'{{"impacts": ['
        f'{{"target_type": "doc", "doc_type": "character", "slug": "ana", "title": "Ana", "reason": "...", "urgency": "high|medium|low"}},'
        f'{{"target_type": "section", "section": "Characters", "title": "Characters", "reason": "...", "urgency": "medium"}}'
        f']}}\n\n'
        f"Rules:\n"
        f"- Only list items that genuinely need review.\n"
        f"- urgency 'high' = direct contradiction; 'medium' = consistency check; 'low' = minor.\n"
        f"- Do NOT include the source document itself.\n"
        f"- If nothing needs updating return {{\"impacts\": []}}"
    )

    try:
        client     = OpenAIClient(c.api_key, c.model)
        raw, usage = client.complete(
            [{"role": "user", "content": prompt}],
            temperature=0.1, max_tokens=1000,
        )
        clean = raw.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

        result = json.loads(clean)
        c.add_tokens(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), usage.get("cost", 0.0))
        return ok(impacts=result.get("impacts", []), usage=usage)

    except json.JSONDecodeError:
        return ok(impacts=[], usage={})
    except Exception as ex:
        return err(str(ex))


# ─── Documents ───────────────────────────────────────────────────────────────

@app.route("/api/documents")
def list_documents():
    c, p, e = require_project()
    if e: return ok(documents=[], doc_types=[])
    dm  = DocumentsManager(p)
    typ = request.args.get("type")
    docs = dm.list_by_type(typ) if typ else dm.list_all()
    return ok(documents=docs, doc_types=[
        {"id": k, "label": v["label"], "icon": v["icon"]}
        for k, v in DOC_TYPES.items()
    ])


@app.route("/api/documents/<doc_type>/<slug>")
def get_document(doc_type, slug):
    c, p, e = require_project()
    if e: return e
    dm  = DocumentsManager(p)
    doc = dm.get(doc_type, slug)
    if not doc: return err("Document not found")
    return ok(**doc)


@app.route("/api/documents/save", methods=["POST"])
def save_document():
    c, p, e = require_project()
    if e: return e
    data     = request.json or {}
    doc_type = data.get("doc_type", "").strip()
    title    = data.get("title", "").strip()
    content  = data.get("content", "")
    if not doc_type or not title:
        return err("doc_type and title required")
    try:
        dm   = DocumentsManager(p)
        meta = dm.save(doc_type, title, content)
        return ok(meta=meta)
    except ValueError as ex:
        return err(str(ex))


@app.route("/api/documents/<doc_type>/<slug>/delete", methods=["POST"])
def delete_document(doc_type, slug):
    c, p, e = require_project()
    if e: return e
    dm      = DocumentsManager(p)
    removed = dm.delete(doc_type, slug)
    return ok(removed=removed)


# ─── Agent document generation ───────────────────────────────────────────────

@app.route("/api/agents/generate-doc", methods=["POST"])
def generate_document():
    """
    Run a single agent (non-streaming) and save the result as a document.
    Body: {agent, task, doc_type, title, context}
    """
    c, p, e = require_project()
    if e: return e
    if not c.api_key: return err("No API key configured")

    data       = request.json or {}
    agent_type = data.get("agent", "treatment").lower()
    task       = data.get("task", "").strip()
    doc_type   = data.get("doc_type", agent_type)
    title      = data.get("title", "").strip()
    context    = data.get("context", {})

    if agent_type not in AGENT_REGISTRY: return err(f"Unknown agent: {agent_type}")
    if not task:  return err("Task required")
    if not title: return err("Title required")

    try:
        client = OpenAIClient(c.api_key, c.model)
        agent  = AGENT_REGISTRY[agent_type](client, p, c)
        context["document_type"] = doc_type
        content, usage = agent.run(task, context, temperature=0.75, max_tokens=3000)

        dm   = DocumentsManager(p)
        meta = dm.save(doc_type, title, content)

        c.add_tokens(usage.get("prompt_tokens", 0),
                     usage.get("completion_tokens", 0),
                     usage.get("cost", 0.0))
        return ok(meta=meta, usage=usage, content=content)
    except Exception as ex:
        return err(str(ex))


@app.route("/api/agents/generate-doc-set", methods=["POST"])
def generate_document_set():
    """
    Generate a set of multiple documents in one agent call.
    Body: {agent, task, doc_type, label, instructions}
    Returns: {created: [{slug, title}], count, usage}
    """
    c, p, e = require_project()
    if e: return e
    if not c.api_key: return err("No API key configured")

    data         = request.json or {}
    agent_type   = data.get("agent", "writer").lower()
    doc_type     = data.get("doc_type", "character")
    label        = data.get("label", doc_type.title() + "s")
    instructions = data.get("instructions", "").strip()

    if agent_type not in AGENT_REGISTRY: return err(f"Unknown agent: {agent_type}")
    if not instructions: return err("Instructions required")

    # Build context from canon + existing KB documents
    cm         = CanonManager(p)
    canon_text, _ = cm.read()
    dm         = DocumentsManager(p)
    existing   = dm.list_by_type(doc_type)
    exist_names = [d.get("title", "") for d in existing]

    type_label = DOC_TYPES.get(doc_type, {}).get("label", label)

    set_task = (
        f"Generate a set of {type_label} for this storyworld.\n\n"
        f"INSTRUCTIONS: {instructions}\n\n"
        f"EXISTING {type_label.upper()} (do not duplicate): {', '.join(exist_names) or 'none yet'}\n\n"
        f"Return your response as a JSON array ONLY — no explanation, no markdown fences:\n"
        f'[{{"title": "Name", "content": "Full document content in markdown"}}, ...]\n\n'
        f"Each item must have a distinct title and fully developed content."
    )

    try:
        client  = OpenAIClient(c.api_key, c.model)
        agent   = AGENT_REGISTRY[agent_type](client, p, c)
        context = {"document_type": doc_type, "canon": canon_text[:3000]}
        raw, usage = agent.run(set_task, context, temperature=0.80, max_tokens=5000)

        # Parse JSON array
        clean = raw.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

        items   = json.loads(clean)
        created = []
        for item in items:
            title   = str(item.get("title", "")).strip()
            content = str(item.get("content", "")).strip()
            if title and content:
                meta = dm.save(doc_type, title, content)
                created.append({"slug": meta["slug"], "title": title})

        c.add_tokens(usage.get("prompt_tokens", 0),
                     usage.get("completion_tokens", 0),
                     usage.get("cost", 0.0))
        return ok(created=created, count=len(created), usage=usage)

    except json.JSONDecodeError as ex:
        return err(f"Agent returned malformed JSON: {ex}")
    except Exception as ex:
        return err(str(ex))


# ─── Canon Knowledge Graph ───────────────────────────────────────────────────

@app.route("/api/canon/graph")
def get_canon_graph():
    """
    Extract and return the knowledge graph for the current project.
    Sources: Canon.md + all KB documents (characters, locations, bible, etc.)
    Cache in Canon/graph.json — invalidated when canon OR any document changes.
    Pass ?refresh=1 to force re-extraction.
    """
    c, p, e = require_project()
    if e: return e
    if not c.api_key: return err("No API key configured")

    cm = CanonManager(p)
    canon_text, error = cm.read()
    if error: return err(error)

    # Build extra context from all KB documents
    dm       = DocumentsManager(p)
    kb_parts = []
    for doc in dm.list_all():
        full = dm.get(doc["doc_type"], doc["slug"])
        if not full or not full.get("content"):
            continue
        type_label = DOC_TYPES.get(doc["doc_type"], {}).get("label", doc["doc_type"])
        snippet    = full["content"][:800].replace("\r", "")
        kb_parts.append(f"### {doc.get('title', doc['slug'])} ({type_label})\n{snippet}")
    extra_context = "\n\n".join(kb_parts)

    cache_path = os.path.join(p, "Canon", "graph.json")
    force      = request.args.get("refresh", "0") == "1"

    if force and os.path.exists(cache_path):
        os.remove(cache_path)

    try:
        client    = OpenAIClient(c.api_key, c.model)
        extractor = CanonGraphExtractor(client)
        result    = extractor.extract(
            canon_text,
            cache_path=cache_path,
            extra_context=extra_context,
        )

        if not result.get("cached"):
            usage = result.get("usage", {})
            c.add_tokens(
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
                usage.get("cost", 0.0),
            )

        return ok(
            nodes=result["nodes"],
            edges=result["edges"],
            cached=result.get("cached", False),
            extracted_at=result.get("extracted_at", ""),
        )
    except Exception as ex:
        return err(str(ex))


# ─── Proposal from text (Agent Room → Canon) ─────────────────────────────────

@app.route("/api/proposals/from-text", methods=["POST"])
def proposal_from_text():
    """
    Create a canon-section proposal directly from text (e.g. Agent Room synthesis).
    Body: {heading, text, agent}
    Returns: {proposal_id}
    """
    c, p, e = require_project()
    if e: return e

    data    = request.json or {}
    heading = data.get("heading", "").strip()
    text    = data.get("text",    "").strip()
    agent   = data.get("agent",   "AgentRoom")

    if not heading: return err("heading required")
    if not text:    return err("text required")

    cm = CanonManager(p)
    canon_text, error = cm.read()
    if error: return err(error)
    if cm.is_locked():
        return err("Canon is LOCKED. Unlock first.")

    new_canon, updated = _replace_section(canon_text, heading, text)
    if not updated:
        return err(f"Section '## {heading}' not found in canon")

    pm = ProposalManager(p)
    prop_id, _ = pm.create(
        agent, "canon-section-from-room",
        cm.canon_path, new_canon,
        f"Agent Room synthesis for section: ## {heading}",
    )
    return ok(proposal_id=prop_id)


# ─── Proposal section-diff ───────────────────────────────────────────────────

@app.route("/api/proposals/<prop_id>/section-diff")
def proposal_section_diff(prop_id):
    """
    For a canon-section-agent proposal, return the before/after content for
    just the targeted section (extracted from the stored full-file snapshots).

    Returns: {heading, old_section, new_section, agent, status}
    """
    import re as _re
    c, p, e = require_project()
    if e: return e
    pm   = ProposalManager(p)
    data = pm.get(prop_id)
    if not data: return err("Proposal not found")

    rationale = data.get("rationale", "")
    m = _re.search(r"##\s+(.+?)(?:\n|$)", rationale)
    heading = m.group(1).strip() if m else None

    old_c = data.get("current_content", "")
    new_c = data.get("new_content",     "")

    if heading:
        old_section = _extract_section(old_c, heading)
        new_section = _extract_section(new_c, heading)
    else:
        old_section = old_c[:3000]
        new_section = new_c[:3000]

    return ok(
        heading=heading,
        old_section=old_section,
        new_section=new_section,
        agent=data.get("agent", ""),
        status=data.get("status", ""),
    )


# ─── Document revision (agent → proposal) ────────────────────────────────────

@app.route("/api/documents/<doc_type>/<slug>/revise", methods=["POST"])
def revise_document(doc_type, slug):
    """
    Run an agent on an existing document and create a PROPOSAL for review.
    Body: {agent, task}
    Returns: {proposal_id, usage}
    """
    c, p, e = require_project()
    if e: return e
    if not c.api_key: return err("No API key configured")

    data       = request.json or {}
    agent_type = data.get("agent", "writer").lower()
    task       = data.get("task", "").strip()

    if agent_type not in AGENT_REGISTRY: return err(f"Unknown agent: {agent_type}")
    if not task: return err("Task required")

    dm  = DocumentsManager(p)
    doc = dm.get(doc_type, slug)
    if not doc: return err(f"Document not found: {doc_type}/{slug}")

    target_file = doc["meta"]["path"]
    try:
        prop_id, usage = _run_agent(
            agent_type, task, target_file, p, c,
            context={"current_content": doc["content"], "document_type": doc_type},
            proposal_type=f"doc-revision-{doc_type}",
        )
        return ok(proposal_id=prop_id, usage=usage)
    except Exception as ex:
        return err(str(ex))


# ─── Images ──────────────────────────────────────────────────────────────────

_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'}


def _images_dir(project_path: str, doc_type: str) -> str:
    return os.path.join(project_path, "Images", doc_type)


def _find_image(project_path: str, doc_type: str, slug: str) -> str | None:
    """Return path to existing image file for slug, or None."""
    folder = _images_dir(project_path, doc_type)
    if not os.path.isdir(folder):
        return None
    for fname in os.listdir(folder):
        name, ext = os.path.splitext(fname)
        if name == slug and ext.lower() in _IMAGE_EXTS:
            return os.path.join(folder, fname)
    return None


@app.route("/api/images/<doc_type>/<slug>")
def get_image(doc_type, slug):
    c, p, e = require_project()
    if e: return err("No active project", 404)
    path = _find_image(p, doc_type, slug)
    if not path: return err("Image not found", 404)
    return send_file(path)


@app.route("/api/images/upload", methods=["POST"])
def upload_image():
    c, p, e = require_project()
    if e: return e

    doc_type = request.form.get("doc_type", "").strip()
    slug     = request.form.get("slug", "").strip()
    if not doc_type or not slug:
        return err("doc_type and slug required")

    if "file" not in request.files:
        return err("No file uploaded")

    f = request.files["file"]
    if not f.filename:
        return err("Empty filename")

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in _IMAGE_EXTS:
        return err(f"Unsupported image type: {ext}")

    folder = _images_dir(p, doc_type)
    os.makedirs(folder, exist_ok=True)

    # Remove any existing image for this slug
    existing = _find_image(p, doc_type, slug)
    if existing:
        os.remove(existing)

    dest = os.path.join(folder, f"{slug}{ext}")
    f.save(dest)
    return ok(path=dest, url=f"/api/images/{doc_type}/{slug}")


# ─── Memory rollback ──────────────────────────────────────────────────────────

@app.route("/api/memory/rollback", methods=["POST"])
def rollback_memory():
    """
    Restore working memory to the state it was in BEFORE a given proposal was applied.
    Body: {proposal_id: "prop_..."}
    """
    c, p, e = require_project()
    if e: return e

    prop_id = (request.json or {}).get("proposal_id", "").strip()
    if not prop_id: return err("proposal_id required")

    pm   = ProposalManager(p)
    data = pm.get(prop_id)
    if not data: return err("Proposal not found")

    old_content = data.get("current_content", "")
    mm = MemoryManager(p)

    new_prop_id, _ = pm.create(
        "Manual-Rollback", "memory-rollback", mm.working_path,
        old_content,
        f"Rollback to state before proposal {prop_id}",
    )
    ok_r, msg = pm.approve(new_prop_id)
    if ok_r:
        VersionTracker(p).commit(pm.get(new_prop_id))
        return ok(msg=f"Memory rolled back to pre-{prop_id} state", new_proposal_id=new_prop_id)
    return err(msg)


# ─── Agent list ──────────────────────────────────────────────────────────────

@app.route("/api/agents")
def list_agents():
    agents = []
    for key, cls in AGENT_REGISTRY.items():
        obj = cls.__new__(cls)
        agents.append({
            "key":   key,
            "name":  getattr(obj, "name", key),
            "label": getattr(obj, "role_label", key.upper()),
        })
    return ok(agents=agents)


# ─── Agent Team (profiles + role editing) ────────────────────────────────────

from src.agent import get_role_override, save_role_override


@app.route("/api/agents/profiles")
def get_agent_profiles():
    profiles = []
    for key, cls in AGENT_REGISTRY.items():
        obj = cls.__new__(cls)
        name         = getattr(obj, "name", key)
        default_role = getattr(obj, "role", "")
        override     = get_role_override(name)
        profiles.append({
            "key":          key,
            "name":         name,
            "role_label":   getattr(obj, "role_label", key.upper()),
            "default_role": default_role,
            "current_role": override or default_role,
            "is_overridden": bool(override),
        })
    return ok(profiles=profiles)


@app.route("/api/agents/<key>/role", methods=["POST"])
def update_agent_role(key):
    if key not in AGENT_REGISTRY:
        return err(f"Unknown agent: {key}")
    role = (request.json or {}).get("role", "").strip()
    if not role:
        return err("role required")
    cls  = AGENT_REGISTRY[key]
    obj  = cls.__new__(cls)
    name = getattr(obj, "name", key)
    save_role_override(name, role)
    return ok(msg=f"Role updated for {name}")


@app.route("/api/agents/<key>/role/reset", methods=["POST"])
def reset_agent_role(key):
    if key not in AGENT_REGISTRY:
        return err(f"Unknown agent: {key}")
    cls  = AGENT_REGISTRY[key]
    obj  = cls.__new__(cls)
    name = getattr(obj, "name", key)
    save_role_override(name, "")   # empty string = use class default
    return ok(msg=f"Role reset to default for {name}")


@app.route("/api/agents/<key>/improve-role", methods=["POST"])
def improve_agent_role(key):
    if key not in AGENT_REGISTRY:
        return err(f"Unknown agent: {key}")
    c = cfg()
    if not c.api_key:
        return err("No API key configured")

    data         = request.json or {}
    instructions = data.get("instructions", "").strip()
    cls          = AGENT_REGISTRY[key]
    obj          = cls.__new__(cls)
    name         = getattr(obj, "name", key)
    current_role = get_role_override(name) or getattr(obj, "role", "")

    prompt = (
        f'You are improving the system prompt for a creative writing AI agent called "{name}".\n'
        f"This agent works in a feature-film writers room.\n\n"
        f"CURRENT ROLE DESCRIPTION:\n{current_role}\n\n"
        f"IMPROVEMENT INSTRUCTIONS:\n"
        f"{instructions or 'Make this agent description more focused, specific, and effective. Keep the same style and approximate length.'}\n\n"
        f"Output ONLY the new role description text. No preamble, no explanation, no quotation marks."
    )

    try:
        client = OpenAIClient(c.api_key, c.model)
        new_role, usage = client.complete(
            [{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1500,
        )
        c.add_tokens(usage.get("prompt_tokens", 0),
                     usage.get("completion_tokens", 0),
                     usage.get("cost", 0.0))
        return ok(improved_role=new_role.strip(), usage=usage)
    except Exception as ex:
        return err(str(ex))


# ─── World Bible ─────────────────────────────────────────────────────────────

@app.route("/api/worldbible")
def get_worldbible():
    """Return all WorldBible sections with content + metadata."""
    c, p, e = require_project()
    if e: return e
    wbm = WorldBibleManager(p)
    return ok(sections=wbm.get_all_sections())


@app.route("/api/worldbible/<section_id>")
def get_worldbible_section(section_id):
    """Return a single WorldBible section."""
    c, p, e = require_project()
    if e: return e
    wbm = WorldBibleManager(p)
    try:
        content = wbm.get_section(section_id)
        info    = wbm.SECTIONS.get(section_id, {})
        return ok(
            section_id=section_id,
            content=content,
            label=info.get("label", section_id),
            description=info.get("description", ""),
        )
    except ValueError as ex:
        return err(str(ex))


@app.route("/api/worldbible/<section_id>", methods=["POST"])
def save_worldbible_section(section_id):
    """Directly save a WorldBible section (manual edit — no proposal required)."""
    c, p, e = require_project()
    if e: return e
    content = (request.json or {}).get("content", "")
    wbm = WorldBibleManager(p)
    try:
        meta = wbm.save_section(section_id, content)
        VersionTracker(p).commit({
            "id": f"wb_{section_id}_{meta['updated_at'][:10]}",
            "agent": "Manual-User",
            "type": f"worldbible-{section_id}-edit",
            "status": "APPROVED",
            "created": meta["updated_at"],
            "target_file": wbm.section_path(section_id),
            "tokens": {},
            "cost": 0.0,
        })
        return ok(meta=meta)
    except ValueError as ex:
        return err(str(ex))


@app.route("/api/worldbible/<section_id>/revise", methods=["POST"])
def revise_worldbible_section(section_id):
    """
    Run an agent on a WorldBible section and return a proposal.
    Body: {agent, task}
    Returns: {proposal_id, usage}
    """
    c, p, e = require_project()
    if e: return e
    if not c.api_key: return err("No API key configured")

    wbm = WorldBibleManager(p)
    if section_id not in wbm.SECTIONS:
        return err(f"Unknown section: {section_id}")

    data       = request.json or {}
    agent_type = data.get("agent", "writer").lower()
    task       = data.get("task", "").strip()

    if agent_type not in AGENT_REGISTRY: return err(f"Unknown agent: {agent_type}")
    if not task: return err("task required")

    current   = wbm.get_section(section_id)
    info      = wbm.SECTIONS[section_id]
    sec_path  = wbm.section_path(section_id)

    scoped_task = (
        f"{task}\n\n"
        f"━━ SCOPE ━━\n"
        f"You are working on the '{info['label']}' section of the Story World Bible.\n"
        f"Description: {info['description']}\n\n"
        f"Current content:\n{current or '(empty — write this section from scratch)'}\n\n"
        f"Output ONLY the complete new content for this section.\n"
        f"Write in worldbuilding style — rich, specific, cinematic.\n"
        f"Do NOT include any preamble, heading, or explanation outside the content itself.\n\n"
        f"FORMAT: Write in descriptive prose and clear analytical notes. "
        f"Do NOT use screenplay format (no INT./EXT. headings, no action lines, "
        f"no script-formatted dialogue). This is a story bible document.\n"
        f"CONTRADICTIONS: If your proposed content conflicts with any existing KB "
        f"documents (characters, locations, world rules), flag it clearly with "
        f"'⚠️ CONTRADICTION:' and explain both sides."
    )

    try:
        client = OpenAIClient(c.api_key, c.model)
        agent  = AGENT_REGISTRY[agent_type](client, p, c)
        new_content, usage = agent.run(scoped_task, {}, temperature=0.72, max_tokens=3000)

        pm = ProposalManager(p)
        prop_id, _ = pm.create(
            agent.name,
            f"worldbible-{section_id}",
            sec_path,
            new_content.strip(),
            f"{agent_type.upper()} agent on WorldBible/{info['label']}\nTask: {task}",
        )
        c.add_tokens(usage.get("prompt_tokens", 0),
                     usage.get("completion_tokens", 0),
                     usage.get("cost", 0.0))
        return ok(proposal_id=prop_id, usage=usage)
    except Exception as ex:
        return err(str(ex))


@app.route("/api/worldbible/<section_id>/propose", methods=["POST"])
def propose_worldbible_section(section_id):
    """
    Create a WorldBible proposal directly from provided content (team synthesis).
    Body: {content}
    Returns: {proposal_id}
    """
    c, p, e = require_project()
    if e: return e

    content = (request.json or {}).get("content", "").strip()
    if not content:
        return err("No content provided")

    wbm = WorldBibleManager(p)
    if section_id not in wbm.SECTIONS:
        return err(f"Unknown section: {section_id}")

    current  = wbm.get_section(section_id)
    info     = wbm.SECTIONS[section_id]
    sec_path = wbm.section_path(section_id)

    pm = ProposalManager(p)
    prop_id, _ = pm.create(
        "team",
        f"worldbible-{section_id}",
        sec_path,
        content,
        f"Team brainstorm: {info.get('label', section_id)}",
        current_content=current,
    )
    return ok(proposal_id=prop_id)


@app.route("/api/worldbible/parse-into-sections", methods=["POST"])
def worldbible_parse_into_sections():
    """
    Parse a synthesis text into individual WorldBible section content.
    Body: {synthesis}
    Returns: {sections: {overview, lore, logic, tone, structure, rules}}
    """
    c, p, e = require_project()
    if e: return e
    if not c.api_key: return err("No API key configured")

    synthesis = (request.json or {}).get("synthesis", "").strip()
    if not synthesis:
        return err("No synthesis provided")

    prompt = (
        "Extract content for each Story World Bible section from this synthesis.\n"
        "Return ONLY valid JSON — no explanation, no markdown fences:\n"
        '{"sections": {"overview": "...", "lore": "...", "logic": "...", '
        '"tone": "...", "structure": "...", "rules": "..."}}\n\n'
        "Rules:\n"
        "- If a section is not covered in the synthesis, return empty string for it.\n"
        "- Write in descriptive prose, not screenplay or script format.\n"
        "- overview: logline, premise, theme, genre, emotional core.\n"
        "- lore: world history, mythology, backstory.\n"
        "- logic: rules of the world (magic, technology, physics).\n"
        "- tone: visual language, cinematic mood, atmosphere.\n"
        "- structure: three-act breakdown, key story beats.\n"
        "- rules: non-negotiable world constraints (can be empty if not discussed).\n\n"
        f"SYNTHESIS:\n{synthesis[:6000]}"
    )

    try:
        client = OpenAIClient(c.api_key, c.model)
        raw, usage = client.complete(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=3000,
        )
        c.add_tokens(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), usage.get("cost", 0.0))
        clean = raw.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        try:
            data = json.loads(clean)
        except Exception:
            m = re.search(r"\{.*\}", clean, re.DOTALL)
            data = json.loads(m.group()) if m else {"sections": {}}
        return ok(sections=data.get("sections", {}))
    except Exception as ex:
        return err(str(ex))


@app.route("/api/worldbible/consistency-check", methods=["POST"])
def worldbible_consistency_check():
    """
    Scan all WorldBible sections + KB documents for contradictions and
    continuity errors. Returns structured list of issues with severity.
    """
    c, p, e = require_project()
    if e: return e
    if not c.api_key: return err("No API key configured")

    wbm = WorldBibleManager(p)
    dm  = DocumentsManager(p)

    # Collect WorldBible sections
    all_content = []
    for sec in wbm.get_all_sections():
        if sec["has_content"]:
            all_content.append(
                f"WORLDBIBLE/{sec['label']}:\n{sec['content'][:1500]}"
            )

    # Collect key KB documents
    for doc in dm.list_all():
        if doc.get("doc_type") not in ("character", "location", "creature", "world", "bible", "object"):
            continue
        full = dm.get(doc["doc_type"], doc["slug"])
        if full and full.get("content"):
            all_content.append(
                f"KB/{doc.get('type_label', doc['doc_type'])}/{doc['title']}:\n{full['content'][:600]}"
            )

    if not all_content:
        return ok(issues=[], message="No content to check yet.")

    combined = "\n\n---\n\n".join(all_content[:25])  # cap to avoid token limits

    client = OpenAIClient(c.api_key, c.model)
    prompt = f"""You are a storyworld consistency analyst for a feature film project.

Check ALL of the following documents for contradictions, inconsistencies, and continuity errors.

DOCUMENTS TO CHECK:
{combined}

Find ALL contradictions and inconsistencies between documents. Look for:
- Character facts that differ between documents (age, background, abilities, relationships)
- Location details that contradict each other
- Timeline or chronology conflicts
- World logic/rules that are broken or inconsistently applied
- Names or titles that are used inconsistently

Return ONLY valid JSON (no markdown fences):
{{"issues": [{{"title": "Brief title of the contradiction", "severity": "high|medium|low", "description": "What specifically contradicts what, with quotes where possible", "sources": ["Document1", "Document2"], "suggestion": "How to resolve this"}}]}}

If no issues found, return {{"issues": []}}."""

    try:
        raw, usage = client.complete(
            [{"role": "system", "content": "You are a story consistency analyst. Return only valid JSON."},
             {"role": "user",   "content": prompt}],
            temperature=0.1,
            max_tokens=2000,
        )
        c.add_tokens(usage.get("prompt_tokens", 0),
                     usage.get("completion_tokens", 0),
                     usage.get("cost", 0.0))

        clean = raw.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        try:
            data = json.loads(clean)
        except Exception:
            import re as _re
            m = _re.search(r"\{.*\}", clean, _re.DOTALL)
            data = json.loads(m.group()) if m else {"issues": []}

        return ok(issues=data.get("issues", []), usage=usage)
    except Exception as ex:
        return err(str(ex))


# ─── Entity Extraction ────────────────────────────────────────────────────────

@app.route("/api/knowledge/extract-entities", methods=["POST"])
def extract_entities():
    """
    Extract named entities (characters, locations, creatures, objects) from text.
    Checks each against existing KB documents and flags new info about existing entities.

    Body: {content}
    Returns: {entities: [{type, name, description, exists, slug?, new_facts?}]}
    """
    c, p, e = require_project()
    if e: return e
    if not c.api_key: return err("No API key configured")

    content = (request.json or {}).get("content", "").strip()
    if not content:
        return ok(entities=[])

    # Load existing entity names for context
    dm = DocumentsManager(p)
    existing = dm.list_all()
    existing_names = {
        d["title"].lower(): {"title": d["title"], "doc_type": d["doc_type"], "slug": d["slug"]}
        for d in existing
        if d.get("doc_type") in ("character", "location", "creature", "object")
    }
    existing_summary = "\n".join(
        f"- {d['title']} ({d['doc_type']})"
        for d in existing
        if d.get("doc_type") in ("character", "location", "creature", "object")
    ) or "None yet."

    client = OpenAIClient(c.api_key, c.model)
    prompt = f"""Analyze this story text and extract all named entities.

EXISTING KB ENTITIES (already have documents):
{existing_summary}

TEXT TO ANALYZE:
{content[:3000]}

Extract every named character, location, creature, and significant object.
For each entity that already EXISTS in the KB, identify any new facts mentioned
about them that aren't likely already captured (new relationships, abilities, backstory, etc.).

Return ONLY valid JSON:
{{"entities": [{{"type": "character|location|creature|object", "name": "Exact Name", "description": "one-line description", "exists": true|false, "new_facts": "any new info about this entity, or empty string if none"}}]}}

Only include real named entities — not generic descriptions like 'the forest' or 'the man'.
Limit to maximum 12 most significant entities."""

    try:
        raw, usage = client.complete(
            [{"role": "system", "content": "You are a story entity extractor. Return only valid JSON."},
             {"role": "user",   "content": prompt}],
            temperature=0.1,
            max_tokens=800,
        )
        c.add_tokens(usage.get("prompt_tokens", 0),
                     usage.get("completion_tokens", 0),
                     usage.get("cost", 0.0))

        clean = raw.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        try:
            data = json.loads(clean)
        except Exception:
            import re as _re
            m = _re.search(r"\{.*\}", clean, _re.DOTALL)
            data = json.loads(m.group()) if m else {"entities": []}

        entities = data.get("entities", [])

        # Resolve slugs for existing entities
        for ent in entities:
            name_key = ent.get("name", "").lower()
            if name_key in existing_names:
                ent["exists"] = True
                ent["slug"]   = existing_names[name_key]["slug"]
                ent["type"]   = existing_names[name_key]["doc_type"]

        return ok(entities=entities)
    except Exception as ex:
        return err(str(ex))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
