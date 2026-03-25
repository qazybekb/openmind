# bCourses Bot — Setup Guide 🐻

AI-powered Canvas study buddy for UC Berkeley students. Runs on your laptop via Docker.

## What you need (5 min to get)

1. **Canvas API token** — bCourses → Profile → Settings → + New Access Token
2. **Telegram bot** — message [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token
3. **Gemini API key** — [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (free, no credit card)
4. **Your Telegram user ID** — message [@userinfobot](https://t.me/userinfobot) on Telegram, it replies with your ID

## Install (10 min)

### Step 1: Clone the repo

```bash
git clone https://github.com/qazybekb/bcourses_bot
cd bcourses_bot
```

### Step 2: Set up environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in your keys:

```
CANVAS_API_TOKEN=your_canvas_token_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_USER_ID=your_telegram_user_id
GEMINI_API_KEY=your_gemini_api_key
```

### Step 3: Set up config.json

```bash
cp config.example.json config.json
```

Edit `config.json` — replace all `YOUR_*` placeholders with your actual keys.

### Step 4: Find your course IDs

Run this (replace YOUR_CANVAS_TOKEN):

```bash
curl -s "https://bcourses.berkeley.edu/api/v1/courses?enrollment_state=active&per_page=50&access_token=YOUR_CANVAS_TOKEN" | python3 -c "
import sys,json
for c in json.load(sys.stdin):
    print(f'{c[\"id\"]} | {c[\"name\"]}')
"
```

### Step 5: Configure your courses

Edit `workspace/courses.json` with your course IDs:

```json
{
  "canvas_base_url": "https://bcourses.berkeley.edu/api/v1",
  "courses": {
    "1234567": "Course Nickname",
    "1234568": "Another Course"
  }
}
```

### Step 6: Set up your profile

Edit `workspace/USER.md` — update your name and school info. Course IDs are loaded from `courses.json` automatically.

### Step 7: Run it

```bash
docker compose up -d
```

### Step 8: Test it

Message your bot on Telegram:

> What's due this week?

### Step 9 (Optional): Set up Gmail

To let the bot check your email for professor messages and course updates:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or use existing) → Enable **Gmail API**
3. Go to **Credentials** → Create **OAuth 2.0 Client ID** → choose "Desktop app"
4. Download the JSON credentials file
5. Save it as `~/.gmail-mcp/gcp-oauth.keys.json`
6. Run the auth flow:

```bash
npx @shinzolabs/gmail-mcp auth
```

A browser window opens — sign in with your Berkeley Google account and approve.

The Gmail MCP server is already configured in `config.json`. Once authenticated, the bot can search and read your emails.

**Privacy note:** The bot only reads emails — it cannot send, draft, or delete anything.

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
| Check my email | Shows recent important emails |
| Any emails from professors? | Course-related email summaries |

See [CAPABILITIES.md](CAPABILITIES.md) for the full feature guide.

## Notifications (automatic)

Every 3 hours the bot checks Canvas and Gmail, and messages you ONLY if:
- ⚠️ Assignment due within 24 hours (not submitted)
- 📋 Assignment due in 2-3 days (not submitted)
- 📈📉 Grade changed since last check
- 🚨 Assignment was due but not submitted
- 📧 Important email from a professor
- 📢 Professor changed a deadline

If nothing to report — stays silent.

## Common issues

| Problem | Fix |
|---------|-----|
| Bot not responding | `docker compose restart` |
| "Gemini rate limit" | Wait a few minutes, or switch to `gemini-2.5-flash` in config |
| Wrong course matched | Update nicknames in `workspace/USER.md` and `workspace/courses.json` |
| Scripts failing | Check that `CANVAS_API_TOKEN` is set in `.env` |
| Gmail not working | Re-run `npx @shinzolabs/gmail-mcp auth` |

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
