# OpenMind — Privacy & Security

## How OpenMind works

OpenMind is a Python CLI that runs on your laptop. It connects to external services to function:

1. **bCourses** (Canvas API) — to read your assignments, grades, files, and announcements
2. **OpenRouter** — to send your messages to an LLM (Gemini, Claude, GPT-4, etc.) for processing
3. **Optional integrations** — Gmail, Slack, Google Calendar, Todoist (when you enable them)

There is no OpenMind server. But your data does leave your machine when you chat — it goes to your chosen LLM provider via OpenRouter.

## What stays on your machine

| Data | Location | Transmitted? |
|------|----------|-------------|
| API tokens (Canvas, OpenRouter, Telegram, Slack, Google) | `~/.openmind/config.json` | **Yes, but only to the service they authenticate with** — never to the LLM as prompt content |
| Student profile (major, interests, career goals) | `~/.openmind/profile.json` | **Fields are included** in every LLM request as context when present |
| Resume PDF (if imported) | Your filesystem | **Never** — only extracted text passes through LLM once |
| Heartbeat state (seen deadlines, grades) | `~/.openmind/state/*.json` | **Never** |
| Terminal command history | `~/.openmind/repl_history` | **Never** |
| Google OAuth tokens | `~/.openmind/gmail/` | **Yes, to Google APIs only** — never to the LLM as prompt content |
| Course catalog (11K courses) | Bundled in package | **Never** — searched locally |

## What goes to external services

### On every conversation turn (sent to OpenRouter → your chosen LLM):
- **System prompt** containing:
  - Berkeley personality instructions
  - Your name and course list
  - Your profile fields: level, major, school, year, expected graduation, interests, career goals, GPA goal, strengths, areas to improve, dream companies, study and learning preferences
  - Resume-extracted data: skills, experience summaries, project names (if you imported a resume)
  - Tool definitions (function names and descriptions)
  - Safety and security rules
- **Your messages** and the bot's previous responses (last 40 messages)
- **Tool results** from the current conversation (Canvas data, PDF text, web content, etc.)

### When you ask about specific services:
- **Gmail content** — fetched from Gmail API, then passed to LLM for summarization
- **Slack messages** — fetched from Slack API, then passed to LLM
- **Google Calendar events** — fetched from Google Calendar API, then passed to LLM

### Sent to bCourses (Canvas API):
- Your Canvas API token (as Bearer auth header)
- API requests for assignments, grades, files, modules, announcements

### Sent to Telegram (if enabled):
- Bot responses and heartbeat notifications
- Your Telegram messages

## What OpenMind can never do

| Action | Enforced by |
|--------|------------|
| Submit assignments | Canvas tools are read-only — no POST/PUT endpoints |
| Post discussions | No write endpoints exposed |
| Send or delete emails | Gmail OAuth scoped to `gmail.readonly` |
| Post to Slack | Slack tools use read-only API methods |
| Modify grades | No write endpoints |
| Send data to OpenMind servers | There are no OpenMind servers |

**Exception:** Google Calendar can create events (this is the only write integration).

## Security measures

| Measure | Implementation |
|---------|---------------|
| SSRF protection | `web.py` blocks localhost, private IPs, non-http schemes, and validates redirect targets |
| Path traversal | `obsidian.py` checks `is_relative_to()` before any file I/O |
| Prompt injection | System prompt declares tool results as untrusted data |
| Canvas URL validation | `config.py` allowlists `bcourses.berkeley.edu` only |
| File permissions | Config/profile/Google credential files created by OpenMind use owner-only permissions |
| Atomic writes | Config and profile use temp-file + rename |
| Token logging | No logger or print statement interpolates stored tokens |

## Deleting everything

```bash
rm -rf ~/.openmind
pip uninstall openmind
```

This removes all configuration, profile data, tokens, and state.
