# bCourses Bot — Complete Setup Guide 🐻💙💛

Your personal AI study buddy for UC Berkeley. Connects to bCourses, reads your lectures, tracks your assignments, and talks to you like a friend on Telegram.

---

## Prerequisites

- **Docker Desktop** installed ([download here](https://www.docker.com/products/docker-desktop/))
- **Telegram** installed on your phone
- **Python 3** installed (comes with macOS)
- A UC Berkeley **bCourses** account

---

## Part 1: Get Your API Keys (5 minutes)

You need 3 keys. All are free.

### 1.1 Canvas API Token

This lets the bot read your courses, assignments, and grades.

1. Go to [bcourses.berkeley.edu](https://bcourses.berkeley.edu)
2. Click your **profile picture** (top right)
3. Click **Settings**
4. Scroll down to **Approved Integrations**
5. Click **+ New Access Token**
6. Purpose: `bCourses Bot`
7. Leave expiration blank (or set to end of semester)
8. Click **Generate Token**
9. **Copy the token immediately** — you can't see it again

Save it somewhere safe. Looks like: `1072~aBcDeFgHiJkLmNoPqRsTuVwXyZ...`

### 1.2 Telegram Bot Token

This creates your private bot on Telegram.

1. Open Telegram
2. Search for **@BotFather** and start a chat
3. Send `/newbot`
4. Choose a name: `My bCourses Bot` (display name)
5. Choose a username: `yourusername_bcourses_bot` (must end in `bot`)
6. BotFather gives you a **token** — copy it

Looks like: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`

### 1.3 Gemini API Key

This is the AI brain of your bot. Free tier gives you 50 requests/day.

1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Click **Create API Key**
3. Select any project (or create one)
4. Copy the key

Looks like: `AIzaSyABCDefGHIjklMNOpqr...`

### 1.4 Your Telegram User ID

This ensures only YOU can talk to your bot.

1. Open Telegram
2. Search for **@userinfobot** and start a chat
3. It replies with your **user ID** — a number like `123456789`
4. Copy it

---

## Part 2: Find Your Course IDs (2 minutes)

The bot needs to know your course IDs on bCourses. Run this in your terminal:

```bash
curl -s "https://bcourses.berkeley.edu/api/v1/courses?enrollment_state=active&per_page=50&access_token=PASTE_YOUR_CANVAS_TOKEN_HERE" | python3 -c "
import sys,json
for c in json.load(sys.stdin):
    print(f'{c[\"id\"]} | {c[\"name\"]}')
"
```

Replace `PASTE_YOUR_CANVAS_TOKEN_HERE` with your actual Canvas token from Step 1.1.

You'll see something like:
```
1552198 | Big Data and Development (Spring 2026)
1550426 | EW & MBA 277 - Ethical AI Business Design (Spring 2026)
1551850 | Information Law and Policy (Spring 2026)
```

Save these IDs — you need them in Part 4.

---

## Part 3: Build the Bot (5 minutes)

### 3.1 Clone the repo

```bash
git clone https://github.com/qazybekb/bcourses_bot.git
cd bcourses_bot
```

### 3.2 Build the Docker image

```bash
docker build -t bcourses-bot .
```

This takes 3-5 minutes. It installs nanobot, Chromium (for reading web pages), pymupdf (for reading PDFs), and all dependencies.

---

## Part 4: Configure Your Bot (5 minutes)

### 4.1 Create config directory

```bash
mkdir -p ~/.bcourses-bot/workspace
```

### 4.2 Create config.json

Create the file `~/.bcourses-bot/config.json` with your favorite text editor:

```bash
nano ~/.bcourses-bot/config.json
```

Paste this and fill in YOUR keys:

```json
{
  "providers": {
    "gemini": {
      "apiKey": "PASTE_YOUR_GEMINI_API_KEY"
    }
  },
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "PASTE_YOUR_TELEGRAM_BOT_TOKEN",
      "allowFrom": ["PASTE_YOUR_TELEGRAM_USER_ID"]
    }
  },
  "agents": {
    "defaults": {
      "model": "gemini-2.5-pro",
      "provider": "gemini"
    }
  },
  "gateway": {
    "heartbeat": {
      "enabled": true,
      "interval_s": 10800
    }
  },
  "tools": {
    "web": {
      "search": {
        "provider": "duckduckgo"
      }
    },
    "mcp_servers": {
      "playwright": {
        "command": "npx",
        "args": ["-y", "@playwright/mcp@latest"]
      }
    }
  }
}
```

Save and close (in nano: Ctrl+X → Y → Enter).

### 4.3 Create your USER.md

This file tells the bot about you and your courses. Copy the template:

```bash
cp workspace/USER.md ~/.bcourses-bot/workspace/USER.md
```

Now edit it:

```bash
nano ~/.bcourses-bot/workspace/USER.md
```

Replace:
- `YOUR_NAME` → your actual name
- `YOUR_EMAIL` → your Berkeley email
- `YOUR_CANVAS_API_TOKEN` → your Canvas token (appears multiple times — replace ALL)
- Update the **course table** with your actual courses from Part 2:

```markdown
| Nickname | Full Name | Course ID |
|----------|-----------|-----------|
| NLP | Natural Language Processing | 1552042 |
| Finance | Corporate Finance | 1550565 |
```

Choose short nicknames — that's how you'll refer to courses in Telegram.

Save and close.

### 4.4 Copy remaining workspace files

```bash
cp workspace/SOUL.md ~/.bcourses-bot/workspace/
cp workspace/AGENTS.md ~/.bcourses-bot/workspace/
cp workspace/HEARTBEAT.md ~/.bcourses-bot/workspace/
cp workspace/read_pdf.py ~/.bcourses-bot/workspace/
```

### 4.5 Update HEARTBEAT.md with your course IDs

```bash
nano ~/.bcourses-bot/workspace/HEARTBEAT.md
```

Replace `YOUR_CANVAS_API_TOKEN` with your actual token. Also update the course IDs in the announcement check URL — replace each `course_XXXXXX` with your actual course IDs from Part 2.

Save and close.

---

## Part 5: Run the Bot

```bash
docker run -d --name bcourses-bot \
  -v ~/.bcourses-bot:/root/.nanobot \
  --restart unless-stopped \
  bcourses-bot
```

Check if it's running:

```bash
docker logs bcourses-bot --tail 10
```

You should see:
```
Telegram bot @your_bot_name connected
Agent loop started
```

---

## Part 6: Test It

Open Telegram and message your bot. Try these:

1. **"What's due this week?"** — should show your upcoming assignments
2. **"What are my grades?"** — should show current grades
3. **"Show me files for [course nickname]"** — should list course files with download links
4. **"Teach me about [topic] from [course]"** — interactive teaching mode

If the bot responds — you're done! 🎉

---

## Optional: Add Todoist

Sync assignments to Todoist automatically.

1. Get your Todoist API token: Todoist app → Settings → Integrations → Developer
2. Edit `~/.bcourses-bot/config.json`
3. Add this inside the `mcp_servers` block:

```json
"todoist": {
  "command": "npx",
  "args": ["-y", "@shayonpal/mcp-todoist"],
  "env": {
    "TODOIST_API_TOKEN": "YOUR_TODOIST_TOKEN"
  }
}
```

4. Restart: `docker restart bcourses-bot`

---

## Optional: Add Obsidian Knowledge Graph

Save reading summaries and study notes to an Obsidian vault.

1. Create a new Obsidian vault (or use an existing one)
2. Note the vault path (e.g., `/Users/you/Documents/Berkeley`)
3. Stop the bot: `docker stop bcourses-bot && docker rm bcourses-bot`
4. Re-run with the vault mounted:

```bash
docker run -d --name bcourses-bot \
  -v ~/.bcourses-bot:/root/.nanobot \
  -v /path/to/your/obsidian/vault:/root/obsidian \
  --restart unless-stopped \
  bcourses-bot
```

5. Add to `config.json` mcp_servers:

```json
"obsidian": {
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/root/obsidian"]
}
```

6. Restart: `docker restart bcourses-bot`

---

## Common Commands

| Command | What it does |
|---------|-------------|
| `docker logs bcourses-bot --tail 20` | Check bot logs |
| `docker restart bcourses-bot` | Restart the bot |
| `docker stop bcourses-bot` | Stop the bot |
| `docker start bcourses-bot` | Start the bot again |
| `docker rm -f bcourses-bot` | Remove the bot completely |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Bot not responding on Telegram | Check `docker logs bcourses-bot --tail 20` for errors |
| "Gemini rate limit" error | Wait 1 min or switch model to `gemini-2.5-flash` in config.json |
| Bot can't find my courses | Verify course IDs in USER.md match what Part 2 showed |
| Bot says "CalNet login" for PDFs | Make sure Canvas token in USER.md is correct and not expired |
| Can't read PDFs | Run `docker exec bcourses-bot pip install pymupdf` |
| Docker build fails | Make sure Docker Desktop is running and you have internet |
| Wrong course when I say "NLP" | Update the nickname table in USER.md |
| Bot sounds robotic | It shouldn't — but if it does, restart: `docker restart bcourses-bot` |

---

## Updating the Bot

When new features are available:

```bash
cd bcourses_bot
git pull
docker build -t bcourses-bot .
docker stop bcourses-bot && docker rm bcourses-bot
docker run -d --name bcourses-bot \
  -v ~/.bcourses-bot:/root/.nanobot \
  --restart unless-stopped \
  bcourses-bot
```

Your config and workspace files are preserved — they live outside Docker.

---

## Privacy & Security

- ✅ All data stays on YOUR machine
- ✅ Canvas token stays in YOUR local config file
- ✅ Only YOUR Telegram account can message the bot
- ✅ No analytics, tracking, or telemetry
- ✅ Bot only talks to: Canvas API, Gemini API, Telegram API
- ✅ You can delete everything anytime: `docker rm -f bcourses-bot && rm -rf ~/.bcourses-bot`

---

## Cost

| Service | Cost |
|---------|------|
| Gemini 2.5 Pro | Free (50 req/day) or ~$1-3/month |
| Canvas API | Free |
| Telegram | Free |
| Docker | Free |
| **Total** | **$0-3/month** |

---

*Go Bears! 🐻 Fiat Lux! 💡*
