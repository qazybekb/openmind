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

### With optional integrations

```bash
pip install ".[telegram]"    # Telegram bot + background alerts
pip install ".[gmail]"       # Gmail search + read
pip install ".[all]"         # Everything
```

## Step 2: Run the setup wizard

```bash
openmind
```

On first run, the wizard launches automatically. It will ask for:

### bCourses API Token

1. Go to [bCourses](https://bcourses.berkeley.edu)
2. Click your profile picture (top-left) > **Settings**
3. Scroll to **Approved Integrations**
4. Click **+ New Access Token**
5. Give it a name like "OpenMind" and click **Generate Token**
6. Copy the token and paste it into the wizard

The wizard validates your token immediately and fetches your active courses.

### OpenRouter API Key

1. Go to [openrouter.ai/keys](https://openrouter.ai/keys)
2. Create an account (free credits available for new users)
3. Generate an API key
4. Paste it into the wizard

Then pick a model. Recommendations:

| Model | Strengths | Cost |
|-------|-----------|------|
| `google/gemini-2.5-pro` | Great all-rounder, fast | ~$0-3/month |
| `anthropic/claude-sonnet-4` | Excellent reasoning, detailed answers | ~$5-10/month |
| `openai/gpt-4o` | Fast, capable | ~$3-8/month |
| `meta-llama/llama-4-maverick` | Open source, very cheap | ~$0-1/month |

### Optional: Telegram Bot

Enables chatting via Telegram and receiving background alerts (deadlines, grade changes, submission checks) every 3 hours.

1. Open Telegram, message [@BotFather](https://t.me/BotFather)
2. Send `/newbot`, follow the prompts, copy the bot token
3. Message [@userinfobot](https://t.me/userinfobot) to get your numeric user ID
4. Paste both into the wizard

### Optional: Todoist

Enables syncing Canvas assignments as Todoist tasks with due dates.

1. Go to Todoist Settings > Integrations > Developer
2. Copy your API token
3. Paste it into the wizard

### Optional: Gmail

Enables searching and reading course-related emails from within OpenMind.

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or use existing)
3. Enable the **Gmail API**
4. Go to Credentials > Create **OAuth 2.0 Client ID** > choose "Desktop app"
5. Download the JSON credentials file
6. Provide the path to the JSON when the wizard asks

Gmail authentication happens on first use — a browser window opens for Google sign-in. This requires a terminal (won't work from Telegram).

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

- All data stays on your machine
- API tokens are stored in `~/.openmind/config.json` (local only)
- Canvas and Gmail access is read-only — OpenMind cannot submit, post, send, or modify anything
- No analytics, no tracking, no telemetry
- Delete everything: `rm -rf ~/.openmind`
