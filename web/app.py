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
from src.documents     import DocumentsManager, DOC_TYPES, ENTITY_TYPES, _slug as doc_slug
from src.graph         import CanonGraphExtractor
from src.world_bible   import WorldBibleManager
from src.snapshot      import SnapshotManager
from src.session_log   import SessionLogger

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

    # Snapshot before overwrite so approval can be undone
    if target:
        SnapshotManager.push(
            p, target,
            f"Proposal approved: {data.get('type', '')} · {data.get('agent', '')}"
        )

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


# ─── Assistant Chat (single-agent SSE streaming) ─────────────────────────────

@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    """
    Simple conversational streaming endpoint for the right-panel assistant.
    Body: {message, context, agent}
      context — the current page text (used as working memory / background)
      agent   — agent key (default: showrunner)
    """
    c, p, e = require_project()

    def _err(msg):
        def g():
            yield f"data: {json.dumps({'type': 'error', 'message': msg})}\n\n"
            yield "data: [DONE]\n\n"
        return Response(stream_with_context(g()), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    if e: return _err("No active project")
    if not c.api_key: return _err("No API key configured")

    data        = request.json or {}
    message     = (data.get("message") or "").strip()
    page_ctx    = (data.get("context") or "").strip()
    agent_key   = data.get("agent", "showrunner")

    if not message: return _err("No message provided")

    agent_cls = AGENT_REGISTRY.get(agent_key) or AGENT_REGISTRY.get("showrunner")
    client    = OpenAIClient(c.api_key, c.model)
    agent     = agent_cls(client, p, c)

    cm         = CanonManager(p)
    canon_text, _ = cm.read()
    canon_text = canon_text or ""
    wm_text    = MemoryManager(p).read_working()

    # Page content becomes the focused working context
    context = {
        "canon":          canon_text,
        "working_memory": (wm_text + "\n\n---\n\n" + page_ctx) if page_ctx else wm_text,
    }

    def generate():
        try:
            for item in agent.run_stream(message, context=context, temperature=0.7):
                if isinstance(item, dict):
                    # Final usage dict yielded by complete_stream
                    c.add_tokens(
                        item.get("prompt_tokens", 0),
                        item.get("completion_tokens", 0),
                        item.get("cost", 0.0),
                    )
                else:
                    yield f"data: {json.dumps({'type': 'token', 'text': item})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as ex:
            yield f"data: {json.dumps({'type': 'error', 'message': str(ex)})}\n\n"
        yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
        from datetime import datetime as _dt
        total_tokens = 0
        total_cost   = 0.0
        # Session record for the conversation log
        session = {
            "id":       "session_" + _dt.now().strftime("%Y%m%d_%H%M%S_%f"),
            "timestamp": _dt.now().isoformat(),
            "team":     team_id,
            "heading":  context.get("section_heading", ""),
            "task":     task,
            "turns":    [],
            "total_tokens": 0,
            "total_cost":   0.0,
        }
        current_turn = None
        try:
            for event in engine.run(task, team_id, context, rounds=rounds):
                yield f"data: {json.dumps(event)}\n\n"
                etype = event.get("type")
                if etype == "agent_start":
                    current_turn = {
                        "agent":   event.get("agent", ""),
                        "key":     event.get("key", ""),
                        "content": "",
                        "tokens":  0,
                        "cost":    0.0,
                    }
                elif etype == "chunk" and current_turn is not None:
                    current_turn["content"] += event.get("content", "")
                elif etype == "agent_done" and current_turn is not None:
                    current_turn["tokens"] = event.get("tokens", 0)
                    current_turn["cost"]   = event.get("cost", 0.0)
                    session["turns"].append(current_turn)
                    current_turn = None
                elif etype == "done":
                    total_tokens = event.get("total_tokens", 0)
                    total_cost   = event.get("total_cost", 0.0)
                    session["total_tokens"] = total_tokens
                    session["total_cost"]   = total_cost
        except Exception as ex:
            yield f"data: {json.dumps({'type': 'error', 'message': str(ex)})}\n\n"
        finally:
            if total_tokens:
                c.add_tokens(0, 0, total_cost)
            # Persist session if any turns were captured
            if session["turns"]:
                try:
                    SessionLogger.append(p, session)
                except Exception:
                    pass
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


@app.route("/api/documents/<doc_type>/<slug>/connections")
def get_entity_connections(doc_type, slug):
    """
    Return explicit (user-added) relations PLUS any graph-extracted edges
    that reference this entity — for display in the CONNECTIONS panel.
    """
    c, p, e = require_project()
    if e: return e
    dm  = DocumentsManager(p)
    doc = dm.get(doc_type, slug)
    if not doc: return err("Document not found")

    title    = (doc.get("meta") or {}).get("title", slug)
    explicit = (doc.get("meta") or {}).get("relations", [])

    # Build a set of IDs that could represent this entity in the graph.
    # Match by: doc slug, slug-of-title, AND any node whose label == title
    slug_variants = {slug, doc_slug(title)}
    title_lower   = title.lower()

    graph_edges = []
    cache_path  = os.path.join(p, "Canon", "graph.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                graph = json.load(f)
            nodes = {n["id"]: n for n in graph.get("nodes", [])}

            # Expand slug_variants with any node whose label matches the title
            for nid, node in nodes.items():
                if node.get("label", "").lower() == title_lower:
                    slug_variants.add(nid)

            for edge in graph.get("edges", []):
                src = str(edge.get("source", ""))
                tgt = str(edge.get("target", ""))
                if src in slug_variants:
                    other = nodes.get(tgt, {})
                    graph_edges.append({
                        "direction":   "outgoing",
                        "label":       edge.get("label", ""),
                        "other_id":    tgt,
                        "other_label": other.get("label", tgt),
                        "other_type":  other.get("type", ""),
                    })
                elif tgt in slug_variants:
                    other = nodes.get(src, {})
                    graph_edges.append({
                        "direction":   "incoming",
                        "label":       edge.get("label", ""),
                        "other_id":    src,
                        "other_label": other.get("label", src),
                        "other_type":  other.get("type", ""),
                    })
        except Exception:
            pass

    return ok(explicit=explicit, graph=graph_edges)


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
        dm = DocumentsManager(p)
        # Snapshot existing file before overwrite (if it exists)
        if doc_type in DOC_TYPES:
            info = DOC_TYPES[doc_type]
            tentative_path = os.path.join(p, "Documents", info["folder"], f"{doc_slug(title)}.md")
            SnapshotManager.push(p, tentative_path, f"Document save: {title}")
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


@app.route("/api/documents/<doc_type>/reorder", methods=["POST"])
def reorder_documents(doc_type):
    """Set order for multiple documents. Body: {order_map: {slug: int}}"""
    c, p, e = require_project()
    if e: return e
    data      = request.json or {}
    order_map = data.get("order_map", {})
    dm = DocumentsManager(p)
    dm.set_orders(doc_type, order_map)
    return ok(reordered=len(order_map))


@app.route("/api/documents/<doc_type>/<slug>/meta", methods=["POST"])
def update_document_meta(doc_type, slug):
    """Merge arbitrary fields into a document's meta. Body: {fields: {...}}"""
    c, p, e = require_project()
    if e: return e
    data   = request.json or {}
    fields = data.get("fields", {})
    try:
        dm   = DocumentsManager(p)
        meta = dm.update_meta(doc_type, slug, fields)
        return ok(meta=meta)
    except ValueError as ex:
        return err(str(ex))


@app.route("/api/documents/<doc_type>/<slug>/relations", methods=["POST"])
def add_relation(doc_type, slug):
    """Add a relation to an entity document. Body: {target_type, target_slug, target_title, label}"""
    c, p, e = require_project()
    if e: return e
    data     = request.json or {}
    relation = {
        "target_type":  data.get("target_type", ""),
        "target_slug":  data.get("target_slug", ""),
        "target_title": data.get("target_title", ""),
        "label":        data.get("label", "related to"),
    }
    if not relation["target_slug"]:
        return err("target_slug required")
    try:
        dm   = DocumentsManager(p)
        meta = dm.add_relation(doc_type, slug, relation)
        return ok(meta=meta)
    except ValueError as ex:
        return err(str(ex))


@app.route("/api/documents/<doc_type>/<slug>/relations/<int:idx>", methods=["DELETE"])
def remove_relation(doc_type, slug, idx):
    """Remove a relation by index from an entity document."""
    c, p, e = require_project()
    if e: return e
    try:
        dm   = DocumentsManager(p)
        meta = dm.remove_relation(doc_type, slug, idx)
        return ok(meta=meta)
    except ValueError as ex:
        return err(str(ex))


@app.route("/api/documents/<doc_type>/<slug>/relations/by-target", methods=["DELETE"])
def remove_relation_by_target(doc_type, slug):
    """Remove the first relation matching target_slug (and optionally label). Body: {target_slug, label}"""
    c, p, e = require_project()
    if e: return e
    data        = request.json or {}
    target_slug = data.get("target_slug", "")
    label       = data.get("label", "")
    try:
        dm        = DocumentsManager(p)
        meta      = dm._read_meta(doc_type, slug)
        relations = meta.get("relations", [])
        idx       = next(
            (i for i, r in enumerate(relations)
             if r.get("target_slug") == target_slug and (not label or r.get("label") == label)),
            None,
        )
        if idx is None:
            return err("Relation not found")
        relations.pop(idx)
        meta["relations"] = relations
        dm._write_meta(meta, doc_type, slug)
        return ok(meta=meta)
    except Exception as ex:
        return err(str(ex))


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
        # Long-form docs (treatments, bibles, beat sheets) need more tokens
        long_form_types = {"treatment", "synopsis", "logline", "beat_sheet", "bible"}
        max_tok = 5000 if (agent_type in {"treatment", "logline", "structure"} or doc_type in long_form_types) else 3000
        content, usage = agent.run(task, context, temperature=0.75, max_tokens=max_tok)

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

        # Merge explicit user-defined relations from entity metadata
        explicit_edges = dm.list_all_relations()
        merged_edges   = list(result["edges"])
        merged_nodes   = {n["id"]: n for n in result["nodes"]}

        # Ensure every KB entity doc appears as a node (even if the LLM missed it)
        for doc in dm.list_all():
            slug = doc.get("slug", "")
            if not slug:
                continue
            if doc.get("doc_type") not in ENTITY_TYPES:
                continue
            if slug not in merged_nodes:
                merged_nodes[slug] = {
                    "id":          slug,
                    "label":       doc.get("title", slug),
                    "type":        doc.get("doc_type", "character"),
                    "description": "",
                    "weight":      1,
                }

        for rel in explicit_edges:
            # Ensure source and target nodes exist
            for nid, ntitle, ntype in [
                (rel["source_slug"], rel["source_title"], rel["source_type"]),
                (rel["target_slug"], rel["target_title"], rel["target_type"]),
            ]:
                if nid and nid not in merged_nodes:
                    merged_nodes[nid] = {"id": nid, "label": ntitle or nid, "type": ntype}

            if rel["source_slug"] and rel["target_slug"]:
                merged_edges.append({
                    "source": rel["source_slug"],
                    "target": rel["target_slug"],
                    "label":  rel["label"],
                    "explicit": True,
                })

        # Filter excluded edges
        excl_path = os.path.join(p, "Canon", "graph_excluded.json")
        try:
            with open(excl_path, encoding="utf-8") as f:
                excluded = json.load(f)
            if excluded:
                def _is_excluded(edge):
                    s = str(edge.get("source", ""))
                    t = str(edge.get("target", ""))
                    l = edge.get("label", "")
                    return any(
                        x.get("source") == s and x.get("target") == t and
                        (not x.get("label") or x.get("label") == l)
                        for x in excluded
                    )
                merged_edges = [e for e in merged_edges if not _is_excluded(e)]
        except Exception:
            pass

        return ok(
            nodes=list(merged_nodes.values()),
            edges=merged_edges,
            cached=result.get("cached", False),
            extracted_at=result.get("extracted_at", ""),
        )
    except Exception as ex:
        return err(str(ex))


@app.route("/api/canon/graph/exclude", methods=["POST"])
def exclude_graph_edge():
    """Permanently hide an edge. Body: {source, target, label}"""
    c, p, e = require_project()
    if e: return e
    data   = request.json or {}
    source = data.get("source", "")
    target = data.get("target", "")
    label  = data.get("label",  "")
    if not source or not target:
        return err("source and target required")

    excl_path = os.path.join(p, "Canon", "graph_excluded.json")
    try:
        with open(excl_path, encoding="utf-8") as f:
            excl = json.load(f)
    except Exception:
        excl = []

    entry = {"source": source, "target": target, "label": label}
    if not any(x.get("source") == source and x.get("target") == target and x.get("label") == label for x in excl):
        excl.append(entry)
    os.makedirs(os.path.join(p, "Canon"), exist_ok=True)
    with open(excl_path, "w", encoding="utf-8") as f:
        json.dump(excl, f, indent=2)

    # Also purge from graph.json cache so it takes effect immediately
    cache_path = os.path.join(p, "Canon", "graph.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                cache = json.load(f)
            cache["edges"] = [
                edge for edge in cache.get("edges", [])
                if not (str(edge.get("source", "")) == source and
                        str(edge.get("target", "")) == target and
                        edge.get("label", "") == label)
            ]
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2)
        except Exception:
            pass

    return ok(msg="Edge excluded")


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


# ─── Undo / Snapshot ─────────────────────────────────────────────────────────

@app.route("/api/undo")
def list_undo():
    c, p, e = require_project()
    if e:
        return ok(snapshots=[])
    n = int(request.args.get("n", 15))
    return ok(snapshots=SnapshotManager.get_history(p, n))


@app.route("/api/undo/<snap_id>/restore", methods=["POST"])
def restore_undo(snap_id):
    c, p, e = require_project()
    if e: return e
    ok_flag, msg = SnapshotManager.restore(p, snap_id)
    if not ok_flag:
        return err(msg)
    return ok(msg=msg)


# ─── Server control ──────────────────────────────────────────────────────────

@app.route("/api/ping")
def ping():
    return ok(status="alive")


@app.route("/api/server/stop", methods=["POST"])
def server_stop():
    """Stop the Flask process; optionally relaunch in a new terminal window."""
    import threading, subprocess
    relaunch = (request.json or {}).get("relaunch", True)
    web_dir  = os.path.dirname(os.path.abspath(__file__))

    def _shutdown():
        if relaunch:
            subprocess.Popen(
                'start cmd /k python app.py',
                shell=True,
                cwd=web_dir,
            )
        import time; time.sleep(0.3)
        os._exit(0)

    threading.Thread(target=_shutdown, daemon=True).start()
    return ok(msg="Server stopping…")


# ─── Conversation Log ─────────────────────────────────────────────────────────

@app.route("/api/conversation-log")
def conversation_log():
    """
    Returns a merged, newest-first chronological log of:
      - All deliberation sessions (from session_log.jsonl)
      - All single-agent proposals (from proposals/)
    Each entry has: id, source, timestamp, agent, type, context, task, content, status, tokens
    """
    import re as _re
    c, p, e = require_project()
    if e:
        return ok(entries=[])

    entries = []

    # ── Sessions (deliberations) ──────────────────────────────────────────────
    sessions = SessionLogger.load(p, n=500)
    for s in sessions:
        entries.append({
            "id":        s.get("id", ""),
            "source":    "session",
            "timestamp": s.get("timestamp", ""),
            "team":      s.get("team", ""),
            "heading":   s.get("heading", ""),
            "task":      s.get("task", ""),
            "turns":     s.get("turns", []),
            "total_tokens": s.get("total_tokens", 0),
            "total_cost":   s.get("total_cost", 0.0),
        })

    # ── Single-agent proposals ────────────────────────────────────────────────
    pm  = ProposalManager(p)
    raw = pm.list_all()
    for prop in raw:
        rationale = prop.get("rationale", "")
        # Extract task from rationale (format: "Generated by X.\nTask: ...")
        task_match = _re.search(r"Task:\s*(.+?)(?:\n|$)", rationale, _re.DOTALL)
        task = task_match.group(1).strip() if task_match else rationale[:120]
        tf = prop.get("target_file", "")
        rel_target = os.path.relpath(tf, p) if os.path.isabs(tf) else tf
        entries.append({
            "id":        prop.get("id", ""),
            "source":    "proposal",
            "timestamp": prop.get("created", ""),
            "agent":     prop.get("agent", ""),
            "type":      prop.get("type", ""),
            "context":   rel_target,
            "task":      task,
            "content":   prop.get("new_content", ""),
            "status":    prop.get("status", ""),
            "tokens":    prop.get("tokens", {}),
        })

    # Sort newest first
    entries.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return ok(entries=entries[:500])


# ─── Book ─────────────────────────────────────────────────────────────────────

from src.book          import BookManager
from src.agents        import BookWriterAgent as _BookWriterAgent


def _build_book_context(project_path: str) -> dict:
    """
    Build a comprehensive context dict for book planning and chapter writing.
    Loads ALL KB entities and ALL WorldBible sections without the normal
    per-agent truncation limits — books need the full picture.
    """
    docs_root = os.path.join(project_path, "Documents")
    wb_root   = os.path.join(project_path, "WorldBible")

    # ── KB entities ────────────────────────────────────────────────────── #
    _FOLDERS = [
        ("Characters",    "LEAD CHARACTER"),
        ("Creatures",     "SUPPORTING CHARACTER"),
        ("Locations",     "LOCATION"),
        ("Concepts",      "CONCEPT"),
        ("Objects",       "OBJECT"),
        ("Events",        "EVENT"),
        ("WorldBuilding", "WORLD BUILDING"),
    ]
    kb_parts = []
    for folder_name, label in _FOLDERS:
        folder = os.path.join(docs_root, folder_name)
        if not os.path.isdir(folder):
            continue
        for fname in sorted(os.listdir(folder)):
            if not fname.endswith(".meta.json"):
                continue
            slug    = fname[:-len(".meta.json")]
            md_path = os.path.join(folder, f"{slug}.md")
            if not os.path.exists(md_path):
                continue
            try:
                with open(os.path.join(folder, fname), encoding="utf-8") as f:
                    meta = json.load(f)
                with open(md_path, encoding="utf-8") as f:
                    content = f.read().strip()
                if not content:
                    continue
                title = meta.get("title", slug)
                kb_parts.append(f"### {title} [{label}]\n{content}")
            except Exception:
                pass

    # ── WorldBible sections ────────────────────────────────────────────── #
    wb_parts = []
    wb_order = ["overview", "lore", "logic", "tone", "structure", "rules"]
    wb_labels = {
        "overview": "OVERVIEW",
        "lore":     "LORE & HISTORY",
        "logic":    "WORLD BIBLE",
        "tone":     "TONE & STYLE",
        "structure":"STRUCTURE",
        "rules":    "WORLD RULES",
    }
    for sid in wb_order:
        md_path = os.path.join(wb_root, f"{sid}.md")
        if os.path.exists(md_path):
            try:
                with open(md_path, encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    wb_parts.append(f"### {wb_labels.get(sid, sid.upper())}\n{content}")
            except Exception:
                pass

    # ── Canon & memory ─────────────────────────────────────────────────── #
    canon_path  = os.path.join(project_path, "Canon", "Canon.md")
    memory_path = os.path.join(project_path, "Memory", "WorkingMemory.md")
    canon_text  = open(canon_path,  encoding="utf-8").read() if os.path.exists(canon_path)  else ""
    memory_text = open(memory_path, encoding="utf-8").read() if os.path.exists(memory_path) else ""

    return {
        "canon":          canon_text,
        "working_memory": memory_text,
        "kb_documents":   "\n\n---\n\n".join(kb_parts),
        "world_bible":    "\n\n---\n\n".join(wb_parts),
        "world_rules":    wb_parts[-1] if wb_parts else "",  # rules is last
    }


@app.route("/api/book/status")
def book_status():
    c, p, e = require_project()
    if e: return ok(outline_exists=False, chapters=[], total_words=0,
                    target_words=85000, planned_chapters=0, next_chapter=1)
    bm = BookManager(p)
    return ok(**bm.status())


@app.route("/api/book/plan/stream", methods=["POST"])
def book_plan_stream():
    """
    Stream the chapter-by-chapter book outline.
    Uses BookWriterAgent with full KB + WorldBible context.
    Body: {task} (optional custom instruction)
    """
    c, p, e = require_project()
    if e: return e
    if not c.api_key: return err("No API key configured")

    user_task = (request.json or {}).get("task", "").strip()
    ctx       = _build_book_context(p)

    plan_task = (
        "You have been given the COMPLETE knowledge base for this story world — "
        "every character, location, concept, object, event, and world-building document, "
        "plus the full Story World Bible.\n\n"
        "Write a COMPLETE, FULL chapter-by-chapter outline for a novel based on this material.\n\n"
        "TARGET: 80,000–100,000 words across 25–30 chapters.\n\n"
        "CRITICAL REQUIREMENT: You MUST write ALL chapters, numbered 1 through the final chapter. "
        "Do NOT stop early. Do NOT summarise the remaining chapters. Do NOT write 'and so on' or "
        "'remaining chapters follow the same pattern'. Every single chapter gets its full entry. "
        "Keep writing until you have written the LAST chapter.\n\n"
        "STORY ARC STRUCTURE:\n"
        "- Chapters 1–5: Setup. Establish world, protagonist, central conflict.\n"
        "- Chapters 6–12: Rising action. Complications, relationships, stakes raised.\n"
        "- Chapter 13: Midpoint reversal. The story turns.\n"
        "- Chapters 14–19: Escalation. Allies tested, antagonist reveals, false victories.\n"
        "- Chapter 20: All-is-lost moment.\n"
        "- Chapters 21–25+: Climax, resolution, denouement.\n\n"
        "FOR EACH CHAPTER, write EXACTLY this format:\n"
        "## Chapter [N]: [Title]\n"
        "**Word target:** ~[3,000–4,500]\n"
        "**Setting:** [specific location from the knowledge base]\n"
        "**POV:** [character name]\n"
        "**Summary:** [2–3 paragraphs. Be specific. Use character names, locations, "
        "objects, events, and concepts from the knowledge base. What happens, what changes, "
        "what the reader feels, what the chapter's dramatic question is.]\n\n"
        "Reference ALL named characters (lead and supporting), ALL key locations, "
        "ALL significant objects, events, and concepts from the knowledge base. "
        "Nothing from the material should be wasted.\n\n"
        "BEGIN NOW with Chapter 1 and do not stop until you have written the final chapter.\n\n"
    )
    if user_task:
        plan_task += f"Additional guidance from the author: {user_task}"

    bm = BookManager(p)

    def generate():
        try:
            client = OpenAIClient(c.api_key, c.model)
            agent  = _BookWriterAgent(client, p, c)
            full   = ""
            for chunk in agent.run_stream(
                plan_task,
                context=ctx,
                temperature=0.75,
                max_tokens=16000,
            ):
                if isinstance(chunk, str):
                    full += chunk
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                else:
                    usage = chunk
                    bm.save_outline(full)
                    c.add_tokens(
                        usage.get("prompt_tokens", 0),
                        usage.get("completion_tokens", 0),
                        usage.get("cost", 0.0),
                    )
                    yield f"data: {json.dumps({'done': True, 'chapters': bm.count_planned_chapters()})}\n\n"
        except Exception as ex:
            yield f"data: {json.dumps({'error': str(ex)})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@app.route("/api/book/write-chapter/stream", methods=["POST"])
def book_write_chapter_stream():
    """
    Stream the writing of a single book chapter.
    Body: {chapter_number: int}
    """
    c, p, e = require_project()
    if e: return e
    if not c.api_key: return err("No API key configured")

    chapter_num = int((request.json or {}).get("chapter_number", 1))

    ctx          = _build_book_context(p)
    bm           = BookManager(p)
    outline      = bm.get_outline()
    chapter_brief = bm.get_chapter_brief(chapter_num)
    prev_end     = bm.previous_chapter_tail(chapter_num)

    ctx["book_outline"]         = outline
    ctx["chapter_number"]       = chapter_num
    ctx["chapter_brief"]        = chapter_brief
    ctx["previous_chapter_end"] = prev_end

    def generate():
        try:
            client = OpenAIClient(c.api_key, c.model)
            agent  = _BookWriterAgent(client, p, c)
            full   = ""
            for chunk in agent.run_stream(
                f"Write Chapter {chapter_num} of the novel.",
                context=ctx,
                temperature=0.85,
                max_tokens=6000,
            ):
                if isinstance(chunk, str):
                    full += chunk
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                else:
                    usage = chunk
                    bm.save_chapter(chapter_num, full)
                    wc = len(full.split())
                    c.add_tokens(
                        usage.get("prompt_tokens", 0),
                        usage.get("completion_tokens", 0),
                        usage.get("cost", 0.0),
                    )
                    yield f"data: {json.dumps({'done': True, 'word_count': wc, 'chapter': chapter_num})}\n\n"
        except Exception as ex:
            yield f"data: {json.dumps({'error': str(ex)})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@app.route("/api/book/chapter/<int:n>")
def get_book_chapter(n):
    c, p, e = require_project()
    if e: return e
    bm = BookManager(p)
    content = bm.get_chapter(n)
    if content is None:
        return err("Chapter not found")
    return ok(content=content, chapter=n)


@app.route("/api/book/outline", methods=["GET"])
def get_book_outline():
    c, p, e = require_project()
    if e: return e
    bm = BookManager(p)
    return ok(outline=bm.get_outline(), exists=bm.has_outline())


@app.route("/api/book/outline", methods=["PUT"])
def save_book_outline():
    """Save a manually edited outline."""
    c, p, e = require_project()
    if e: return e
    content = (request.json or {}).get("content", "")
    bm = BookManager(p)
    bm.save_outline(content)
    return ok(chapters=bm.count_planned_chapters())


@app.route("/api/book/export")
def export_book():
    c, p, e = require_project()
    if e: return e
    bm      = BookManager(p)
    content = bm.export_full_book()
    return ok(content=content, word_count=len(content.split()))


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
        SnapshotManager.push(p, wbm.section_path(section_id), f"WorldBible/{section_id} — manual edit")
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
