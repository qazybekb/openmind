# bCourses Bot 🐻💙💛

AI-powered Canvas LMS study buddy for UC Berkeley students. Built with [Nanobot](https://github.com/HKUDS/nanobot), Gemini 2.5 Pro, and Cal spirit.

## What it does

- **Assignments & Deadlines** — "What's due this week?" with urgency flags
- **Grades** — "What are my grades?" / "What do I need for an A?"
- **Readings** — Fetches, reads, and summarizes course readings from Canvas
- **Assignment Help** — Reads the prompt + rubric, gives specific guidance
- **Teach Me** — Step-by-step interactive teaching from course materials
- **Todoist Sync** — Auto-adds assignments with due dates, detects changes
- **Obsidian Knowledge Graph** — Saves reading summaries and assignment notes
- **Proactive Alerts** — Deadline reminders, new file detection, grade notifications

## Architecture

```
Telegram (@qb_bcoursesbot)
    │
    ▼
Nanobot (Docker) — Gemini 2.5 Pro
    │
    ├── Canvas API (web_fetch) — assignments, grades, files, modules
    ├── Todoist MCP — task management
    ├── Playwright + Chromium — read PDFs, external articles
    ├── Obsidian (filesystem MCP) — knowledge base
    └── DuckDuckGo — web search
```

## Setup

1. Clone this repo
2. Copy `config.example.json` to `config.json` and fill in your API keys
3. Copy workspace files (SOUL.md, USER.md, AGENTS.md, HEARTBEAT.md) to `~/.nanobot-canvas/workspace/`
4. Update USER.md with your Canvas course IDs and API token
5. Start with Docker: `docker compose up -d nanobot-canvas`

## Required API Keys

- **Gemini** — [aistudio.google.com](https://aistudio.google.com/apikey)
- **Canvas** — bCourses Settings → Approved Integrations → New Access Token
- **Todoist** — Settings → Integrations → Developer → API Token
- **Telegram Bot** — [@BotFather](https://t.me/BotFather) → /newbot

## Files

- `config.example.json` — Configuration template
- `SOUL.md` — Bot personality (Cal study buddy)
- `USER.md` — User profile, Canvas API endpoints, interaction rules
- `AGENTS.md` — Agent instructions for handling different requests
- `HEARTBEAT.md` — Automated checks (deadlines, announcements, Todoist sync)
- `Nanobot_Guide.md` — Full user guide
- `Canvas_Bot_Improvements.md` — Future improvement roadmap
- `Obsidian_bCourses_Strategy.md` — Obsidian knowledge graph strategy

## Cost

~$1-5/month on Gemini free/paid tier. Canvas, Todoist, and Telegram APIs are free.

---

*Go Bears! 🐻 Fiat Lux! 💡*
