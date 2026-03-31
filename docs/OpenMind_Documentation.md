# OpenMind — Comprehensive Documentation

**AI Study Buddy + Personal Time Manager for UC Berkeley**

Version 1.0.0 | March 2026

---

## Table of Contents

1. [Overview](#1-overview)
2. [Installation](#2-installation)
3. [First-Run Setup](#3-first-run-setup)
4. [Models](#4-models)
5. [CLI Commands](#5-cli-commands)
6. [Telegram Bot](#6-telegram-bot)
7. [Integrations](#7-integrations)
8. [Tools Reference (43 Tools)](#8-tools-reference)
9. [Features](#9-features)
10. [Time & Task Management](#10-time--task-management)
11. [Guided Learning](#11-guided-learning)
12. [Study Guide & Cheatsheet Generator](#12-study-guide--cheatsheet-generator)
13. [Background Alerts](#13-background-alerts)
14. [Privacy & Security](#14-privacy--security)
15. [Architecture](#15-architecture)
16. [Testing Guide](#16-testing-guide)
17. [Troubleshooting](#17-troubleshooting)

---

## 1. Overview

OpenMind is a pip-installable Python CLI tool that serves as an AI-powered study buddy and personal time manager for UC Berkeley students. It connects to bCourses (Canvas LMS), reads your courses, assignments, and grades, and provides personalized study advice through a terminal REPL and Telegram bot.

### Key capabilities

- **43 AI tools** (30 core + 13 optional integrations)
- **Canvas LMS integration** — read-only access to courses, assignments, grades, announcements
- **Telegram bot** — chat from your phone with push notifications
- **Time management** — auto-sync deadlines to Todoist + Google Calendar
- **Guided learning** — Socratic tutoring from your actual course materials
- **Study guide generator** — 10-25 page PDFs powered by Claude Opus
- **Morning briefing** — daily 8am summary via Telegram
- **Berkeley personality** — talks like a Cal student, references campus locations

### Tech stack

- Python 3.11+
- OpenRouter API (any LLM — MiMo, Claude, GPT, Gemini)
- Canvas LMS API (bCourses)
- python-telegram-bot (Telegram)
- Google APIs (Gmail, Calendar)
- Rich + prompt-toolkit (terminal UI)
- pymupdf (PDF reading)
- pdflatex (PDF generation)

---

## 2. Installation

### Requirements

- Python 3.11 or higher
- pip
- macOS, Linux, or WSL

### Install

```bash
pip install git+https://github.com/qazybekb/openmind.git
```

All dependencies are included — no extras needed. This installs:

| Package | Purpose |
|---------|---------|
| typer | CLI framework |
| rich | Terminal UI (panels, tables, markdown) |
| prompt-toolkit | REPL with history and autocomplete |
| openai | OpenRouter LLM client |
| httpx | HTTP requests |
| pymupdf | PDF reading |
| python-telegram-bot | Telegram bot |
| google-auth-oauthlib | Gmail/Calendar OAuth |
| google-api-python-client | Gmail/Calendar API |

### Verify installation

```bash
openmind --version
```

---

## 3. First-Run Setup

Running `openmind` for the first time starts a 3-step setup wizard:

### Step 1: Connect to bCourses

1. Go to bcourses.berkeley.edu
2. Click your profile icon (top-left) → Settings → + New Access Token
3. Name it "OpenMind", generate, and paste the token

The wizard validates the token and shows your courses.

### Step 2: Choose your LLM model

```
1  xiaomi/mimo-v2-pro           — reliable + affordable, $1/$3 per 1M (default)
2  anthropic/claude-sonnet-4-6  — best reasoning, $3/$15 per 1M
3  openai/gpt-5.4              — GPT ecosystem, $2.50/$15 per 1M
4  google/gemini-2.5-pro       — 1M context, strong Canvas analysis, $1.25/$10 per 1M
```

You can change this later with `/setup model`.

### Step 3: Connect OpenRouter

1. Go to openrouter.ai/keys
2. Create an account (free credits available)
3. Generate an API key and paste it

After setup, you'll see a welcome message with all available integrations.

### Detailed setup guides

Available at openmindbot.io/guides:
- bCourses token
- OpenRouter API key
- Telegram bot
- Gmail
- Google Calendar
- Slack

---

## 4. Models

### Chat model (user's choice)

The student picks their model during setup. It handles everything — Canvas queries, chat, tools, learning.

| Model | Cost (in/out per 1M) | Context | Best for |
|-------|---------------------|---------|----------|
| xiaomi/mimo-v2-pro | $1 / $3 | 1M | Default — reliable, affordable |
| anthropic/claude-sonnet-4-6 | $3 / $15 | 1M | Deep reasoning |
| openai/gpt-5.4 | $2.50 / $15 | 1M | GPT ecosystem |
| google/gemini-2.5-pro | $1.25 / $10 | 1M | Strong Canvas analysis |

### Study guide model (automatic)

Claude Opus (anthropic/claude-opus-4-6) is used automatically for `/study` and `/cheatsheet` PDF generation. Students don't configure this.

### Changing models

```
/setup model
```

---

## 5. CLI Commands

### Terminal commands

```bash
openmind              # Start (REPL + Telegram if enabled)
openmind chat         # Terminal REPL only (no Telegram)
openmind config       # Show configuration
openmind profile      # View student profile
openmind privacy      # What stays local vs what goes to the LLM
openmind setup        # Full setup wizard
openmind setup <name> # Set up a specific integration
```

### In-chat slash commands

Type `/` to see the autocomplete menu.

#### Learning
| Command | Description |
|---------|-------------|
| `/learn [topic]` | Guided Socratic tutoring |
| `/study [course]` | Generate 10-25 page study guide PDF |
| `/cheatsheet [course]` | Generate 2-page exam cheatsheet PDF |

#### Academics
| Command | Description |
|---------|-------------|
| `/grades` | Quick grade check across all courses |
| `/gpa [target]` | GPA calculator (e.g., `/gpa 3.5` for what-if) |
| `/courses` | List enrolled courses |
| `/plan [scope]` | Create a study plan with time blocks |
| `/sync` | Sync Canvas deadlines to Todoist |
| `/remind [text]` | Set a reminder |

#### Session
| Command | Description |
|---------|-------------|
| `/new` | Save conversation context + start fresh |
| `/clear` | Clear conversation history |
| `/setup [name]` | Set up integrations without leaving chat |
| `/config` | Show config path |
| `/restart` | Restart OpenMind |
| `/quit` or `/exit` | Exit |

---

## 6. Telegram Bot

### Setup

```
/setup telegram
```

Requires:
1. Bot token from @BotFather on Telegram
2. Your user ID from @userinfobot

### How it works

- OpenMind runs the bot in a background thread while the REPL stays in the foreground
- Both work simultaneously
- The bot sends a welcome message with quick-action buttons on startup

### Telegram commands

All REPL commands work in Telegram:
`/start`, `/help`, `/menu`, `/learn`, `/grades`, `/gpa`, `/study`, `/cheatsheet`, `/plan`, `/sync`, `/courses`, `/remind`, `/new`, `/clear`, `/setup`

### Quick-action buttons

After `/start` and after every response:

```
[Deadlines] [Grades] [GPA]
[Learn] [Study Plan] [Announcements]
```

### Features

- **Streaming responses** — placeholder message edited in real-time as tokens arrive
- **Typing indicator** — "typing..." shown while processing
- **PDF support** — send a PDF to get it summarized; generated PDFs are sent back as documents
- **Markdown rendering** — with automatic sanitization for Telegram's parser

---

## 7. Integrations

All integrations are set up via `/setup <name>` (in chat) or `openmind setup <name>` (terminal).

### Required

| Integration | Setup | Access |
|-------------|-------|--------|
| **bCourses** | Canvas access token | Read-only |
| **OpenRouter** | API key | LLM requests |

### Optional

| Integration | Setup | Access | What it does |
|-------------|-------|--------|-------------|
| **Telegram** | Bot token + user ID | Read/Write | Chat + notifications |
| **Gmail** | Google OAuth credentials.json | Read-only | Search professor emails |
| **Google Calendar** | Google OAuth (shared with Gmail) | Read/Write | Sync deadlines, add events |
| **Slack** | User OAuth token (xoxp-...) | Read-only | Search course channels |
| **Todoist** | API token | Read/Write | Sync tasks |
| **Obsidian** | Vault path | Local write | Save notes |
| **Profile** | In-chat or setup wizard | Local | Major, goals, resume |

---

## 8. Tools Reference

### 43 tools total (30 core + 13 optional)

#### Canvas (13 tools — always available)

| Tool | What it does |
|------|-------------|
| `get_upcoming_assignments` | All upcoming deadlines across courses |
| `get_course_assignments` | Assignments for a specific course (with UPCOMING_DEADLINES) |
| `get_assignment_details` | Full details for one assignment |
| `get_grades` | Grades for a specific course |
| `get_all_grades` | Grades across all courses |
| `get_assignment_groups` | Grade weights per category |
| `get_modules` | Course modules |
| `get_page_content` | Module page content |
| `get_course_files` | Files in a course |
| `get_announcements` | Recent announcements |
| `get_syllabus` | Course syllabus |
| `get_discussion_topics` | Discussion topics |
| `get_upcoming_events` | Calendar events |

#### Berkeley Campus (3 tools)

| Tool | What it does |
|------|-------------|
| `berkeley_events` | Live events from events.berkeley.edu |
| `berkeley_library_hours` | Library hours |
| `berkeley_study_rooms` | Study room booking links |

#### Course Catalog (1 tool)

| Tool | What it does |
|------|-------------|
| `berkeley_course_search` | Search 11,169 Berkeley courses |

#### GPA Calculator (1 tool)

| Tool | What it does |
|------|-------------|
| `gpa_calculator` | Estimate GPA with what-if analysis |

#### Profile (3 tools)

| Tool | What it does |
|------|-------------|
| `get_profile` | Read student profile |
| `update_profile` | Update profile fields (allowlisted) |
| `import_resume` | Import skills from resume |

#### Study Guide & Cheatsheet (2 tools)

| Tool | What it does |
|------|-------------|
| `generate_study_guide` | 10-25 page PDF (Claude Opus) |
| `generate_cheatsheet` | 2-page exam reference PDF (Claude Opus) |

#### Reminders (2 tools)

| Tool | What it does |
|------|-------------|
| `remind_me` | Set a reminder with due date |
| `list_reminders` | List pending reminders |

#### Web & PDF (3 tools)

| Tool | What it does |
|------|-------------|
| `web_fetch` | Fetch a web page (SSRF protected) |
| `web_search` | Search DuckDuckGo |
| `read_pdf` | Read a PDF from URL |

#### Optional: Gmail (2 tools)

| Tool | What it does |
|------|-------------|
| `gmail_search` | Search emails |
| `gmail_read` | Read an email |

#### Optional: Slack (3 tools)

| Tool | What it does |
|------|-------------|
| `slack_search` | Search messages |
| `slack_read_channel` | Read channel history |
| `slack_list_channels` | List channels |

#### Optional: Google Calendar (3 tools)

| Tool | What it does |
|------|-------------|
| `calendar_list_events` | List upcoming events |
| `calendar_add_event` | Create an event |
| `calendar_add_deadlines` | Bulk-add Canvas deadlines |

#### Optional: Todoist (2 tools)

| Tool | What it does |
|------|-------------|
| `todoist_add_task` | Create a task |
| `todoist_list_tasks` | List tasks |

#### Optional: Obsidian (3 tools)

| Tool | What it does |
|------|-------------|
| `obsidian_read` | Read a note |
| `obsidian_write` | Write/update a note |
| `obsidian_search` | Search notes |

---

## 9. Features

### Smart deadlines
- Sorted by urgency x grade weight
- Deadline change detection (alerts when professors move dates)
- Course names included in notifications

### GPA calculator
- Estimates current GPA from Canvas grades
- What-if analysis: "what do I need on the final for a 3.5?"
- Disclaimer: estimates only, check CalCentral for official GPA

### Personalization
- Student profile: major, year, interests, career goals
- Resume import: skill extraction + skill-gap analysis
- Tailored course recommendations

### Memory
- Conversation context preserved across sessions via memory.json
- `/new` saves current context before clearing

### Berkeley personality
- Campus references: Moffitt, Doe, Main Stacks, FSM Cafe, Top Dog
- Varied spirit phrases: "Fiat Lux!", "Sko Bears!", "Go Bears!"
- Says "Cal" not "UC Berkeley", "GSI" not "TA"
- Acknowledges the grind: "Berkeley's hard. That's not a you problem"

---

## 10. Time & Task Management

### Auto-sync (background)

Every 3 hours, the heartbeat automatically:
- **Canvas → Todoist**: Creates tasks for all unsubmitted deadlines
- **Canvas → Calendar**: Creates all-day events for assignments worth 5+ points (with 1-day and 1-hour reminders)
- Deduped — won't create duplicates

### /plan command

Creates a study plan by:
1. Checking all deadlines (Canvas + Todoist)
2. Estimating time per task (quiz 30min, essay 4-8h, final 10-20h)
3. Checking Google Calendar for free time
4. Creating day-by-day time blocks with Berkeley locations
5. Offering to add blocks to Calendar + tasks to Todoist

### /sync command

Manually triggers Canvas → Todoist sync for all upcoming deadlines.

### Proactive task creation

The LLM suggests adding Todoist tasks when it sees:
- New assignments with due dates
- Actionable emails
- Student requests ("I need to...")

---

## 11. Guided Learning

### How it works

Type `/learn [topic]` or naturally say "teach me about X", "help me understand Y".

### 5-phase Socratic method

1. **Diagnose** — "What do you already know about [topic]?"
2. **Teach one concept** — analogy + worked example from course materials
3. **Check understanding** — scenario question (never yes/no)
4. **Respond adaptively** — correct→extend, partial→probe, wrong→hint ladder
5. **Consolidate** — "Explain in your own words"

### Hint ladder (for wrong answers)

1. Self-monitoring: "What do you notice about...?"
2. Reveal constraint: "Remember that [rule]..."
3. Worked example: "Let me show a simpler case..."
4. Direct guidance: "The key insight is..." (last resort)

---

## 12. Study Guide & Cheatsheet Generator

### Study Guide (`/study [course]`)

- 10-25 page two-column LaTeX PDF
- Powered by Claude Opus
- Teaches from scratch — not a cheatsheet
- Structure adapts to subject (law vs CS vs business vs science)
- Reads actual course materials from Canvas first

### Cheatsheet (`/cheatsheet [course]`)

- 2-page ultra-dense exam reference
- 7pt font, two-column, tight margins
- Maximum information density
- Designed for open-note exams

### Requirements

- pdflatex installed (`brew install --cask basictex` on macOS)
- Output saved to `~/.openmind/study_guides/`

---

## 13. Background Alerts

### Morning briefing (8am PT daily)

Sent via Telegram:
- Today's deadlines
- This week's deadlines
- Grades needing attention (below 80%)
- Unread Berkeley email count

### Heartbeat (every 3 hours via Canvas, hourly for reminders)

| Alert | Trigger |
|-------|---------|
| Deadline urgency | Assignment due within 7 days |
| Deadline change | Professor moved a due date |
| Grade change | Score went up or down |
| Unsubmitted assignment | Due in last 24 hours, not submitted |
| New announcement | Posted in last 3 hours |
| New Berkeley email | Unread from @berkeley.edu |
| Reminder due | Student-set reminder past due time |

### Notification format

```
Deadline update 🐻
📚 Info Law & Policy — Lab 2 (Submit) (due Mar 31, 3d)
📚 NLP — Midterm report (due Apr 01, 4d)
📚 Big Data — 4. Midterm report (due Apr 02, 5d)
```

---

## 14. Privacy & Security

### Data storage

| Data | Location | Sent to LLM? |
|------|----------|--------------|
| Config (API tokens) | ~/.openmind/config.json | Never |
| Student profile | ~/.openmind/profile.json | Yes (for personalization) |
| Conversation memory | ~/.openmind/memory.json | Summaries in system prompt |
| Reminders | ~/.openmind/reminders.json | Never |
| Heartbeat state | ~/.openmind/state/*.json | Never |
| Study guides | ~/.openmind/study_guides/*.pdf | Never |
| REPL history | ~/.openmind/repl_history | Never |
| Gmail OAuth tokens | ~/.openmind/gmail/ | To Google APIs only |
| Resume PDF | Original file | Never uploaded |

### Security measures

- **SSRF protection**: fail-closed DNS, private IP blocking, redirect validation
- **Canvas HTTPS enforcement**: rejects http:// URLs
- **Per-turn tool authorization**: prevents prompt injection from tool results
- **Profile field allowlist**: only 15 specific fields can be written
- **Prompt secrecy**: system instructions never revealed
- **Atomic file writes**: tempfile + rename prevents corruption
- **File permissions**: sensitive files created with 0600

### What's sent to the LLM

- Your messages and the bot's responses
- Course list and profile fields (for personalization)
- Canvas data fetched during conversation
- Gmail/Slack/Calendar content when you ask about it

### What's NEVER sent

- API tokens (sent only to their own service)
- Raw resume PDF file
- Heartbeat state files
- Terminal command history

### Delete everything

```bash
rm -rf ~/.openmind
pip uninstall openmind-berkeley
```

---

## 15. Architecture

### Module structure

```
src/openmind/
├── cli.py              # Typer CLI entry point
├── repl.py             # Terminal REPL with prompt-toolkit
├── bot.py              # Telegram bot (TelegramBotService)
├── llm.py              # OpenRouter LLM client + tool execution
├── personality.py       # System prompt (persona + playbooks + policy)
├── universities.py      # Berkeley config + spirit phrases
├── config.py           # Config management + validation
├── memory.py           # Conversation memory persistence
├── heartbeat.py         # Background alerts + auto-sync
├── banner.py           # ASCII art banner
├── tools/
│   ├── __init__.py     # Tool registry + dispatch
│   ├── canvas.py       # 13 Canvas API tools
│   ├── berkeley.py     # Campus events, library, study rooms
│   ├── courses.py      # 11K course catalog search
│   ├── gpa.py          # GPA calculator
│   ├── profile.py      # Student profile management
│   ├── studyguide.py   # PDF generation (Opus)
│   ├── reminders.py    # Reminder scheduling
│   ├── gmail.py        # Gmail integration
│   ├── calendar.py     # Google Calendar
│   ├── slack.py        # Slack integration
│   ├── todoist.py      # Todoist integration
│   ├── obsidian.py     # Obsidian vault
│   ├── web.py          # Web fetch + search (SSRF protected)
│   └── pdf.py          # PDF reading
```

### System prompt layers

1. **Persona** — Berkeley voice and personality
2. **Context** — Student name, courses, profile, current date/time
3. **Playbooks** — Task-specific instructions (deadlines, learning, planning, etc.)
4. **Policy** — Security rules, read-only enforcement, prompt secrecy
5. **Memory** — Prior conversation context

### Multi-model architecture

| Component | Model |
|-----------|-------|
| Chat + Canvas + Tools | Student's choice (MiMo default) |
| Study guides + Cheatsheets | Claude Opus (automatic) |

---

## 16. Testing Guide

### Automated tests

```bash
# Run all 22 tests
python -m pytest tests/ -v

# Run specific test files
python -m pytest tests/test_cli_and_setup.py
python -m pytest tests/test_release_contract.py
python -m pytest tests/test_heartbeat_runtime.py
```

### Lint

```bash
python -m ruff check src/
```

### Manual testing checklist

#### First-run experience
- [ ] `pip install git+https://github.com/qazybekb/openmind.git`
- [ ] Run `openmind` — setup wizard starts
- [ ] Enter bCourses token — courses discovered
- [ ] Choose model — 4 options with prices shown
- [ ] Enter OpenRouter key — validates OK
- [ ] Welcome message shows all integrations
- [ ] Banner, spirit phrase, and tips display correctly

#### REPL
- [ ] Type `/` — autocomplete menu appears
- [ ] "What's due?" — shows deadlines with course names
- [ ] "How are my grades?" — shows all course grades
- [ ] `/gpa` — estimates GPA
- [ ] `/gpa 3.5` — what-if analysis
- [ ] `/learn [topic]` — Socratic tutoring starts
- [ ] `/plan` — creates study plan with time blocks
- [ ] `/sync` — syncs Canvas → Todoist
- [ ] `/setup telegram` — inline setup works
- [ ] `/setup model` — model changes immediately
- [ ] `/new` — saves context, clears conversation
- [ ] `/restart` — restarts the process
- [ ] Ctrl+C during response — cancels cleanly
- [ ] `/quit` — exits with "Go Bears!"
- [ ] Response metadata shows (time + model + tool count)
- [ ] Tool progress spinner updates ("Checking deadlines...")

#### Telegram
- [ ] Welcome message with buttons on startup
- [ ] /start — greeting with buttons
- [ ] /help — full command list
- [ ] Tap Deadlines button — shows deadlines
- [ ] Type "Hi" — streaming response with placeholder editing
- [ ] Send a PDF — extracted and summarized
- [ ] /study [course] — generates and sends PDF
- [ ] /plan — creates study plan
- [ ] /sync — syncs to Todoist
- [ ] /setup — redirects to terminal
- [ ] Unauthorized user gets "private bot" message

#### Canvas accuracy
- [ ] "What's due?" catches ALL upcoming deadlines (including Big Data)
- [ ] Grades are accurate across all courses
- [ ] Announcements show recent posts
- [ ] Course files are listed
- [ ] Assignment details include descriptions

#### Time management
- [ ] /sync creates Todoist tasks for all deadlines
- [ ] Background auto-sync creates Calendar events (5+ point assignments)
- [ ] Calendar events have reminders (1 day + 1 hour)
- [ ] /plan checks Calendar for free time
- [ ] No duplicate tasks/events on repeated sync

#### Error handling
- [ ] Wrong bCourses token — helpful error + retry
- [ ] Wrong OpenRouter key — "check at openrouter.ai/keys"
- [ ] Out of credits — "top up at openrouter.ai/credits"
- [ ] Network timeout — actionable error message
- [ ] Canvas 500 error — graceful partial results

---

## 17. Troubleshooting

### "openmind: command not found"

```bash
pip install git+https://github.com/qazybekb/openmind.git
```

### Telegram bot not responding

1. Make sure `openmind` is running in a terminal
2. Only ONE instance should run at a time
3. Check: `ps aux | grep openmind`
4. Kill all and restart: `pkill -f openmind && openmind`

### "Failed to parse Canvas timestamp: None"

This is a debug-level log, not an error. Canvas returns null timestamps for some assignments. Harmless.

### Study guide fails ("pdflatex not installed")

```bash
# macOS
brew install --cask basictex
sudo /Library/TeX/texbin/tlmgr install enumitem titlesec

# Linux
sudo apt install texlive
```

### OAuth browser window pops up

Normal for first-time Gmail or Calendar use. Authorize once and it won't ask again.

### Reset everything

```bash
rm -rf ~/.openmind
openmind   # Starts fresh setup
```

### Change model

```
/setup model
```

### Update to latest version

```bash
pip install git+https://github.com/qazybekb/openmind.git --force-reinstall --no-deps
```

---

**Built at UC Berkeley School of Information**

Go Bears! 🐻

Website: openmindbot.io | GitHub: github.com/qazybekb/openmind
