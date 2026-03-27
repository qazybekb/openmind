<p align="center">
  <img src="https://img.shields.io/badge/UC_Berkeley-003262?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMDAgMTAwIj48dGV4dCB5PSIwLjllbSIgZm9udC1zaXplPSI4NSIgeD0iNTAlIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj7wn5CrPC90ZXh0Pjwvc3ZnPg==&logoColor=white" alt="UC Berkeley" />
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/github/actions/workflow/status/qazybekb/openmind/ci.yml?branch=main&style=for-the-badge" alt="CI" />
  <img src="https://img.shields.io/badge/License-MIT-FDB515?style=for-the-badge" alt="MIT License" />
  <img src="https://img.shields.io/badge/Tools-43-22c55e?style=for-the-badge" alt="43 Tools" />
</p>

<h1 align="center">🐻 OpenMind</h1>
<p align="center"><strong>AI-powered study buddy for UC Berkeley students</strong></p>
<p align="center">Connects to bCourses. Talks like a Bear. Runs from your terminal.</p>

---

## Quick Start

```bash
pip install git+https://github.com/qazybekb/openmind.git
openmind
```

First run asks for three things — your bCourses token, a model choice, and an OpenRouter key. Then you're chatting:

```
🐻 Hey Oski! Go Bears! 💙💛

You → What's due this week?

🔥 HIGH — NLP midterm report (due Fri, 30% of grade)
📋 MED  — Social Issues writing prompt (due Mon)
📚 LOW  — Finance case reading (due next Wed)

I'd start with the NLP report — that's 30% of your grade.
You could knock out the outline at a Moffitt table tonight.
```

## What It Does

| Category | Features |
|----------|----------|
| **Academics** | Smart deadlines (priority scoring), GPA calculator, PDF summarizer, study guide + cheatsheet generator, guided Socratic tutoring |
| **Personalization** | Student profile, skill gap analysis, career-aware course recommendations |
| **Course Catalog** | 11,000+ Berkeley courses (undergrad + graduate) searchable by subject, level, keyword |
| **Campus** | Live events from events.berkeley.edu, library hours, study room booking links |
| **Integrations** | Telegram, Gmail, Google Calendar, Slack, Todoist, Obsidian |
| **Alerts** | Morning briefing (8am), deadline warnings, grade changes, email alerts, reminders, deadline change detection |

**43 tools total** — 30 always-on, 13 from optional integrations.

## How It Works

```
You (Terminal or Telegram)
    │
    ▼
OpenMind — Any LLM via OpenRouter
    │
    ├── bCourses API — assignments, grades, files, modules
    ├── Course Catalog — 11K Berkeley courses (bundled)
    ├── Campus Data — events, library hours, study rooms
    ├── Student Profile — goals, skills, resume (local)
    ├── PDF Reader — lecture slides, papers
    ├── Web Search — DuckDuckGo + article fetch
    └── Optional: Telegram, Gmail, Calendar, Slack, Todoist, Obsidian
```

## Commands

```bash
openmind                    # Start (REPL + Telegram if enabled)
openmind chat               # Terminal REPL only (no Telegram)
openmind config             # Show configuration
openmind profile            # View your student profile
openmind privacy            # What stays local vs what goes to the LLM
openmind setup              # Full setup (all settings)
openmind setup telegram     # Add Telegram alerts
openmind setup model        # Change your LLM model
```

**In-chat commands** (type these in the REPL or Telegram):

```
/learn [topic]      — Guided Socratic tutoring (uses Gemini 2.5 Pro)
/study [course]     — Generate 10-25 page study guide PDF (uses Claude Opus)
/cheatsheet [course] — Generate 2-page exam cheatsheet PDF (uses Claude Opus)
/grades             — Quick grade check
/gpa [target]       — GPA calculator with what-if
/remind [text]      — Set a reminder
/new                — Save context + start fresh
/setup [name]       — Set up integrations without leaving the chat
/help               — All commands
```

## Install

**PyPI / pipx package name (once published):** `openmind-berkeley`

**From GitHub:**
```bash
pip install git+https://github.com/qazybekb/openmind.git
```

**From a local clone:**
```bash
pip install .
```

**From PyPI (after the first public release):**
```bash
pip install openmind-berkeley
```

**Recommended for Homebrew users (after PyPI release):**
```bash
brew install pipx
pipx install openmind-berkeley
```

All integrations (Telegram, Gmail, Calendar) are included by default. No extras needed.

## Requirements

| What | Where to get it |
|------|----------------|
| Python 3.11+ | [python.org](https://python.org) |
| bCourses API token | bCourses → Profile → Settings → + New Access Token |
| OpenRouter API key | [openrouter.ai/keys](https://openrouter.ai/keys) (free credits available) |

## Personalization

OpenMind gets smarter when it knows you. Run `openmind setup profile` to add your major, year, interests, and career goals. If you later add resume-derived skills and experience to your profile, gap analysis gets more specific. Then ask:
- *"What skills am I missing for AI PM roles?"* → compares your resume to career requirements
- *"What courses should I take?"* → searches 11K courses, recommends based on your goals
- *"Help with the NLP midterm"* → connects rubric points to your experience

All profile data stays at `~/.openmind/profile.json`. Run `openmind privacy` for full details.

## Privacy

OpenMind runs locally on your laptop. There is no OpenMind server — but it does talk to external services:

| What | Where it goes |
|------|--------------|
| API tokens | **Stored locally** in `~/.openmind/config.json`, then sent only to the relevant service for authentication |
| Your profile (major, goals, skills) | **Sent to your LLM provider** (OpenRouter) as part of every conversation |
| Conversation messages | **Sent to your LLM provider** for processing |
| Canvas data (assignments, grades) | **Fetched from bCourses**, passed through LLM when you ask about it |
| Gmail/Slack content | **Fetched only when you ask**, then passed through LLM |
| Resume PDF | **Stays local** — only extracted text goes through LLM once during import |

**What OpenMind can never do:** submit assignments, post discussions, send emails, or modify any account. All external access is read-only (except Google Calendar, which can create events).

**No analytics, no tracking, no telemetry.** Delete everything: `rm -rf ~/.openmind`

Run `openmind privacy` for the full breakdown.

## Project Structure

```
src/openmind/
├── cli.py              # Entry point (5 commands + default run path)
├── setup_wizard.py     # Progressive onboarding
├── config.py           # ~/.openmind/config.json
├── universities.py     # UC Berkeley config + personality
├── personality.py      # System prompt generation
├── llm.py              # OpenRouter client + tool calling
├── repl.py             # Terminal REPL
├── bot.py              # Telegram bot (async)
├── heartbeat.py        # Background checks + notifications
├── data/
│   ├── undergraduate_courses.csv  # 6,771 courses
│   └── graduate_courses.csv       # 4,398 courses
└── tools/
    ├── canvas.py       # 13 bCourses API tools (paginated)
    ├── berkeley.py     # Campus events, library hours, study rooms
    ├── courses.py      # Course catalog search (11K courses)
    ├── profile.py      # Student profile + resume import
    ├── pdf.py          # PDF text extraction
    ├── web.py          # Web fetch + search (SSRF protected)
    ├── gmail.py        # Gmail search + read
    ├── slack.py        # Slack search + read channels
    ├── calendar.py     # Google Calendar events
    ├── todoist.py      # Task management
    └── obsidian.py     # Vault read/write/search
```

## Documentation

| Document | Description |
|----------|-------------|
| [Setup Guide](docs/SETUP.md) | Detailed installation and configuration |
| [Features](docs/FEATURES.md) | Everything you can do with OpenMind |
| [Architecture](docs/ARCHITECTURE.md) | Technical design, data flow, module reference |
| [Tools Reference](docs/TOOLS.md) | All 43 tools with parameters |
| [Privacy & Security](docs/PRIVACY.md) | What data goes where |
| [Contributing](docs/CONTRIBUTING.md) | How to add tools and features |
| [Distribution](docs/DISTRIBUTION.md) | PyPI, pipx, and release workflow |
| [Security Policy](SECURITY.md) | How to report vulnerabilities responsibly |
| [Changelog](CHANGELOG.md) | Release history and notable changes |
| [Roadmap](PLAN.md) | Berkeley knowledge base, multi-university, live feeds |

## Contributing

We welcome contributions! See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for details.

```bash
git clone https://github.com/qazybekb/openmind.git
cd openmind
pip install -e .
openmind --help
```

## License

[MIT](LICENSE) — Qazybek Beken, 2026

---

<p align="center">
  Built with 💙💛 at UC Berkeley<br/>
  <strong>Go Bears! 🐻 Fiat Lux! 💡</strong>
</p>
