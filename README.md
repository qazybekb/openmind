# bCourses Bot 🐻💙💛

AI-powered Canvas LMS study buddy for UC Berkeley students. Built with [Nanobot](https://github.com/HKUDS/nanobot), Gemini 2.5 Pro, and Cal spirit.

## What it does

- **Assignments & Deadlines** — "What's due this week?" with urgency flags
- **Grades** — "What are my grades?" / "What do I need for an A?"
- **Readings** — Fetches, reads, and summarizes course readings from Canvas
- **Assignment Help** — Reads the prompt + rubric, gives specific guidance
- **Teach Me** — Step-by-step interactive teaching from course materials
- **Gmail Integration** — Check course emails, professor messages, assignment feedback
- **Todoist Sync** — Auto-adds assignments with due dates, detects changes
- **Obsidian Knowledge Graph** — Saves reading summaries and assignment notes
- **Proactive Alerts** — Deadline reminders, grade changes, submission checks, important emails

## Architecture

```
Telegram
    │
    ▼
Nanobot (Docker) — Gemini 2.5 Pro
    │
    ├── Canvas API (web_fetch) — assignments, grades, files, modules
    ├── Gmail MCP — course emails, professor messages
    ├── Todoist MCP — task management
    ├── Playwright + Chromium — read PDFs, external articles
    ├── Obsidian (filesystem MCP) — knowledge base
    └── DuckDuckGo — web search
```

## Quick Start

```bash
git clone https://github.com/qazybekb/bcourses_bot
cd bcourses_bot
cp .env.example .env         # fill in your API keys
cp config.example.json config.json  # fill in your keys here too
# edit workspace/courses.json with your course IDs
docker compose up -d
```

See [SETUP.md](SETUP.md) for detailed step-by-step instructions.

## Required API Keys

| Key | Where to get it |
|-----|----------------|
| **Canvas API token** | bCourses → Profile → Settings → + New Access Token |
| **Telegram bot token** | [@BotFather](https://t.me/BotFather) → /newbot |
| **Gemini API key** | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (free) |
| **Telegram user ID** | [@userinfobot](https://t.me/userinfobot) on Telegram |
| Todoist (optional) | Settings → Integrations → Developer → API Token |
| Gmail (optional) | Google Cloud Console → OAuth 2.0 → Gmail API |

## Project Structure

```
├── config.example.json          # Nanobot configuration template
├── .env.example                 # Environment variables template
├── docker-compose.yml           # Docker Compose service definition
├── Dockerfile                   # Container build
├── workspace/                   # Bot personality & scripts (mounted into Docker)
│   ├── SOUL.md                  # Bot personality (Cal study buddy)
│   ├── USER.md                  # User profile, Canvas API reference, rules
│   ├── AGENTS.md                # Agent instructions for handling requests
│   ├── HEARTBEAT.md             # Automated checks (deadlines, grades, email)
│   ├── courses.json             # Course IDs (single source of truth)
│   ├── check_deadlines.py       # Deadline notification script
│   ├── check_submissions.py     # Submission verification script
│   ├── grade_history.py         # Grade tracking over time
│   └── read_pdf.py              # PDF text extraction
├── qa_check.py                  # QA tool for bot response quality
├── SETUP.md                     # Detailed setup guide
├── CAPABILITIES.md              # Full feature guide
├── PLAN.md                      # Public release roadmap
├── Canvas_Bot_Improvements.md   # Feature improvement ideas
└── Obsidian_bCourses_Strategy.md # Obsidian knowledge graph strategy
```

## Cost

~$0-3/month on Gemini free/paid tier. Canvas, Todoist, Telegram, and Gmail APIs are free.

---

*Go Bears! 🐻 Fiat Lux! 💡*
