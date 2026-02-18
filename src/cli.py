"""
StoryVault Terminal UI
80s terminal aesthetic: black background, green text, Courier New, ASCII separators.
"""

import os
import sys

try:
    import colorama
    colorama.init(autoreset=True)
except ImportError:
    pass

# ANSI codes
GREEN  = '\033[92m'
WHITE  = '\033[97m'
DIM    = '\033[2m'
RESET  = '\033[0m'
BOLD   = '\033[1m'
RED    = '\033[91m'
YELLOW = '\033[93m'
CYAN   = '\033[96m'

WIDTH = 56


class CLI:
    def __init__(self):
        self.width = WIDTH

    # ------------------------------------------------------------------ #
    # Structural elements
    # ------------------------------------------------------------------ #

    def line(self):
        print(f"{GREEN}{'=' * self.width}{RESET}")

    def thin_line(self):
        print(f"{GREEN}{'-' * self.width}{RESET}")

    def blank(self):
        print()

    # ------------------------------------------------------------------ #
    # Text output
    # ------------------------------------------------------------------ #

    def msg(self, text, color=None):
        c = color if color else WHITE
        print(f"{c}{text}{RESET}")

    def success(self, text):
        print(f"{GREEN}[OK]  {text}{RESET}")

    def error(self, text):
        print(f"{RED}[ERR] {text}{RESET}", file=sys.stderr)

    def warn(self, text):
        print(f"{YELLOW}[!]   {text}{RESET}")

    def info(self, text):
        print(f"{DIM}>>    {text}{RESET}")

    def label(self, key, value, key_width=20):
        k = f"{key}:".ljust(key_width)
        print(f"{GREEN}{k}{RESET} {WHITE}{value}{RESET}")

    def header(self, project=None, model="gpt-4o-mini"):
        self.line()
        print(f"{GREEN}  STORYVAULT v0.1{RESET}")
        if project:
            print(f"{WHITE}  PROJECT : {project}{RESET}")
        print(f"{DIM}  MODEL   : {model}{RESET}")
        self.line()

    # ------------------------------------------------------------------ #
    # Interactive
    # ------------------------------------------------------------------ #

    def prompt(self, text=">"):
        try:
            return input(f"\n{GREEN}{text} {RESET}").strip()
        except EOFError:
            return ""

    def confirm(self, text):
        try:
            answer = input(f"{YELLOW}{text} [y/N]: {RESET}").strip().lower()
            return answer == 'y'
        except EOFError:
            return False

    # ------------------------------------------------------------------ #
    # Menus
    # ------------------------------------------------------------------ #

    def show_main_menu(self):
        self.header()
        self.blank()
        items = [
            ("[1]", "create-project <name>",  "Create new project"),
            ("[2]", "run-agent <type>",        "Run AI agent"),
            ("[3]", "review",                  "Review pending proposals"),
            ("[4]", "approve <id>",            "Approve proposal"),
            ("[5]", "export-screenplay",       "Export formatted screenplay"),
            ("[6]", "status",                  "System status"),
            ("[7]", "help",                    "Full command list"),
        ]
        for num, cmd, desc in items:
            print(f"  {GREEN}{num}{RESET} {WHITE}{cmd:<28}{RESET} {DIM}{desc}{RESET}")
        self.blank()
        print(f"{DIM}  Usage: python storyvault.py <command> [args]{RESET}")
        self.line()

    def show_help(self):
        self.line()
        print(f"{GREEN}  STORYVAULT COMMANDS{RESET}")
        self.thin_line()
        commands = [
            ("create-project <name>",      "Create a new project"),
            ("set-project <name>",         "Switch active project"),
            ("",                           ""),
            ("run-agent <type>",           "Run agent: writer/critic/editor/archivist"),
            ("run-phase <phase>",          "Run pipeline phase"),
            ("",                           ""),
            ("propose <type>",             "Create a manual proposal"),
            ("review",                     "List pending proposals"),
            ("approve <id>",               "Approve and apply proposal"),
            ("reject <id> [reason]",       "Reject proposal"),
            ("",                           ""),
            ("create-scene <num>",         "Create scene card"),
            ("draft-scene <num>",          "Draft scene (writer agent)"),
            ("critique-scene <num>",       "Critique scene (critic agent)"),
            ("revise-scene <num>",         "Revise scene (editor agent)"),
            ("approve-scene <num>",        "Approve and lock scene"),
            ("",                           ""),
            ("compress-memory",            "Compress working memory (archivist)"),
            ("lock-canon",                 "Lock canon file"),
            ("unlock-canon",               "Unlock canon file"),
            ("",                           ""),
            ("export-screenplay",          "Export screenplay .txt"),
            ("status",                     "Show full system status"),
            ("tokens",                     "Show token usage and cost"),
            ("set-key <apikey>",           "Store OpenAI API key"),
        ]
        for cmd, desc in commands:
            if not cmd:
                self.blank()
                continue
            print(f"  {GREEN}{cmd:<35}{RESET} {DIM}{desc}{RESET}")
        self.line()

    # ------------------------------------------------------------------ #
    # Display helpers
    # ------------------------------------------------------------------ #

    def show_tokens(self, tracking):
        prompt_t = tracking.get('total_prompt_tokens', 0)
        comp_t   = tracking.get('total_completion_tokens', 0)
        cost     = tracking.get('total_cost', 0.0)
        self.thin_line()
        print(f"{GREEN}  TOKEN USAGE{RESET}")
        self.thin_line()
        self.label("Prompt tokens",     f"{prompt_t:,}")
        self.label("Completion tokens", f"{comp_t:,}")
        self.label("Total tokens",      f"{prompt_t + comp_t:,}")
        self.label("Estimated cost",    f"${cost:.4f}")
        self.thin_line()

    def show_usage_line(self, usage):
        t = usage.get('total_tokens', 0)
        c = usage.get('cost', 0.0)
        print(f"{DIM}  Tokens used: {t:,}   Estimated cost: ${c:.4f}{RESET}")

    def show_proposal(self, data):
        self.line()
        print(f"{GREEN}  PROPOSAL: {data.get('id','?')}{RESET}")
        self.thin_line()
        self.label("Agent",   data.get('agent', '-'))
        self.label("Type",    data.get('type', '-'))
        self.label("Status",  data.get('status', '-'))
        self.label("Target",  data.get('target_file', '-'))
        self.label("Created", data.get('created', '-'))
        self.thin_line()
        print(f"{WHITE}  RATIONALE:{RESET}")
        rat = data.get('rationale', '')
        for ln in rat.splitlines()[:6]:
            print(f"  {DIM}{ln}{RESET}")
        self.thin_line()
        print(f"{WHITE}  DIFF PREVIEW:{RESET}")
        diff = data.get('diff', '')
        for ln in diff.splitlines()[:30]:
            if ln.startswith('+') and not ln.startswith('+++'):
                print(f"  {GREEN}{ln}{RESET}")
            elif ln.startswith('-') and not ln.startswith('---'):
                print(f"  {RED}{ln}{RESET}")
            else:
                print(f"  {DIM}{ln}{RESET}")
        self.line()

    def show_scene_list(self, scenes):
        self.thin_line()
        print(f"{GREEN}  SCENES{RESET}")
        self.thin_line()
        if not scenes:
            print(f"  {DIM}No scenes created.{RESET}")
        for s in scenes:
            num    = s.get('scene_num', '?')
            phase  = s.get('phase', '-')
            locked = ' [LOCKED]' if s.get('locked') else ''
            title  = s.get('title', '')
            title_str = f" - {title}" if title else ""
            print(f"  {GREEN}SCENE {int(num):02d}{title_str:<20}{RESET} "
                  f"{WHITE}{phase:<12}{RESET}{RED}{locked}{RESET}")
        self.thin_line()

    def pager(self, content, title=""):
        if title:
            self.line()
            print(f"{GREEN}  {title}{RESET}")
            self.thin_line()
        for ln in content.splitlines():
            print(f"  {WHITE}{ln}{RESET}")
        self.line()
