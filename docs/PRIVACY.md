# OpenMind — Privacy & Security

## Data Storage

All data stays on your machine. OpenMind stores configuration and runtime state in `~/.openmind/`:

| File | Contains | Sensitive? |
|------|----------|-----------|
| `config.json` | API tokens, model choice, courses, integration settings | Yes |
| `state/deadlines.json` | Last-seen deadline urgency levels | No |
| `state/grades.json` | Last-seen grade scores (for change detection) | Mildly |
| `state/submissions.json` | IDs of recently-checked assignments | No |
| `state/announcements.json` | IDs of seen announcements | No |
| `repl_history` | Your terminal REPL command history | Mildly |
| `gmail/credentials.json` | Google OAuth client credentials | Yes |
| `gmail/token.json` | Google OAuth access/refresh token | Yes |

## What OpenMind Can Access

### bCourses (Canvas API)

OpenMind can **read**:
- Your courses, assignments, grades, modules, pages, files
- Announcements, discussion topics, syllabus
- Your submission status for assignments

OpenMind **cannot**:
- Submit assignments
- Post discussions or replies
- Upload files
- Modify grades, submissions, or any data
- Do anything that changes your bCourses account

The Canvas API token is sent only to `bcourses.berkeley.edu` via HTTPS with Bearer authentication.

### Gmail (optional)

OpenMind can **read**:
- Search your emails by query
- Read email content by message ID

OpenMind **cannot**:
- Send, draft, or delete emails
- Modify labels or settings
- Access contacts or calendar

OAuth scope is restricted to `gmail.readonly`. Tokens are stored locally.

### Todoist (optional)

OpenMind can:
- Create tasks
- List active tasks

Todoist token is sent only to `api.todoist.com` via HTTPS.

### Obsidian (optional)

OpenMind can:
- Read, write, and search markdown files in your specified vault directory

Files stay local. Path traversal outside the vault is blocked.

## External Services Contacted

| Service | Purpose | What's sent |
|---------|---------|------------|
| `bcourses.berkeley.edu` | Canvas API | Bearer token + API requests |
| `openrouter.ai` | LLM inference | API key + conversation messages + tool results |
| `api.telegram.org` | Telegram bot (optional) | Bot token + messages |
| `api.todoist.com` | Todoist (optional) | Bearer token + task data |
| `googleapis.com` | Gmail (optional) | OAuth token + search queries |
| `html.duckduckgo.com` | Web search | Search queries |
| Various web URLs | Web fetch / PDF read | Requested by LLM for readings |

## What Goes to the LLM

When you ask a question, OpenMind sends to OpenRouter:

1. The system prompt (Berkeley personality + agent instructions)
2. Your conversation history (last 40 messages)
3. Tool definitions (function names + descriptions)
4. Tool results (Canvas API responses, PDF text, web page content)

**This means your course data, grades, and assignment content pass through the LLM provider.** OpenRouter routes to the model you chose (Google, Anthropic, OpenAI, Meta, etc.). Review your chosen provider's data policies.

## What Does NOT Leave Your Machine

- Your Canvas API token (sent only to bcourses.berkeley.edu)
- Your config.json file
- Your heartbeat state files
- Your Gmail credentials
- Your Obsidian vault contents (unless the LLM requests a file to answer your question)

## Deleting Everything

```bash
rm -rf ~/.openmind
pip uninstall openmind
```

This removes all config, tokens, state, and history.

## Security Practices

- Canvas API token sent via `Authorization: Bearer` header, never in URL query parameters
- SSRF protection blocks `web_fetch` and `read_pdf` from accessing localhost, private IPs, and non-http(s) schemes
- Obsidian file operations check `is_relative_to()` to prevent path traversal
- Gmail OAuth only initiates interactive browser flow when running in a terminal (TTY check)
- Config validation ensures the app can't start with missing tokens (routes to setup wizard)
- All external HTTP requests have explicit timeouts (15-60 seconds)
- Telegram bot only responds to the configured user ID
