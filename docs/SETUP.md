# OpenMind — Setup Guide

## Prerequisites

- Python 3.11 or later
- pip (comes with Python)
- A UC Berkeley bCourses account
- An OpenRouter account (free to start)

## Step 1: Install

### From source (developers)

```bash
git clone https://github.com/qazybekb/openmind.git
cd openmind
pip install .
```

### From GitHub (users)

```bash
pip install git+https://github.com/qazybekb/openmind.git
```

All integrations (Telegram, Gmail, Calendar, Slack, Todoist, Obsidian) are included by default.

## Step 2: Run the setup wizard

```bash
openmind
```

On first run, the wizard asks for three things:

### Step 1: bCourses API Token

1. Go to [bCourses](https://bcourses.berkeley.edu)
2. Click your profile picture (top-left) > **Settings**
3. Scroll to **Approved Integrations**
4. Click **+ New Access Token**
5. Give it a name like "OpenMind" and click **Generate Token**
6. Copy the token and paste it into the wizard

The wizard validates your token immediately, greets you by name, and discovers your active courses.

### Step 2: Choose your LLM model

Pick the AI model that powers OpenMind:

1. **xiaomi/mimo-v2-pro** — reliable + affordable, $1/$3 per 1M tokens (default)
2. **anthropic/claude-sonnet-4-6** — best reasoning, $3/$15 per 1M tokens
3. **openai/gpt-5.4** — GPT ecosystem, $2.50/$15 per 1M tokens

Or type any OpenRouter model ID. You can change this later with `/setup model`.

### Step 3: OpenRouter API Key

1. Go to [openrouter.ai/keys](https://openrouter.ai/keys)
2. Create an account (free credits available for new users)
3. Generate an API key
4. Paste it into the wizard

That's it — you're chatting. OpenMind defaults to `google/gemini-2.5-pro`. Change it anytime with `openmind setup model`.

### Adding integrations later

Every integration has its own setup command. Run these whenever you're ready:

```bash
openmind setup telegram     # Telegram bot + background alerts
openmind setup gmail        # Gmail search + read
openmind setup calendar     # Google Calendar sync
openmind setup slack        # Slack channel reader
openmind setup todoist      # Todoist task sync
openmind setup obsidian     # Obsidian vault integration
openmind setup profile      # Academic profile + career goals
openmind setup model        # Change your LLM model
```

### Integration details

**Telegram:** Message @BotFather → /newbot → copy token. Message @userinfobot → get user ID. Validated during setup — invalid tokens are rejected.

**Gmail / Calendar:** Requires Google OAuth credentials (Desktop app) from Google Cloud Console. Both share the same credentials directory. Auth completes on first use via browser sign-in.

**Slack:** Requires a Slack user token (xoxp-...) from api.slack.com/apps. Read-only access to course channels.

**Todoist:** API token from Todoist Settings > Integrations > Developer.

**Obsidian:** Provide the path to your vault directory.

### Optional: Obsidian

Enables saving reading summaries, assignment outlines, and flashcards to your Obsidian vault.

1. Provide the path to your Obsidian vault (e.g., `~/Documents/Obsidian`)
2. OpenMind creates subdirectories as needed (Readings/, Assignments/, Flashcards/)

## Step 3: Use it

```bash
openmind          # Start Telegram bot (if configured) or terminal REPL
openmind chat     # Force terminal REPL
openmind config   # Show current configuration
openmind setup    # Re-run setup wizard to change settings
```

## Where config lives

All configuration is stored in `~/.openmind/`:

```
~/.openmind/
├── config.json       # All settings, tokens, courses
├── repl_history      # Terminal REPL command history
├── state/            # Heartbeat state (deadlines, grades, submissions, announcements)
│   ├── deadlines.json
│   ├── grades.json
│   ├── submissions.json
│   └── announcements.json
└── gmail/            # Gmail OAuth tokens (if enabled)
    ├── credentials.json
    └── token.json
```

## Changing your courses

If you add/drop a course mid-semester, edit `~/.openmind/config.json` and update the `"courses"` section:

```json
{
  "courses": {
    "1552198": "Big Data",
    "1550426": "Ethical AI"
  }
}
```

Or re-run `openmind setup` to auto-discover courses fresh from bCourses.

## Changing your model

Edit `~/.openmind/config.json` and change the `"model"` field:

```json
{
  "model": "anthropic/claude-sonnet-4"
}
```

Browse all available models at [openrouter.ai/models](https://openrouter.ai/models).

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `openmind: command not found` | Make sure pip's bin directory is in your PATH. Try `python -m openmind` |
| Setup wizard keeps looping | Check your bCourses token hasn't expired. Generate a new one. |
| "Canvas token is invalid or expired" | Generate a new token in bCourses Settings |
| "Canvas rate limit hit" | Wait 1-2 minutes and try again |
| Telegram bot not responding | Check bot token and user ID. Run `openmind setup` to reconfigure |
| Gmail "not ready" error | Run `openmind chat` (needs terminal for browser auth), or delete `~/.openmind/gmail/token.json` and re-auth |
| No courses found during setup | Some courses may not be "active" yet. Add course IDs manually to config.json |
| pymupdf errors | Run `pip install pymupdf` to reinstall |

## Privacy

- OpenMind runs on your machine, but chat data goes to OpenRouter for LLM responses
- API tokens are stored in `~/.openmind/config.json` and sent only to the service they authenticate with
- Canvas, Gmail, and Slack access are read-only — OpenMind cannot submit, post, send, or modify them
- Google Calendar is the one write integration: it can create calendar events when you ask
- No analytics, no tracking, no telemetry
- Delete everything: `rm -rf ~/.openmind`
