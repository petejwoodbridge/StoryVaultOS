"""
StoryVault Command Router
Routes CLI arguments to the appropriate subsystem.
All commands that touch AI must go through: propose → review → approve/reject.
"""

import os
import sys

from .config       import Config
from .openai_client import OpenAIClient
from .project      import ProjectManager
from .proposal     import ProposalManager
from .canon        import CanonManager
from .memory       import MemoryManager
from .scene        import SceneManager
from .export       import ExportEngine
from .version      import VersionTracker
from .agents       import AGENT_REGISTRY


class CommandRouter:
    def __init__(self, cli):
        self.cli    = cli
        self.config = Config()

    # ================================================================== #
    # Route
    # ================================================================== #

    def route(self, command: str, args: list[str]):
        handlers = {
            # Project
            "create-project":    self.cmd_create_project,
            "set-project":       self.cmd_set_project,
            # Agent execution
            "run-agent":         self.cmd_run_agent,
            "run-phase":         self.cmd_run_phase,
            # Proposal lifecycle
            "propose":           self.cmd_propose,
            "review":            self.cmd_review,
            "approve":           self.cmd_approve,
            "reject":            self.cmd_reject,
            # Memory
            "compress-memory":   self.cmd_compress_memory,
            # Canon
            "lock-canon":        self.cmd_lock_canon,
            "unlock-canon":      self.cmd_unlock_canon,
            # Scene workflow
            "create-scene":      self.cmd_create_scene,
            "draft-scene":       self.cmd_draft_scene,
            "critique-scene":    self.cmd_critique_scene,
            "revise-scene":      self.cmd_revise_scene,
            "approve-scene":     self.cmd_approve_scene,
            # Output
            "export-screenplay": self.cmd_export_screenplay,
            # System
            "status":            self.cmd_status,
            "tokens":            self.cmd_tokens,
            "set-key":           self.cmd_set_key,
            "help":              self.cmd_help,
            "--help":            self.cmd_help,
            "-h":                self.cmd_help,
            # Web UI
            "web":               self.cmd_web,
        }
        handler = handlers.get(command)
        if handler:
            handler(args)
        else:
            self.cli.error(f"Unknown command: {command}")
            self.cli.info("Run: python storyvault.py help")

    # ================================================================== #
    # Guards
    # ================================================================== #

    def _require_project(self) -> str:
        p = self.config.project_path()
        if not p or not os.path.isdir(p):
            self.cli.error("No active project. Run: python storyvault.py set-project <name>")
            sys.exit(1)
        return p

    def _require_api_key(self) -> str:
        key = self.config.api_key
        if not key:
            self.cli.error("No OpenAI API key found.")
            self.cli.info("Set env var: OPENAI_API_KEY=sk-...")
            self.cli.info("Or run: python storyvault.py set-key <key>")
            sys.exit(1)
        return key

    def _get_openai(self) -> OpenAIClient:
        return OpenAIClient(self._require_api_key(), self.config.model)

    def _track(self, usage: dict | None):
        if usage:
            self.config.add_tokens(
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
                usage.get("cost", 0.0),
            )

    def _proposal_manager(self, project_path: str) -> ProposalManager:
        return ProposalManager(project_path)

    # ================================================================== #
    # Project
    # ================================================================== #

    def cmd_create_project(self, args: list[str]):
        if not args:
            self.cli.error("Usage: create-project <name>")
            return

        name = "_".join(args).upper()
        pm   = ProjectManager(self.config.vault_path)

        ok, msg = pm.create(name)
        if ok:
            self.config.current_project = name
            self.cli.header(name, self.config.model)
            self.cli.success(f"Project created: {name}")
            self.cli.info("Active project set.")
            self.cli.info(f"Edit canon: StoryVault/Projects/{name}/Canon/Canon.md")
        else:
            self.cli.error(msg)

    def cmd_set_project(self, args: list[str]):
        if not args:
            projects = self.config.list_projects()
            self.cli.line()
            print(f"\033[92m  PROJECTS\033[0m")
            self.cli.thin_line()
            if not projects:
                self.cli.msg("  No projects found.")
            for p in projects:
                marker = "  *" if p == self.config.current_project else "   "
                self.cli.msg(f"{marker} {p}")
            self.cli.line()
            return

        name = "_".join(args).upper()
        if not os.path.isdir(self.config.project_path(name) or ""):
            self.cli.error(f"Project not found: {name}")
            self.cli.info("Run: python storyvault.py create-project <name>")
            return

        self.config.current_project = name
        self.cli.success(f"Active project: {name}")

    # ================================================================== #
    # Agent execution
    # ================================================================== #

    def cmd_run_agent(self, args: list[str]):
        if not args:
            self.cli.error("Usage: run-agent <type> [--target <relpath>] [--task <text>]")
            self.cli.info(f"Types: {', '.join(AGENT_REGISTRY.keys())}")
            return

        agent_type = args[0].lower()
        if agent_type not in AGENT_REGISTRY:
            self.cli.error(f"Unknown agent type: {agent_type}")
            self.cli.info(f"Available: {', '.join(AGENT_REGISTRY.keys())}")
            return

        project_path = self._require_project()

        # Parse --target and --task flags
        target_rel = None
        task       = None
        i = 1
        while i < len(args):
            if args[i] == "--target" and i + 1 < len(args):
                target_rel = args[i + 1]; i += 2
            elif args[i] == "--task" and i + 1 < len(args):
                task = " ".join(args[i + 1:]); break
            else:
                i += 1

        if not task:
            task = self.cli.prompt(f"Task for {agent_type} agent")
        if not task:
            self.cli.error("No task specified.")
            return

        if not target_rel:
            target_rel = self.cli.prompt("Target file (relative to project root)")
        if not target_rel:
            self.cli.error("No target file specified.")
            return

        target_file = os.path.join(project_path, target_rel)

        self._run_agent_to_proposal(
            agent_type=agent_type,
            task=task,
            target_file=target_file,
            project_path=project_path,
        )

    def _run_agent_to_proposal(
        self,
        agent_type: str,
        task: str,
        target_file: str,
        project_path: str,
        context: dict | None = None,
        proposal_type: str | None = None,
    ) -> tuple[str | None, dict | None]:
        """Run an agent and submit its output as a proposal. Returns (prop_id, usage)."""
        self.cli.line()
        self.cli.info(f"Agent    : {agent_type.upper()}")
        self.cli.info(f"Task     : {task[:70]}")
        self.cli.info(f"Target   : {os.path.relpath(target_file, project_path)}")
        self.cli.thin_line()
        self.cli.msg("  Calling OpenAI...")

        openai_client = self._get_openai()
        pm            = self._proposal_manager(project_path)
        AgentClass    = AGENT_REGISTRY[agent_type]
        agent         = AgentClass(openai_client, project_path, self.config)

        try:
            prop_id, prop_data, usage = agent.propose(
                task=task,
                target_file=target_file,
                proposal_manager=pm,
                context=context,
                proposal_type=proposal_type,
            )
        except Exception as e:
            self.cli.error(f"Agent failed: {e}")
            return None, None

        self._track(usage)

        self.cli.thin_line()
        self.cli.success(f"Proposal created : {prop_id}")
        self.cli.show_usage_line(usage)
        self.cli.info("Review with: python storyvault.py review")
        self.cli.line()
        return prop_id, usage

    def cmd_run_phase(self, args: list[str]):
        """
        Pre-defined pipeline phases:
          development  - writer on all non-drafted scenes
          critique     - critic on all drafted scenes
          revision     - editor on all critiqued scenes
          memory       - archivist compress working memory
        """
        if not args:
            self.cli.error("Usage: run-phase <phase>")
            self.cli.info("Phases: development | critique | revision | memory")
            return

        phase        = args[0].lower()
        project_path = self._require_project()
        sm           = SceneManager(project_path)
        scenes       = sm.list_scenes()

        if phase == "development":
            targets = [s for s in scenes if s.get("phase") == "CREATED"]
            if not targets:
                self.cli.warn("No scenes in CREATED phase."); return
            for sc in targets:
                num = sc["scene_num"]
                self.cli.msg(f"\n  >> Drafting scene {num:02d}...")
                self._draft_scene(num, project_path, sm)

        elif phase == "critique":
            targets = [s for s in scenes if s.get("phase") == "DRAFTED"]
            if not targets:
                self.cli.warn("No scenes in DRAFTED phase."); return
            for sc in targets:
                num = sc["scene_num"]
                self.cli.msg(f"\n  >> Critiquing scene {num:02d}...")
                self._critique_scene(num, project_path, sm)

        elif phase == "revision":
            targets = [s for s in scenes if s.get("phase") == "CRITIQUED"]
            if not targets:
                self.cli.warn("No scenes in CRITIQUED phase."); return
            for sc in targets:
                num = sc["scene_num"]
                self.cli.msg(f"\n  >> Revising scene {num:02d}...")
                self._revise_scene(num, project_path, sm)

        elif phase == "memory":
            self.cmd_compress_memory([])

        else:
            self.cli.error(f"Unknown phase: {phase}")
            self.cli.info("Phases: development | critique | revision | memory")

    # ================================================================== #
    # Proposal lifecycle
    # ================================================================== #

    def cmd_propose(self, args: list[str]):
        """Manually create a proposal from a file."""
        project_path = self._require_project()

        prop_type  = args[0] if args else "manual-edit"
        target_rel = self.cli.prompt("Target file (relative to project)")
        if not target_rel:
            return
        target_file = os.path.join(project_path, target_rel)

        self.cli.msg("Enter new content (end with a line containing only '---END'):")
        lines = []
        while True:
            try:
                line = input()
            except EOFError:
                break
            if line == "---END":
                break
            lines.append(line)

        new_content = "\n".join(lines)
        if not new_content.strip():
            self.cli.error("No content entered.")
            return

        rationale = self.cli.prompt("Rationale (optional)")
        pm = self._proposal_manager(project_path)
        prop_id, _ = pm.create(
            agent_name="Manual",
            proposal_type=prop_type,
            target_file=target_file,
            new_content=new_content,
            rationale=rationale or "Manual proposal.",
        )
        self.cli.success(f"Proposal created: {prop_id}")

    def cmd_review(self, args: list[str]):
        project_path = self._require_project()
        pm           = self._proposal_manager(project_path)
        pending      = pm.list_pending()

        self.cli.header(self.config.current_project, self.config.model)

        if not pending:
            self.cli.msg("  No pending proposals.")
            self.cli.line()
            return

        self.cli.msg(f"  {len(pending)} PENDING PROPOSAL(S)")
        self.cli.thin_line()

        for i, data in enumerate(pending, 1):
            print(
                f"\033[92m  [{i}]\033[0m "
                f"\033[97m{data['id']}\033[0m  "
                f"\033[2m{data.get('agent','?')} | {data.get('type','?')}\033[0m"
            )
            print(
                f"       target: \033[97m"
                f"{os.path.relpath(data.get('target_file',''), project_path)}"
                f"\033[0m"
            )

        self.cli.thin_line()

        if args and args[0] == "--detail":
            for data in pending:
                self.cli.show_proposal(data)
        else:
            self.cli.info("View detail: python storyvault.py review --detail")
            self.cli.info("Approve    : python storyvault.py approve <id>")
            self.cli.info("Reject     : python storyvault.py reject <id>")

        self.cli.line()

    def cmd_approve(self, args: list[str]):
        if not args:
            self.cli.error("Usage: approve <proposal-id>")
            return

        prop_id      = args[0]
        project_path = self._require_project()
        pm           = self._proposal_manager(project_path)

        data = pm.get(prop_id)
        if not data:
            self.cli.error(f"Proposal not found: {prop_id}")
            return

        # Canon lock check
        target = data.get("target_file", "")
        canon_path = os.path.join(project_path, "Canon", "Canon.md")
        if os.path.normpath(target) == os.path.normpath(canon_path):
            cm = CanonManager(project_path)
            if cm.is_locked():
                self.cli.error("Canon is LOCKED. Unlock first: python storyvault.py unlock-canon")
                return

        # Show a brief summary
        self.cli.line()
        self.cli.msg(f"  Approving: {prop_id}")
        self.cli.label("  Agent",  data.get("agent", "-"))
        self.cli.label("  Target", os.path.relpath(target, project_path))
        self.cli.thin_line()

        ok, msg = pm.approve(prop_id)
        if ok:
            # Commit to version log
            vt = VersionTracker(project_path)
            commit_id = vt.commit(pm.get(prop_id))
            self.cli.success(f"Applied: {msg}")
            self.cli.success(f"Commit : {commit_id}")
        else:
            self.cli.error(msg)

        self.cli.line()

    def cmd_reject(self, args: list[str]):
        if not args:
            self.cli.error("Usage: reject <proposal-id> [reason]")
            return

        prop_id      = args[0]
        reason       = " ".join(args[1:]) if len(args) > 1 else ""
        project_path = self._require_project()
        pm           = self._proposal_manager(project_path)

        if not reason:
            reason = self.cli.prompt("Rejection reason (optional)")

        ok, msg = pm.reject(prop_id, reason)
        if ok:
            vt = VersionTracker(project_path)
            vt.commit(pm.get(prop_id))
            self.cli.success(f"Proposal rejected: {prop_id}")
        else:
            self.cli.error(msg)

    # ================================================================== #
    # Memory
    # ================================================================== #

    def cmd_compress_memory(self, args: list[str]):
        project_path = self._require_project()
        mm = MemoryManager(project_path)

        current = mm.read_working()
        if not current.strip():
            self.cli.warn("Working memory is empty. Nothing to compress.")
            return

        self.cli.line()
        self.cli.msg(f"  Working memory size: {mm.get_size_display()}")
        self.cli.thin_line()

        # Archive current before proposing compression
        archive = mm.archive_working()
        self.cli.info(f"Archived to: {os.path.relpath(archive, project_path)}")

        target_file = mm.working_path
        self._run_agent_to_proposal(
            agent_type="archivist",
            task="Compress and restructure the working memory. Preserve all critical story information. Target 30-50% of original length.",
            target_file=target_file,
            project_path=project_path,
            proposal_type="memory-compression",
        )

    # ================================================================== #
    # Canon
    # ================================================================== #

    def cmd_lock_canon(self, args: list[str]):
        project_path = self._require_project()
        cm = CanonManager(project_path)

        if not self.cli.confirm("Lock Canon.md? It will be immutable until unlocked."):
            self.cli.msg("  Cancelled.")
            return

        ok, msg = cm.lock()
        if ok:
            self.cli.success(msg)
        else:
            self.cli.error(msg)

    def cmd_unlock_canon(self, args: list[str]):
        project_path = self._require_project()
        cm = CanonManager(project_path)

        self.cli.warn("Unlocking canon allows agents to propose changes to Canon.md.")
        if not self.cli.confirm("Unlock Canon.md?"):
            self.cli.msg("  Cancelled.")
            return

        ok, msg = cm.unlock()
        if ok:
            self.cli.success(msg)
            self.cli.warn("Remember to re-lock when edits are complete.")
        else:
            self.cli.error(msg)

    # ================================================================== #
    # Scene workflow
    # ================================================================== #

    def cmd_create_scene(self, args: list[str]):
        if not args:
            self.cli.error("Usage: create-scene <number> [title]")
            return

        try:
            num = int(args[0])
        except ValueError:
            self.cli.error("Scene number must be an integer.")
            return

        project_path = self._require_project()
        sm = SceneManager(project_path)

        title       = " ".join(args[1:]) if len(args) > 1 else ""
        location    = self.cli.prompt("Location (e.g. INT. THE LAB - NIGHT)")
        time_of_day = self.cli.prompt("Time of day (e.g. NIGHT, DAY, DUSK)")
        description = self.cli.prompt("Scene description (one line)")

        ok, msg = sm.create(num, title, location, time_of_day, description)
        if ok:
            self.cli.success(msg)
            self.cli.info(f"Draft with: python storyvault.py draft-scene {num}")
        else:
            self.cli.error(msg)

    def cmd_draft_scene(self, args: list[str]):
        if not args:
            self.cli.error("Usage: draft-scene <number>")
            return
        try:
            num = int(args[0])
        except ValueError:
            self.cli.error("Scene number must be an integer.")
            return

        project_path = self._require_project()
        sm = SceneManager(project_path)
        self._draft_scene(num, project_path, sm)

    def _draft_scene(self, num: int, project_path: str, sm: SceneManager):
        meta = sm.get_meta(num)
        if not meta:
            self.cli.error(f"Scene {num:02d} does not exist. Create it first.")
            return
        if sm.is_locked(num):
            self.cli.error(f"Scene {num:02d} is locked.")
            return

        card = sm.get_card(num)
        target_file = sm.scene_file(num, "draft.md")

        self._run_agent_to_proposal(
            agent_type="writer",
            task=f"Draft scene {num:02d}. Write the full scene as a screenplay excerpt in markdown. Use the scene card below as your brief.",
            target_file=target_file,
            project_path=project_path,
            context={"current_content": card},
            proposal_type="scene-draft",
        )
        sm.update_phase(num, "DRAFTED")

    def cmd_critique_scene(self, args: list[str]):
        if not args:
            self.cli.error("Usage: critique-scene <number>")
            return
        try:
            num = int(args[0])
        except ValueError:
            self.cli.error("Scene number must be an integer.")
            return

        project_path = self._require_project()
        sm = SceneManager(project_path)
        self._critique_scene(num, project_path, sm)

    def _critique_scene(self, num: int, project_path: str, sm: SceneManager):
        meta = sm.get_meta(num)
        if not meta:
            self.cli.error(f"Scene {num:02d} does not exist.")
            return
        if sm.is_locked(num):
            self.cli.error(f"Scene {num:02d} is locked.")
            return

        content = sm.get_draft(num) or sm.get_card(num)
        if not content:
            self.cli.error(f"No content found for scene {num:02d}. Draft it first.")
            return

        target_file = sm.scene_file(num, "critique.md")

        self._run_agent_to_proposal(
            agent_type="critic",
            task=f"Critique scene {num:02d}. Evaluate dramatic effectiveness, character consistency, and canon fidelity.",
            target_file=target_file,
            project_path=project_path,
            context={"current_content": content},
            proposal_type="scene-critique",
        )
        sm.update_phase(num, "CRITIQUED")

    def cmd_revise_scene(self, args: list[str]):
        if not args:
            self.cli.error("Usage: revise-scene <number>")
            return
        try:
            num = int(args[0])
        except ValueError:
            self.cli.error("Scene number must be an integer.")
            return

        project_path = self._require_project()
        sm = SceneManager(project_path)
        self._revise_scene(num, project_path, sm)

    def _revise_scene(self, num: int, project_path: str, sm: SceneManager):
        meta = sm.get_meta(num)
        if not meta:
            self.cli.error(f"Scene {num:02d} does not exist.")
            return
        if sm.is_locked(num):
            self.cli.error(f"Scene {num:02d} is locked.")
            return

        content  = sm.get_draft(num)
        critique = sm.get_critique(num)

        if not content:
            self.cli.error(f"No draft found for scene {num:02d}. Draft it first.")
            return
        if not critique:
            self.cli.warn(f"No critique found for scene {num:02d}. Running without critique notes.")

        target_file = sm.scene_file(num, "revision.md")

        self._run_agent_to_proposal(
            agent_type="editor",
            task=f"Revise scene {num:02d} based on the critique notes. Produce the complete revised scene.",
            target_file=target_file,
            project_path=project_path,
            context={"current_content": content, "critique": critique},
            proposal_type="scene-revision",
        )
        sm.update_phase(num, "REVISED")

    def cmd_approve_scene(self, args: list[str]):
        if not args:
            self.cli.error("Usage: approve-scene <number>")
            return
        try:
            num = int(args[0])
        except ValueError:
            self.cli.error("Scene number must be an integer.")
            return

        project_path = self._require_project()
        sm = SceneManager(project_path)

        meta = sm.get_meta(num)
        if not meta:
            self.cli.error(f"Scene {num:02d} does not exist.")
            return
        if sm.is_locked(num):
            self.cli.error(f"Scene {num:02d} is already locked.")
            return

        content = sm.get_best_content(num)
        if not content:
            self.cli.error(f"Scene {num:02d} has no content. Draft it first.")
            return

        self.cli.warn(f"Approving scene {num:02d} will lock it permanently.")
        if not self.cli.confirm(f"Lock scene {num:02d}?"):
            self.cli.msg("  Cancelled.")
            return

        sm.lock(num)
        sm.update_phase(num, "APPROVED")
        self.cli.success(f"Scene {num:02d} approved and locked.")
        self.cli.info("Scene file is now immutable.")

    # ================================================================== #
    # Export
    # ================================================================== #

    def cmd_export_screenplay(self, args: list[str]):
        project_path = self._require_project()

        include_all = "--all" in args
        if include_all:
            self.cli.warn("Exporting all scenes (including unapproved).")

        ee = ExportEngine(project_path)
        output_path, content = ee.export(include_unapproved=include_all)

        self.cli.line()
        self.cli.success(f"Screenplay exported:")
        self.cli.msg(f"  {output_path}")
        self.cli.thin_line()

        # Preview first 30 lines
        for ln in content.splitlines()[:30]:
            print(f"  \033[97m{ln}\033[0m")
        self.cli.info("...")
        self.cli.line()

    # ================================================================== #
    # Status
    # ================================================================== #

    def cmd_status(self, args: list[str]):
        self.cli.header(self.config.current_project or "NONE", self.config.model)

        if not self.config.current_project:
            self.cli.warn("No active project. Run: python storyvault.py set-project <name>")
            self.cli.line()
            return

        project_path = self.config.project_path()
        pm_proj = ProjectManager(self.config.vault_path)
        status  = pm_proj.get_status(project_path)

        # Project info
        self.cli.label("  Project",   self.config.current_project)
        self.cli.label("  Model",     self.config.model)
        self.cli.label("  API Key",   "SET" if self.config.api_key else "NOT SET")
        self.cli.thin_line()

        # Canon
        canon_lock = "LOCKED" if status["canon_locked"] else "unlocked"
        self.cli.label("  Canon",  f"{status['canon_size_bytes']:,} bytes  [{canon_lock}]")
        self.cli.label("  Memory", f"{status['memory_size_bytes']:,} bytes")
        self.cli.thin_line()

        # Scenes
        sm     = SceneManager(project_path)
        scenes = sm.list_scenes()
        self.cli.label("  Scenes", f"{status['scene_count']} total")
        if scenes:
            self.cli.show_scene_list(scenes)

        # Proposals
        self.cli.label("  Proposals", f"{status['pending_proposals']} pending")

        # Tokens
        self.cli.thin_line()
        tracking = self.config.token_tracking
        self.cli.show_tokens(tracking)

        # Version history
        vt    = VersionTracker(project_path)
        stats = vt.get_stats()
        self.cli.label("  Commits",  str(stats["total_commits"]))
        self.cli.label("  Approved", str(stats["approved"]))
        self.cli.label("  Rejected", str(stats["rejected"]))
        self.cli.line()

    # ================================================================== #
    # Tokens / key / help
    # ================================================================== #

    def cmd_tokens(self, args: list[str]):
        self.cli.header(self.config.current_project or "NONE", self.config.model)
        self.cli.show_tokens(self.config.token_tracking)

        if self.config.current_project:
            project_path = self.config.project_path()
            vt   = VersionTracker(project_path)
            stats = vt.get_stats()
            self.cli.label("  Commits",       str(stats["total_commits"]))
            self.cli.label("  Cumulative cost", f"${stats['total_cost']:.4f}")

        self.cli.line()

    def cmd_set_key(self, args: list[str]):
        if not args:
            self.cli.error("Usage: set-key <your-openai-api-key>")
            return

        key = args[0].strip()
        if not key.startswith("sk-"):
            self.cli.warn("Key does not start with 'sk-'. Storing anyway.")

        self.config.api_key = key
        self.cli.success("API key stored in config.json.")
        self.cli.warn("Consider using the OPENAI_API_KEY environment variable instead.")

    def cmd_help(self, args: list[str]):
        self.cli.show_help()

    # ================================================================== #
    # Web UI
    # ================================================================== #

    def cmd_web(self, args: list[str]):
        port = 5000
        for a in args:
            try:
                port = int(a)
            except ValueError:
                pass

        self.cli.line()
        print(f"\033[92m  STORYVAULT WEB UI\033[0m")
        self.cli.thin_line()
        print(f"\033[97m  URL   : http://localhost:{port}\033[0m")
        print(f"\033[2m  Stop  : Ctrl+C\033[0m")
        self.cli.line()

        try:
            from web.app import app as flask_app
            flask_app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
        except ImportError:
            self.cli.error("Flask not installed. Run: pip install flask")
        except OSError as e:
            self.cli.error(f"Could not start server: {e}")
