# OpenMind — Roadmap

## Current State (v0.1.0)

CLI tool installable via `pip install .`. Setup wizard, bCourses integration, OpenRouter LLM, Telegram bot, terminal REPL. Optional Gmail, Todoist, Obsidian integrations. Berkeley personality.

---

## Phase 1: Berkeley Knowledge Base

Turn OpenMind from "course tool" into "Berkeley companion."

### Architecture

Bundled markdown files shipped with the package. One new tool (`berkeley_info`) searches filenames + content and returns relevant sections. Zero external dependencies, works offline.

```
src/openmind/knowledge/
├── campus/
│   ├── history.md          # Founding, Free Speech Movement, Nobel laureates
│   ├── landmarks.md        # Sather Gate, Campanile, Doe, Moffitt, Memorial Glade
│   ├── libraries.md        # Doe, Moffitt, Main Stacks, Bancroft, Music Library
│   ├── dining.md           # Croads, Foothill, Asian Ghetto, Top Dog, Cheese Board
│   └── housing.md          # Units 1-3, Clark Kerr, off-campus areas
├── safety/
│   ├── safewalk.md         # Hours, phone number, how to request
│   ├── night_shuttle.md    # Routes, schedule, BearWalk
│   ├── emergency.md        # UCPD, WarnMe alerts, active shooter protocol
│   └── seismic.md          # Earthquake procedures
├── health/
│   ├── insurance.md        # SHIP/Wellfleet, waiver process, coverage
│   ├── tang_center.md      # UHS, appointments, urgent care
│   └── mental_health.md    # Counseling, crisis line, Let's Talk drop-in
├── academics/
│   ├── schools.md          # L&S, CoE, Haas, iSchool, Law, etc.
│   ├── calendar.md         # Semester dates, dead week, RRR week, finals
│   ├── grading.md          # GPA scale, P/NP deadlines, grade disputes
│   └── advising.md         # L&S advisors, major declaration, Phase 1/2
├── transit/
│   ├── bart.md             # BayPass, stations, SF/Oakland trips
│   ├── buses.md            # AC Transit, Bear Transit, campus shuttles
│   └── biking.md           # Bay Wheels, bike theft prevention
├── student_life/
│   ├── events.md           # Big Game, Cal Day, Noon Concert, Sproul
│   ├── clubs.md            # How to join, CODEBASE, data science, ASUC
│   ├── rec_sports.md       # RSF, intramurals, outdoor adventures
│   └── traditions.md       # 4.0 Hill, Big C hike, card stunts, Oski
└── local/
    ├── telegraph.md        # Telegraph Ave, shops, vibes
    ├── neighborhoods.md    # Northside, Southside, downtown, Gourmet Ghetto
    └── hidden_gems.md      # Best study spots, secret views, cheap eats
```

### Implementation

1. Create `src/openmind/tools/berkeley.py` with a `berkeley_info(query)` tool
2. Tool searches filenames and content via simple keyword matching
3. Returns the matching section(s) for the LLM to use in its response
4. Knowledge files are installed with the package via `pyproject.toml` package data
5. Add to tool registry (conditionally always-on since it's Berkeley-specific)

### Community contribution

Knowledge files are markdown — students can PR new tips, corrections, hidden gems. Could be a growth vector on r/berkeley.

---

## Phase 2: Slack & Google Calendar Integrations

### Slack (read-only, like Gmail)

Student provides their Slack user token from a course workspace (e.g., iSchool Slack). OpenMind can search and read messages but never post.

**How it works:**
- Student gets a Slack user OAuth token (xoxp-...) with `channels:history`, `channels:read`, `search:read` scopes
- Token stored in `~/.openmind/config.json` alongside other integrations
- Two tools: `slack_search(query)` and `slack_read_channel(channel, limit)`

**Example interactions:**
```
You → "What did the TA say about the midterm in Slack?"
🐻 → Found 2 messages in #nlp-announcements:
      Prof. Bamman (Mon): "Midterm report deadline extended to Apr 4"
      TA Sarah (Tue): "Office hours moved to Wed 3pm this week"

You → "Any Slack messages about the final project?"
🐻 → 3 results across #info-law and #big-data...
```

**Setup flow:**
1. `openmind setup` asks "Enable Slack?" (y/n)
2. Student provides workspace token
3. Optionally lists channels to watch

**Tools:**
- `slack_search(query)` — search messages across accessible channels
- `slack_read_channel(channel, limit)` — read recent messages from a specific channel
- `slack_list_channels()` — list channels the user has access to

**API:** Slack Web API (`https://slack.com/api/`)
- `search.messages` — search
- `conversations.list` — list channels
- `conversations.history` — read channel messages

**Security:** Read-only. Never post, react, or modify anything. Token stored locally.

### Google Calendar

Auto-create calendar events from Canvas deadlines and block study time.

**How it works:**
- Google OAuth (same flow as Gmail) with `calendar.events` scope
- Two tools: `calendar_add_event(title, start, end)` and `calendar_list_events(days)`
- Heartbeat can auto-add new Canvas deadlines as calendar events

**Example interactions:**
```
You → "Add my deadlines to Google Calendar"
🐻 → Added 3 events:
      📅 NLP midterm report — Mar 28
      📅 Social Issues writing prompt — Mar 31
      📅 Big Data case analysis — Apr 2

You → "Block 2 hours tomorrow for the midterm"
🐻 → Added: "Study: NLP midterm report" tomorrow 2pm-4pm

You → "What's on my calendar this week?"
🐻 → You've got 4 things...
```

**Setup flow:**
1. `openmind setup` asks "Enable Google Calendar?" (y/n)
2. Uses same Google OAuth credentials as Gmail (adds `calendar` scope)
3. Or separate OAuth if Gmail isn't enabled

**Tools:**
- `calendar_add_event(title, date, duration)` — create an event
- `calendar_list_events(days_ahead)` — list upcoming events
- `calendar_add_deadlines()` — bulk-add Canvas deadlines as events

**API:** Google Calendar API v3
- `events.insert` — create events
- `events.list` — list events

**Note:** Unlike Canvas/Gmail/Slack, Calendar is READ-WRITE. The tools can create events. This should be clearly documented and the LLM should confirm before bulk-adding.

---

## Phase 3: Live Berkeley Data Feeds

Layer real-time Berkeley data on top of the static knowledge base.

### Potential feeds

| Feed | Source | Value |
|------|--------|-------|
| Berkeley events | cal.berkeley.edu RSS/API | "What's happening on campus this week?" |
| Shuttle status | BearTransit API | "When's the next shuttle?" |
| Emergency alerts | WarnMe feed | Proactive safety notifications |
| Dining hours | Cal Dining API | "Is Croads open right now?" |
| Library hours | lib.berkeley.edu | "Is Doe open?" |

### Implementation

Each feed is a separate tool. Only add feeds with reliable, stable APIs.

---

## Phase 4: Multi-University Expansion

Re-add the university registry (previously built, currently stripped to Berkeley-only).

### What's needed

1. Restore university picker in setup wizard
2. Each university gets: Canvas URL, personality, knowledge base
3. Knowledge base per university (or start with empty + community contributions)
4. Personality generated dynamically from university config

### Already built (saved for later)

The multi-university registry with 12 schools was previously implemented and tested. Code is in git history if needed.

---

## Phase 5: Distribution

| Channel | Effort | Reach |
|---------|--------|-------|
| GitHub + pip install | Done | Anyone who finds the repo |
| r/berkeley post | Low | Berkeley students |
| MIMS/iSchool Slack | Low | Direct peers |
| PyPI (`pip install openmind`) | Low | Broader Python community |
| Homebrew formula | Medium | Mac users |

---

## Backlog

- [ ] Course data cache (local JSON, refresh on heartbeat) for faster common queries
- [ ] Quiet hours (no Telegram notifications 11pm-7am, batch morning alerts)
- [ ] Weekly study plan generator (Sunday evening, based on upcoming deadlines + weights)
- [ ] Reading tracker (mark readings as done, "what am I behind on?")
- [ ] Anki export for flashcards
- [ ] Notion integration (alternative to Obsidian — same tool pattern)
- [ ] Apple Reminders integration (alternative to Todoist for Mac users)
- [ ] CI/CD with GitHub Actions (lint, type check, test)
- [ ] Test suite for session parsing, heartbeat logic, tool execution
