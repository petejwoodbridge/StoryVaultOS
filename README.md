# StoryVaultOS

**A local-first, multi-agent AI operating system for screenwriters and story developers.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Powered by OpenAI](https://img.shields.io/badge/powered%20by-OpenAI-412991.svg)](https://openai.com/)

---

## What is StoryVaultOS?

StoryVaultOS is a creative development environment for screenwriters, novelists, and showrunners
who want AI collaboration on their own terms. It runs entirely on your machine, stores everything
as plain Markdown files, and puts a team of 11 specialised AI agents at your disposal — each
with a distinct voice and area of expertise.

The key design principle is **human-in-the-loop**. No AI agent writes directly to your story.
Every suggestion, revision, and new scene goes through a **Propose → Review → Approve** cycle.
You see the diff. You decide what lands.

It's built for the long project: the feature, the pilot, the series bible. The kind of work
where continuity matters, where contradictions accumulate, and where you need a system that
remembers everything you've decided.

**What it isn't:** a one-click story generator, a writing app, or a chatbot. It's a toolkit.

---

## Features

- **Browser-based UI** — a terminal-aesthetic web interface for all core workflows
- **11 specialised agents** — Writer, Critic, Editor, Archivist, Producer, Character, Structure,
  Logline, Treatment, Lore, and Showrunner, each with a distinct methodology
- **Multi-agent deliberation** — send a task to a whole team; agents debate, critique each other,
  and synthesise a recommendation; you control the number of rounds (1–5)
- **Proposal system** — every AI output is a proposal; nothing changes until you approve it
- **World Bible** — 6-section structure (Overview, Lore, Logic, Tone, Structure, Rules) for
  capturing your story world; agents flag contradictions inline
- **Knowledge Base** — character, location, creature, world element documents; impact-checked
  when you save changes; KB-aware agents flag conflicts during deliberation
- **Scene workflow** — structured cards, drafts, critiques, revisions; exportable as screenplay
- **Agent Room** — real-time deliberation feed with live streaming SSE output
- **Version tracking** — immutable commit log for every approved change
- **Token tracking** — built-in cost monitoring across all API calls
- **Local-first** — all your story data lives in plain Markdown on your machine
- **CLI interface** — 80s terminal aesthetic for power users

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/StoryVaultOS.git
cd StoryVaultOS
pip install -r requirements.txt
```

### 2. Configure your API key

**Option A — `.env` file (recommended):**
```bash
cp .env.example .env
# Open .env and replace sk-... with your actual OpenAI API key
```

**Option B — environment variable:**
```bash
# Linux / macOS
export OPENAI_API_KEY=sk-your-key-here

# Windows CMD
set OPENAI_API_KEY=sk-your-key-here

# Windows PowerShell
$env:OPENAI_API_KEY="sk-your-key-here"
```

**Option C — CLI command (after first launch):**
```bash
python storyvault.py set-key sk-your-key-here
```

Get an API key at [platform.openai.com/api-keys](https://platform.openai.com/api-keys).
StoryVaultOS uses `gpt-4o-mini` by default — fast and inexpensive for development work.

### 3. Bootstrap a demo project (optional)

To explore the system with pre-loaded sample content (a near-future sci-fi mystery called
*THE SIGNAL*):

```bash
# Linux / macOS
cp -r StoryVault.example StoryVault

# Windows CMD
xcopy StoryVault.example StoryVault /E /I

# Windows PowerShell
Copy-Item -Recurse StoryVault.example StoryVault
```

### 4. Launch the web UI

```bash
cd web
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

> **First run without the demo project:** StoryVaultOS will create the `StoryVault/` vault
> directory automatically. Use **PROJECTS → New Project** to create your first project.

---

## Web Interface

The browser UI is the primary way to work with StoryVaultOS. Navigate using the top bar.

### PROJECTS
Create and switch between story projects. Each project gets a structured vault of Canon,
Characters, Scenes, World Bible, Knowledge Base, and History directories.

### CANON
Your project's immutable world rules. Sections can be locked to prevent accidental edits.
Use the team room to workshop rule changes with the full agent team before committing.

### WORLD BIBLE
Six-section story bible: **Overview** (logline, premise, theme), **Lore** (history, mythology),
**Logic** (how the world works), **Tone** (voice, aesthetic, reference points), **Story**
(prose summary of the full story arc — acts, key turns, inciting incident, climax), and **Rules** (hard constraints).

Each section has:
- **RUN AGENT ▾** — single agent revision with proposal output
- **RUN TEAM ▾** — full team brainstorm with live streaming deliberation; configurable rounds;
  agents flag KB contradictions inline with `⚠️ CONTRADICTION:` markers
- **BUILD ALL SECTIONS** (Overview only) — one team session covering all six sections,
  then parsed into individual proposals

### KNOWLEDGE BASE
Document-level knowledge management. Create character, location, creature, and world-element
documents. Features:
- **Save + Check Impact** — after saving a document, identify all other documents and canon
  sections that may need updating
- **Sync to KB** — extract entities from a story bible document and create missing records
- **Find Mentions** — locate every document that references a character or location

### SCENES
Scene lifecycle management:
1. Create a scene card (location, characters, purpose, emotional beat)
2. Draft with a writer agent
3. Critique with the critic agent
4. Revise based on critique
5. Approve and lock

Approved scenes can be exported as a Courier-format screenplay PDF.

### AGENT ROOM
A free-form team deliberation space. Choose a team, set the number of rounds (1–5), write
a task, and watch the agents debate in real time via a live SSE feed. The Showrunner opens
the room, specialists deliberate, the Showrunner synthesises. Output goes to the proposal queue.

### REVIEW
The proposal queue. Every AI output lands here — pending your approval, revision request,
or rejection. Nothing reaches your story files without passing through this screen.

---

## Agent Teams

| Agent | Role | Speciality |
|-------|------|------------|
| **Showrunner** | Room chair / synthesiser | Opens deliberations, frames the problem, synthesises the final recommendation |
| **Writer** | Prose and scene work | Screenplay format, scene construction, dialogue, action lines |
| **Critic** | Analytical feedback | Story logic, character consistency, structural weaknesses |
| **Editor** | Refinement | Line-level clarity, pacing, cutting what doesn't earn its place |
| **Archivist** | Knowledge management | Continuity, canon compliance, cross-reference checking |
| **Producer** | Practical oversight | Tone consistency, audience, format requirements, time/budget logic |
| **Character** | Character development | Arc, psychology, voice, relationship dynamics |
| **Structure** | Narrative architecture | Act structure, beat sheets, episode arcs, scene sequencing |
| **Logline** | High-concept pitch | One-liners, hooks, elevator pitches |
| **Treatment** | Story outlines | Scene-by-scene treatments, series outlines, pitch documents |
| **Lore** | World building | Mythology, history, rules of the world, internal consistency |

All agents are grounded in classical screenwriting methodology: McKee (*Story*), Syd Field
(*Screenplay*), Blake Snyder (*Save the Cat*), Joseph Campbell (*The Hero's Journey*).

---

## The Proposal System

StoryVaultOS enforces a strict separation between **AI suggestion** and **story canon**:

```
Task submitted
      │
      ▼
  Agent runs
      │
      ▼
 Proposal created  ──→  Review queue
      │
      ▼
  You decide:
  ┌──────────┐   ┌──────────┐   ┌──────────┐
  │ APPROVE  │   │  REVISE  │   │  REJECT  │
  │          │   │          │   │          │
  │ Written  │   │ Sent back│   │ Discarded│
  │ to disk  │   │ to agent │   │          │
  └──────────┘   └──────────┘   └──────────┘
```

Every approval is logged in the project's immutable commit history (`History/commits.json`).

---

## World Bible

The World Bible is the canonical reference document for your story world. Each of the six
sections serves a distinct purpose:

| Section | Purpose |
|---------|---------|
| **Overview** | Logline, premise, theme, genre, emotional core |
| **Lore** | History, mythology, backstory — the world before your story begins |
| **Logic** | How the world works: technology, economy, power structures, magic systems |
| **Tone** | Voice, aesthetic, cinematic references, what it feels like |
| **Story** | Prose narrative of the full story arc: acts, inciting incident, turning points, climax |
| **Rules** | Hard constraints — the things that can never happen in this world |

Agents working on the World Bible write in **descriptive prose** (not screenplay format) and
flag contradictions with existing KB documents using `⚠️ CONTRADICTION:` markers.

---

## CLI Reference

StoryVaultOS also has a full terminal interface (80s aesthetic, green on black):

```bash
# Project management
python storyvault.py new-project "MY PROJECT"   # Create a new project
python storyvault.py set-project "MY PROJECT"   # Switch active project
python storyvault.py list-projects              # List all projects

# Configuration
python storyvault.py set-key sk-...            # Save API key to config
python storyvault.py show-config               # Display current settings
python storyvault.py token-stats               # Show token usage and cost

# Scene workflow (CLI)
python storyvault.py new-scene                 # Create a scene card
python storyvault.py draft-scene scene_01      # Draft a scene with AI
python storyvault.py critique-scene scene_01   # Critique a draft
python storyvault.py revise-scene scene_01     # Revise based on critique
python storyvault.py approve-scene scene_01    # Approve and lock

# Export
python storyvault.py export                    # Export approved scenes as screenplay

# (No arguments — show interactive menu)
python storyvault.py
```

---

## Project Vault Structure

When you create a project, StoryVaultOS scaffolds this directory structure inside `StoryVault/`:

```
StoryVault/
├── config.json                         ← vault settings (gitignored)
└── Projects/
    └── MY PROJECT/
        ├── Canon/
        │   └── Canon.md                ← world rules and locked facts
        ├── Documents/
        │   ├── Characters/             ← character documents (.md)
        │   ├── Locations/
        │   ├── Creatures/
        │   ├── Objects/
        │   ├── Events/
        │   └── WorldBuilding/
        ├── WorldBible/
        │   ├── overview.md
        │   ├── lore.md
        │   ├── logic.md
        │   ├── tone.md
        │   ├── structure.md
        │   └── rules.md
        ├── Scenes/
        │   └── scene_01/
        │       ├── scene_card.md
        │       ├── draft.md
        │       ├── critique.md
        │       ├── revision.md
        │       └── meta.json
        ├── Drafts/                     ← exported screenplays
        ├── Memory/
        │   └── WorkingMemory.md        ← continuity notes
        └── History/
            ├── commits.json            ← immutable approval log
            └── proposals/              ← all generated proposals (.md + .json)
```

All story content is **plain Markdown**. You can read, edit, and version-control it with any
tool — StoryVaultOS doesn't lock you into a proprietary format.

---

## Configuration

| Setting | How to set | Default | Description |
|---------|------------|---------|-------------|
| `OPENAI_API_KEY` | `.env` file or env var | — | Required. Your OpenAI API key |
| Model | `.env`: `STORYVAULT_MODEL` or CLI `set-key` | `gpt-4o-mini` | OpenAI model to use |
| Vault path | `StoryVault/config.json` | `StoryVault/` | Where projects are stored |
| Current project | `StoryVault/config.json` or `set-project` | — | Active project name |

The `StoryVault/` directory is **gitignored** — it contains your API key and all your story
data. It lives only on your machine.

---

## System Requirements

- Python 3.11 or later
- An OpenAI API key with access to `gpt-4o-mini` (or whichever model you configure)
- A modern web browser for the UI

---

## Contributing

Contributions are welcome. Please:

1. Fork the repo and create a branch from `main`
2. Make your changes with clear commit messages
3. Open a pull request with a description of what you've changed and why
4. For significant changes, open an issue first to discuss the approach

This project follows the principle of **minimum necessary complexity** — resist the urge to
generalise prematurely. A clear, specific implementation beats a flexible abstraction every time.

---

## Licence

MIT — see [LICENSE](LICENSE).

---

## A note on API costs

StoryVaultOS uses `gpt-4o-mini` by default. At current pricing, a typical scene draft
costs roughly $0.001–$0.005 USD. A full team deliberation session costs roughly $0.01–$0.05
depending on rounds and complexity. The token tracker in PROJECTS → stats shows your
cumulative cost at all times.

You can switch to `gpt-4o` for higher-quality output at roughly 10–15× the cost, or to any
other OpenAI model by editing `StoryVault/config.json` directly.
