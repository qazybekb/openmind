# OpenMind — Architecture

## Overview

OpenMind is a Python CLI application that connects students to their Canvas LMS (bCourses) via an LLM with tool calling. The LLM decides which tools to call based on the student's question, OpenMind executes them, and the LLM formats the response.

```
Student (Telegram or Terminal)
    │
    ▼
┌─────────────────────────────────────────────────┐
│  OpenMind CLI                                   │
│                                                 │
│  ┌──────────┐    ┌──────────┐    ┌───────────┐ │
│  │ bot.py   │    │ repl.py  │    │ cli.py    │ │
│  │ Telegram │    │ Terminal │    │ Commands  │ │
│  └────┬─────┘    └────┬─────┘    └───────────┘ │
│       │               │                         │
│       └───────┬───────┘                         │
│               ▼                                 │
│  ┌────────────────────┐                         │
│  │ llm.py             │                         │
│  │ OpenRouter client  │                         │
│  │ Tool-calling loop  │                         │
│  └────────┬───────────┘                         │
│           │                                     │
│           ▼                                     │
│  ┌────────────────────┐                         │
│  │ tools/             │                         │
│  │ ├── canvas.py      │ ← bCourses API         │
│  │ ├── pdf.py         │ ← PDF extraction        │
│  │ ├── web.py         │ ← Web fetch + search    │
│  │ ├── gmail.py       │ ← Gmail API (optional)  │
│  │ ├── todoist.py     │ ← Todoist API (optional) │
│  │ └── obsidian.py    │ ← File system (optional) │
│  └────────────────────┘                         │
│                                                 │
│  ┌────────────────────┐                         │
│  │ heartbeat.py       │ ← Background thread     │
│  │ Deadlines, grades, │    (Telegram only)      │
│  │ submissions, anncs │                         │
│  └────────────────────┘                         │
│                                                 │
│  ┌────────────────────┐                         │
│  │ personality.py     │ ← System prompt          │
│  │ universities.py    │    (Berkeley vibe)       │
│  └────────────────────┘                         │
│                                                 │
│  Config: ~/.openmind/config.json                │
└─────────────────────────────────────────────────┘
```

## Key Design Decisions

### Tool calling over direct API construction

The LLM never constructs Canvas API URLs directly. Instead, it calls named functions like `get_upcoming_assignments` or `get_course_files`, and Python code handles the API request correctly. This eliminates URL hallucination and ensures proper authentication, pagination, and error handling.

### OpenRouter as the LLM gateway

OpenRouter provides a single OpenAI-compatible API that routes to any model (Gemini, Claude, GPT-4, Llama, etc.). Students pick their preferred model during setup. The `openai` Python SDK works out of the box since OpenRouter is API-compatible.

### Single config file

Everything lives in `~/.openmind/config.json` — tokens, model choice, courses, integration settings. No `.env` files, no dual config, no environment variables. One file, one truth.

### Optional integrations via extras

Telegram, Gmail, and their dependencies are optional pip extras. The base install is lightweight (typer, rich, httpx, openai, pymupdf). Students who don't want Telegram don't need to install `python-telegram-bot`.

### Berkeley personality baked in

The system prompt is generated dynamically from the university config in `universities.py`. It includes Berkeley-specific slang ("hella"), landmarks (Moffitt, Doe, Main Stacks), and behavioral rules (never sound like ChatGPT). This runs through `personality.py` which combines the university vibe with agent instructions.

## Data Flow

### Chat flow (REPL or Telegram)

```
1. User sends message
2. Message appended to conversation history
3. System prompt prepended (personality + agent instructions + course list)
4. History trimmed to last 40 messages (context window management)
5. Sent to OpenRouter with tool definitions
6. If LLM returns tool calls:
   a. Execute each tool (Canvas API, PDF read, web fetch, etc.)
   b. Append tool results to messages
   c. Send back to LLM for another round
   d. Repeat until LLM returns text (max 10 rounds)
7. Final text response rendered to user
```

### Heartbeat flow (Telegram only)

```
1. Background thread starts 30 seconds after bot launch
2. Every 3 hours:
   a. Check deadlines: GET /users/self/upcoming_events → filter to assignments → compare with previous state → notify on new/escalated
   b. Check submissions: GET /courses/{id}/assignments?include=submission → find recently-due unsubmitted → notify (deduplicated by course_id:assignment_id)
   c. Check grades: GET /courses/{id}/enrollments → compare scores with previous snapshot → notify on changes
   d. Check announcements: GET /announcements → filter to last 3 hours → notify on new (deduplicated by announcement ID)
3. If any notifications: send combined message to Telegram (chunked at 4000 chars)
4. All state persisted to ~/.openmind/state/*.json
```

## Module Reference

| Module | Responsibility |
|--------|---------------|
| `cli.py` | Typer CLI app. Entry point, routes to setup/REPL/bot. Validates config. |
| `setup_wizard.py` | Interactive first-run onboarding. Validates tokens, discovers courses. |
| `config.py` | Read/write `~/.openmind/config.json`. Config validation. |
| `universities.py` | UC Berkeley config (Canvas URL, personality data). |
| `personality.py` | Generates the full system prompt from university + courses + rules. |
| `llm.py` | OpenRouter client via openai SDK. Iterative tool-calling loop. |
| `repl.py` | Terminal REPL with prompt_toolkit (history, slash commands, rich rendering). |
| `bot.py` | Telegram bot with per-user conversations. Launches heartbeat thread. |
| `heartbeat.py` | Background checks for deadlines, submissions, grades, announcements. |
| `tools/__init__.py` | Tool registry. Conditionally loads tools based on config. |
| `tools/canvas.py` | 13 Canvas API tools with pagination, reusable client, error mapping. |
| `tools/pdf.py` | PDF download + text extraction via pymupdf. |
| `tools/web.py` | Web fetch + DuckDuckGo search. SSRF protection. |
| `tools/gmail.py` | Gmail search + read via Google API. OAuth flow with TTY detection. |
| `tools/todoist.py` | Todoist task creation + listing via REST API. |
| `tools/obsidian.py` | Obsidian vault read/write/search. Path traversal protection. |

## Security Model

| Concern | Mitigation |
|---------|-----------|
| Canvas token storage | Stored in `~/.openmind/config.json`, not tracked by git |
| Canvas write protection | All Canvas tools are read-only. No POST/PUT/DELETE endpoints exposed. |
| Gmail write protection | Gmail OAuth scoped to `gmail.readonly`. Tool never sends/deletes. |
| SSRF (web_fetch/read_pdf) | Blocks localhost, private IPs, non-http(s) schemes |
| Obsidian path traversal | `is_relative_to()` check prevents `../../` escapes |
| Token in URL params | All Canvas requests use `Authorization: Bearer` header |
| Gmail in headless | Interactive OAuth blocked when not on a TTY. Clear error message. |
| Config validation | Missing/corrupt config routes to setup wizard, never crashes |
| Tool execution | All tool calls wrapped in try/except. Errors returned as JSON, never raised. |

## Canvas API Pagination

Canvas returns paginated results with a `Link` header containing `rel="next"`. The `_get_paginated()` helper follows these links automatically, accumulating results up to 20 pages (2000 items). Used for assignments, modules, files, announcements, and discussion topics.

## Conversation Memory

Messages are kept in a list per user (REPL: single list; Telegram: per-user dict). Before each LLM call, the list is trimmed to the system prompt + last 40 messages to stay within context limits. No persistent conversation storage — history resets on restart.
