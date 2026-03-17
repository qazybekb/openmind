# bCourses Bot — Quick Start 🐻

## Step 1: Get your keys (5 min)

You need 3 things:

| What | Where to get it |
|------|----------------|
| **Canvas API token** | bCourses → Profile pic → Settings → + New Access Token |
| **Telegram bot token** | Message [@BotFather](https://t.me/BotFather) → /newbot → copy token |
| **Gemini API key** | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (free) |

Also get your **Telegram user ID**: message [@userinfobot](https://t.me/userinfobot)

## Step 2: Find your course IDs (2 min)

Run this in terminal (replace YOUR_CANVAS_TOKEN):

```bash
curl -s "https://bcourses.berkeley.edu/api/v1/courses?enrollment_state=active&per_page=50&access_token=YOUR_CANVAS_TOKEN" | python3 -c "
import sys,json
for c in json.load(sys.stdin):
    print(f'{c[\"id\"]} | {c[\"name\"]}')
"
```

Save the IDs — you'll need them in Step 4.

## Step 3: Build the bot (5 min)

```bash
cd bcourses_bot
docker build -t bcourses-bot .
```

## Step 4: Create your config

Create a file at `~/.bcourses-bot/config.json`:

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
    },
    "mcp_servers": {
      "todoist": {
        "command": "npx",
        "args": ["-y", "@shayonpal/mcp-todoist"],
        "env": {
          "TODOIST_API_TOKEN": "YOUR_TODOIST_TOKEN_OR_REMOVE_THIS_BLOCK"
        }
      },
      "playwright": {
        "command": "npx",
        "args": ["-y", "@playwright/mcp@latest"]
      }
    }
  }
}
```

## Step 5: Create your USER.md

Create `~/.bcourses-bot/workspace/USER.md` — this tells the bot about YOU.

Copy the template from `workspace/USER.md` in this repo and replace:
- Your name, email
- Your course nicknames and IDs (from Step 2)
- `YOUR_CANVAS_API_TOKEN` with your actual token

## Step 6: Run it

```bash
docker run -d --name bcourses-bot \
  -v ~/.bcourses-bot:/root/.nanobot \
  --restart unless-stopped \
  bcourses-bot
```

## Step 7: Test

Message your bot on Telegram:

> What's due this week?

## Optional: Todoist

If you want assignment auto-sync with Todoist:
1. Get API token: Todoist → Settings → Integrations → Developer
2. Add it to config.json (already has placeholder)

## Optional: Obsidian

If you want a knowledge graph:
1. Create an Obsidian vault
2. Add to docker run: `-v /path/to/vault:/root/obsidian`
3. Add to config.json mcp_servers:
```json
"obsidian": {
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/root/obsidian"]
}
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Bot not responding | `docker restart bcourses-bot` |
| Gemini rate limit | Wait or switch to `gemini-2.5-flash` |
| Can't read PDFs | `docker exec bcourses-bot pip install pymupdf` |
| Wrong course | Update USER.md with correct course IDs |

## Privacy

- Everything runs locally on YOUR machine
- Canvas token stays in YOUR config file
- Only YOUR Telegram account can talk to the bot
- No data sent anywhere except Canvas API and Gemini API
