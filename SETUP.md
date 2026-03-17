# bCourses Bot — Setup Guide 🐻

AI-powered Canvas study buddy for UC Berkeley students. Runs on your laptop via Docker.

## What you need (5 min to get)

1. **Canvas API token** — bCourses → Profile → Settings → + New Access Token
2. **Telegram bot** — message [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token
3. **Gemini API key** — [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (free, no credit card)
4. **Your Telegram user ID** — message [@userinfobot](https://t.me/userinfobot) on Telegram, it replies with your ID

## Install (10 min)

### Step 1: Clone and build

```bash
git clone https://github.com/HKUDS/nanobot.git
cd nanobot
docker build -t bcourses-bot .
```

### Step 2: Create config directory

```bash
mkdir -p ~/.nanobot-canvas/workspace
```

### Step 3: Download bot personality files

```bash
cd ~/.nanobot-canvas/workspace
curl -sO https://raw.githubusercontent.com/qazybekb/bcourses_bot/main/SOUL.md
curl -sO https://raw.githubusercontent.com/qazybekb/bcourses_bot/main/AGENTS.md
curl -sO https://raw.githubusercontent.com/qazybekb/bcourses_bot/main/HEARTBEAT.md
```

### Step 4: Find your course IDs

Run this (replace YOUR_CANVAS_TOKEN):

```bash
curl -s "https://bcourses.berkeley.edu/api/v1/courses?enrollment_state=active&per_page=50&access_token=YOUR_CANVAS_TOKEN" | python3 -c "
import sys,json
for c in json.load(sys.stdin):
    print(f'{c[\"id\"]} | {c[\"name\"]}')
"
```

### Step 5: Create USER.md

Create `~/.nanobot-canvas/workspace/USER.md` with your info:

```markdown
# User Profile

## About Me

- **Name**: Your Name
- **Email**: your.email@berkeley.edu
- **School**: UC Berkeley
- **Timezone**: US/Pacific

## My Active Courses

| Nickname | Full Name | Course ID |
|----------|-----------|-----------|
| (short name) | (full course name) | (ID from Step 4) |
| (short name) | (full course name) | (ID from Step 4) |

When I mention a course by nickname, use the Course ID above.

## Canvas API

Base URL — ALWAYS use this format:
https://bcourses.berkeley.edu/api/v1/{endpoint}?access_token=YOUR_CANVAS_TOKEN

Add &per_page=100 for lists.

### Quick Reference

| What | Endpoint |
|------|----------|
| All upcoming | /users/self/upcoming_events |
| Course assignments | /courses/{id}/assignments?include[]=submission&order_by=due_at&per_page=100 |
| Syllabus | /courses/{id}?include[]=syllabus_body |
| Modules | /courses/{id}/modules?include[]=items&per_page=100 |
| Page content | /courses/{id}/pages/{page_url} |
| Files | /courses/{id}/files?per_page=100 |
| Announcements | /announcements?context_codes[]=course_{id} |
| Grades | /courses/{id}/enrollments?user_id=self |

## Important Rules

1. Use course IDs from the table — never fetch course list
2. Always fetch live from Canvas API
3. Flag anything due within 48 hours
4. NEVER say "of course", "one moment" — just do it
```

Replace `YOUR_CANVAS_TOKEN` with your actual Canvas API token in the file.

### Step 6: Create config.json

Create `~/.nanobot-canvas/config.json`:

```json
{
  "providers": {
    "gemini": {
      "apiKey": "YOUR_GEMINI_API_KEY"
    }
  },
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "YOUR_TELEGRAM_BOT_TOKEN",
      "allowFrom": ["YOUR_TELEGRAM_USER_ID"]
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
    }
  }
}
```

Replace all `YOUR_*` placeholders with your actual keys.

### Step 7: Run it

```bash
docker run -d --name bcourses-bot \
  -v ~/.nanobot-canvas:/root/.nanobot \
  --restart unless-stopped \
  bcourses-bot gateway
```

### Step 8: Test it

Message your bot on Telegram:

> What's due this week?

## What it can do

| Say this | Bot does this |
|----------|--------------|
| What's due this week? | Shows upcoming assignments with urgency flags |
| What are my grades? | Shows current grade per course |
| What readings for [course]? | Fetches and summarizes readings |
| Help me with [assignment] | Reads the prompt + rubric, gives guidance |
| Teach me about [topic] | Step-by-step teaching with comprehension checks |
| Quiz me on [topic] | Generates practice questions |
| Show me files for [course] | Lists course files with download links |

## Notifications (automatic)

Every 3 hours the bot checks Canvas and messages you ONLY if:
- ⚠️ Assignment due within 24 hours (not submitted)
- 📋 Assignment due in 2-3 days (not submitted)
- 📢 Professor changed a deadline
- 📄 New file uploaded

If nothing to report — stays silent.

## Common issues

| Problem | Fix |
|---------|-----|
| Bot not responding | `docker restart bcourses-bot` |
| "Gemini rate limit" | Wait a few minutes, or switch to `gemini-2.5-flash` in config |
| Wrong course matched | Update nicknames in USER.md |
| Can't read PDFs | Install pymupdf: `docker exec bcourses-bot pip install pymupdf` |

## Privacy

- All data stays on YOUR machine
- Canvas token never leaves your config file
- Bot only responds to YOUR Telegram account
- No analytics, no tracking, no cloud

## Cost

- **Gemini**: Free tier (50 requests/day) covers most usage
- **Canvas API**: Free
- **Telegram**: Free
- **Docker**: Free

---

*Go Bears! 🐻💙💛*
