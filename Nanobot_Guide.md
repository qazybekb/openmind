# Nanobot Personal AI System — User Guide

## Your Setup

You have two AI bots running in Docker on your Mac Mini:

| Bot | Telegram | Model | Purpose |
|-----|----------|-------|---------|
| **@qb_nanobot** | Main bot | GPT-4.1 | Personal assistant — email, calendar, tasks, web, notes |
| **@qb_bcoursesbot** | Canvas bot | Claude Sonnet 4.6 | UC Berkeley coursework — assignments, grades, readings |

Both bots only respond to your Telegram account. No one else can use them.

---

## Bot 1: @qb_nanobot — Personal Assistant

### Email (Berkeley Gmail: qazybek@berkeley.edu)

| What to say | What it does |
|-------------|-------------|
| "Check my email" | Scans unread emails, shows only important ones |
| "Do I have emails from McKinsey?" | Searches your inbox |
| "Draft a reply to [email]" | Writes a draft for you |

**Note:** Email labeling and notifications are handled automatically by n8n (separate system). Important emails trigger Telegram notifications with `[berkeley]` or `[personal]` prefix.

### Calendar (Google Calendar)

| What to say | What it does |
|-------------|-------------|
| "What's on my calendar today?" | Shows today's events as bullet points |
| "What's tomorrow look like?" | Tomorrow's schedule |
| "Add a meeting with John on Friday at 2pm" | Creates a calendar event |
| "Block 3 hours tomorrow afternoon for studying" | Creates a time block |

### Tasks (Todoist)

| What to say | What it does |
|-------------|-------------|
| "Add task: buy groceries" | Adds to Todoist Inbox |
| "Add task: reply to Stripe by Friday" | Adds with due date |
| "Show my tasks" | Lists your tasks |
| "What's overdue?" | Shows overdue tasks |
| "Complete [task]" | Marks task as done |

### Notes (Obsidian)

| What to say | What it does |
|-------------|-------------|
| "List my Obsidian notes" | Shows vault contents |
| "Create a note called Interview Prep" | Creates a new note |
| "What's in my [note name] note?" | Reads note content |
| "Add to my daily journal: had a great call" | Appends to a note |

### Web Search & Browsing

| What to say | What it does |
|-------------|-------------|
| "Search for best ramen near campus" | DuckDuckGo search |
| "Go to amazon.com and find USB-C hubs" | Opens browser, navigates |
| "Summarize this article: [URL]" | Fetches and summarizes |

### General

| What to say | What it does |
|-------------|-------------|
| "Help me draft a cold email to a recruiter" | Writes a draft |
| "Translate this to Russian: [text]" | Translates |
| "What time is it in Tokyo?" | Answers questions |

---

## Bot 2: @qb_bcoursesbot — Canvas Study Buddy

### Assignments & Deadlines

| What to say | What it does |
|-------------|-------------|
| "What's due this week?" | All upcoming assignments across all courses |
| "What's due for NLP?" | Specific course assignments |
| "What's due tomorrow?" | Urgent deadlines only |
| "Add all upcoming assignments to Todoist" | Bulk add with due dates |
| "Am I missing any submissions?" | Checks for unsubmitted work |

### Grades

| What to say | What it does |
|-------------|-------------|
| "What are my grades?" | Current grade for every course |
| "How am I doing in Corporate Finance?" | Specific course grade |
| "What did I get on the NLP midterm?" | Specific assignment score |
| "What do I need on the final to get an A?" | Grade calculation |

### Course Content & Readings

| What to say | What it does |
|-------------|-------------|
| "What readings for Info Law this week?" | Fetches weekly readings from Canvas |
| "Summarize the readings for Social Issues unit 8" | Reads and summarizes each reading |
| "Summarize this article: [URL]" | Opens and summarizes any linked reading |
| "What files are in Big Data?" | Lists course files |
| "Show me the syllabus for NLP" | Full syllabus |
| "What topics are covered in module 3?" | Module contents |

### Assignment Help

| What to say | What it does |
|-------------|-------------|
| "Help me with the Big Data midterm report" | Reads assignment prompt + rubric, gives guidance |
| "What's the prompt for the writing assignment?" | Fetches exact prompt from Canvas |
| "What does the rubric say about the final project?" | Shows grading criteria |
| "What format does Prof. Cheshire want?" | Checks assignment requirements |

### Study & Practice

| What to say | What it does |
|-------------|-------------|
| "Quiz me on algorithmic fairness" | Generates practice questions |
| "Prepare me for the NLP midterm" | Pulls relevant materials and creates a study plan |
| "Explain transformers from the NLP course" | Explains concepts using course materials |
| "What's the discussion topic for Social Issues?" | Shows current discussion prompt |

### Announcements

| What to say | What it does |
|-------------|-------------|
| "Any new announcements?" | Checks all courses for recent announcements |
| "What did the NLP professor announce?" | Specific course announcements |

---

## Automatic Notifications

### Email Notifications (via n8n)

Two n8n workflows run 24/7, checking both email accounts every minute:

**Berkeley Email Smart Labeler** (qazybek@berkeley.edu):
- Labels every email automatically (Jobs/Interviews, Education, Events, etc.)
- Archives unimportant emails
- Sends Telegram notification for important emails
- Creates Todoist task with due date
- Message format:
  ```
  [berkeley] Hey! Stripe wants to do a phone screen with you 🎉

  From: Jessica Chen <recruiting@stripe.com>
  Subject: Phone Screen - ML Engineer

  ✅ Added to Todoist: Reply to Stripe with availability Thu/Fri
  ```

**Personal Gmail Smart Labeler** (qazybekbeken@gmail.com):
- Same as above but for personal email
- Message prefix: `[personal]`

**What gets notified:**
- Interview invites, coding challenges, take-homes, OA links
- Professor/TA emails (Berkeley only)
- University events, CARL meetings
- Bank fraud alerts, bills due
- Anyone asking you a direct question

**What gets silently labeled (no notification):**
- Job rejections
- Application confirmations
- Newsletters, marketing
- LinkedIn invites/digests
- Job board digests

### Canvas Notifications (via heartbeat)

The Canvas bot checks bCourses every 3 hours:
- ⚠️ Assignments due within 24 hours — urgent alert
- Assignments due in 2-3 days — reminder
- New announcements that change deadlines
- Missing submissions — warning

### Todoist Reminders (via heartbeat)

The main bot checks Todoist every 3 hours:
- Tasks due in the next 2 days — reminder

---

## Course Nicknames

The Canvas bot understands these shortcuts:

| You say | It matches |
|---------|-----------|
| NLP | Natural Language Processing |
| Finance | Corporate Finance (MBA 231) |
| Info Law | Information Law and Policy |
| Social Issues | Social Issues of Information (INFO 203) |
| Big Data | Big Data and Development |
| Ethical AI | Ethical AI Business Design (EW & MBA 277) |

---

## Managing the System

### Restart bots

If a bot stops responding:

```bash
cd ~/nanobot

# Restart main bot
docker compose restart nanobot-gateway

# Restart Canvas bot
docker compose restart nanobot-canvas

# Restart both
docker compose restart

# Full restart (if something is really broken)
docker compose down && docker compose up -d
```

### Check status

```bash
# See running containers
docker compose ps

# Check logs
docker compose logs nanobot-gateway --tail 20
docker compose logs nanobot-canvas --tail 20
```

### Restart n8n (email labeling)

```bash
pkill -f "n8n"; sleep 2; n8n start &
```

### Check n8n workflows

Open http://localhost:5678 in your browser.

---

## Architecture

```
┌──────────────┐     ┌─────────────────────┐
│   Telegram    │────▶│  @qb_nanobot        │
│   (you)       │     │  Docker: GPT-4.1    │
│               │     │  Gmail, Calendar,   │
│               │     │  Todoist, Obsidian,  │
│               │     │  Playwright, Web    │
│               │     └─────────────────────┘
│               │
│               │     ┌─────────────────────┐
│               │────▶│  @qb_bcoursesbot    │
│               │     │  Docker: Sonnet 4.6 │
│               │     │  Canvas API,        │
│               │     │  Todoist, Playwright │
│               │     └─────────────────────┘
└──────────────┘
                      ┌─────────────────────┐
                      │  n8n (localhost:5678)│
                      │  Gmail triggers     │
Gmail ───────────────▶│  GPT-4.1 Mini       │───▶ Telegram + Todoist
                      │  Smart labeling     │
                      └─────────────────────┘
```

---

## Costs

| Service | Estimated monthly cost |
|---------|----------------------|
| GPT-4.1 (main bot) | $5-10 |
| Claude Sonnet 4.6 (Canvas bot) | $8-15 |
| GPT-4.1 Mini (n8n labeling) | $1-3 |
| Todoist | Free (API) |
| Google Calendar | Free (API) |
| Canvas/bCourses | Free (API) |
| **Total** | **~$15-30/month** |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Bot not responding | `docker compose restart nanobot-gateway` |
| Canvas bot not responding | `docker compose restart nanobot-canvas` |
| No email notifications | Check n8n at localhost:5678, restart if needed |
| "API limit" error | Wait a few minutes, try again |
| Wrong email labeled | Check n8n workflow prompt at localhost:5678 |
| Todoist task missing due date | Tell bot explicitly: "add with due date Friday" |
| Bot sounds robotic | Say "talk to me like a friend, not a robot" |

---

*Built with Nanobot, n8n, GPT-4.1, Claude Sonnet 4.6, and a lot of caffeine.* 🐻💙💛
