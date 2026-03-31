# OpenMind -- Full Documentation

**AI Study Buddy + Personal Time Manager for UC Berkeley Students**

Version 1.0.0 | Spring 2026 | Built at the School of Information

Website: openmindbot.io | Repository: github.com/qazybekb/openmind

---

## 1. Introduction

### 1.1 What is OpenMind?

OpenMind is an open-source, pip-installable Python CLI tool that serves as an AI-powered study buddy and personal time management assistant for UC Berkeley students. It connects directly to bCourses (Berkeley's Canvas LMS) and provides personalized academic support through a terminal interface and Telegram bot.

Unlike generic AI chatbots, OpenMind:

- Reads your **actual** courses, assignments, grades, and announcements from bCourses
- Knows the current date and calculates real deadlines
- Has a Berkeley personality -- references campus locations, uses Cal slang
- Manages your time by syncing deadlines to Todoist and Google Calendar
- Generates professional study guides and cheatsheets using Claude Opus
- Provides Socratic tutoring from your actual lecture materials
- Sends push notifications for deadlines, grade changes, and emails via Telegram
- Runs entirely on your machine -- no OpenMind server, no data collection

### 1.2 Key Numbers

| Metric | Value |
|--------|-------|
| Total AI tools | 43 (30 core + 13 optional) |
| Canvas API tools | 13 (all read-only) |
| Supported models | 4 default options + any OpenRouter model |
| Course catalog | 11,169 Berkeley courses |
| Dependencies | 9 Python packages |
| Setup time | ~5 minutes |
| Python requirement | 3.11+ |

### 1.3 Supported Platforms

- macOS (Apple Silicon and Intel)
- Linux (Ubuntu 20.04+, Debian 11+)
- Windows via WSL2
- Any system with Python 3.11+ and pip

---

## 2. Installation

### 2.1 Prerequisites

- Python 3.11 or higher
- pip (comes with Python)
- A UC Berkeley bCourses account
- An OpenRouter account (free credits available at openrouter.ai)

### 2.2 Install Command

```
pip install git+https://github.com/qazybekb/openmind.git
```

This installs OpenMind and all 9 dependencies:

| Package | Version | Purpose |
|---------|---------|---------|
| typer | >=0.12 | CLI framework |
| rich | >=13.0 | Terminal UI (panels, tables, markdown rendering) |
| prompt-toolkit | >=3.0 | REPL with history, autocomplete |
| openai | >=1.30 | OpenRouter LLM client (OpenAI-compatible) |
| httpx | >=0.27 | HTTP client for Canvas, web fetching |
| pymupdf | >=1.24 | PDF text extraction |
| python-telegram-bot | >=21.0 | Telegram bot framework |
| google-auth-oauthlib | >=1.0 | Gmail/Calendar OAuth |
| google-api-python-client | >=2.0 | Gmail/Calendar API client |

All integrations are included by default. No optional extras or separate installs needed.

### 2.3 Verify Installation

```
openmind --version
```

This displays the ASCII banner with version number.

### 2.4 Update to Latest Version

```
pip install git+https://github.com/qazybekb/openmind.git --force-reinstall --no-deps
```

The `--no-deps` flag keeps your existing dependencies and only updates OpenMind code.

### 2.5 Uninstall

```
pip uninstall openmind-berkeley
rm -rf ~/.openmind
```

The second command removes all local configuration, tokens, and state files.

---

## 3. First-Run Setup

### 3.1 Overview

Running `openmind` for the first time launches a 3-step setup wizard. Total time: approximately 5 minutes.

### 3.2 Step 1: Connect to bCourses

**What you need:** A Canvas API access token from bCourses.

**How to get it:**

1. Open bcourses.berkeley.edu and log in with your CalNet ID
2. Click your profile icon (top-left sidebar)
3. Click **Settings**
4. Scroll down to **Approved Integrations**
5. Click **+ New Access Token**
6. Enter purpose: "OpenMind"
7. Click **Generate Token**
8. Copy the token immediately (you cannot view it again)

**What happens:** OpenMind validates your token, greets you by name, and discovers all your active courses. A typical student has 5-15 active courses.

**If the token fails:** The wizard shows what went wrong (invalid token, expired, network error) and lets you try again or exit.

**Detailed guide:** openmindbot.io/guides/bcourses

### 3.3 Step 2: Choose Your LLM Model

OpenMind supports any LLM available on OpenRouter. Four recommended options are shown with pricing:

| Option | Model | Cost (Input/Output per 1M tokens) | Best For |
|--------|-------|-----------------------------------|----------|
| 1 (default) | xiaomi/mimo-v2-pro | $1 / $3 | Reliable daily use, affordable |
| 2 | anthropic/claude-sonnet-4-6 | $3 / $15 | Complex reasoning, deep analysis |
| 3 | openai/gpt-5.4 | $2.50 / $15 | GPT ecosystem familiarity |
| 4 | google/gemini-2.5-pro | $1.25 / $10 | Large context, Canvas analysis |

All four models have 1M token context windows and support tool calling (required for OpenMind's 43 tools).

**Typical cost per student per semester:** $0.50-$5.00 depending on model and usage.

You can also type any OpenRouter model ID (e.g., `meta-llama/llama-4-scout`).

**Change later:** Type `/setup model` in the chat at any time.

### 3.4 Step 3: Connect OpenRouter

**What you need:** An OpenRouter API key.

**How to get it:**

1. Go to openrouter.ai/keys
2. Sign up with Google or GitHub (30 seconds)
3. Click **Create Key**
4. Name it "OpenMind"
5. Copy the key (starts with `sk-or-...`)

**Free credits:** New OpenRouter accounts typically receive free credits sufficient for dozens of study sessions.

**Detailed guide:** openmindbot.io/guides/openrouter

### 3.5 After Setup

A welcome screen shows your configuration and lists all available integrations:

```
You're all set, Kazybek! Go Bears!

  Model: xiaomi/mimo-v2-pro
  Courses: 14

Add more features anytime:
  openmind setup telegram   -- chat on your phone + push notifications
  openmind setup gmail      -- search professor emails (read-only)
  openmind setup calendar   -- sync deadlines to Google Calendar
  openmind setup slack      -- search course Slack channels
  openmind setup todoist    -- sync tasks
  openmind setup obsidian   -- save notes to your vault
  openmind setup profile    -- add your goals, interests, resume
  openmind setup model      -- change your LLM

  Guides: openmindbot.io/guides
```

---

## 4. Models and AI Architecture

### 4.1 Chat Model

The student's chosen model handles all conversation, Canvas queries, tool calling, and guided learning. It processes:

- System prompt (~14K tokens): Berkeley personality, playbooks, security policy
- 43 tool definitions: function schemas for all available tools
- Conversation history: last 40 messages
- Tool results: Canvas data, email content, web pages (up to 100K chars each)

### 4.2 Study Guide Model

Claude Opus (anthropic/claude-opus-4-6) is used automatically and exclusively for generating study guide and cheatsheet PDFs. This is a separate API call inside the `generate_study_guide` and `generate_cheatsheet` tools. The student never configures this -- it happens transparently.

**Why Opus?** Study guides require sustained, high-quality long-form writing (10-25 pages). Opus produces the best educational content.

### 4.3 Model Routing Summary

| Feature | Model Used |
|---------|------------|
| Chat, Canvas queries, tools | Student's choice (MiMo default) |
| Guided Socratic tutoring | Student's choice |
| Study guide PDF generation | Claude Opus (automatic) |
| Cheatsheet PDF generation | Claude Opus (automatic) |
| Background heartbeat | No LLM -- rule-based checks |

---

## 5. Use Cases -- Detailed

### 5.1 Deadline Management

**Trigger phrases:** "What's due?", "What should I work on?", "Any deadlines?", "How about [course]?"

**Tools used:** `get_upcoming_assignments`, `get_course_assignments`

**What OpenMind does:**

1. Calls Canvas `/users/self/upcoming_events` API for cross-course deadlines
2. For specific courses, calls `/courses/{id}/assignments` with submission status
3. Sorts by priority: urgency (days until due) x grade weight (points/total)
4. Shows course name, assignment title, due date, points, and submission status
5. Identifies unsubmitted assignments with explicit "UNSUBMITTED" flag

**Response includes:**

- Course name and assignment title
- Due date with day-of-week
- Point value and grade weight
- Assignment details (format, word count, requirements)
- Submission status
- Suggested action: which to tackle first and why

**Example:**

```
Due Monday 3/30:
  Info Law & Policy -- Lab 2 (Submit), 10 pts
  Partner lab, ~90 min. Make a copy of the Google Doc, turn responses red.

Due Tuesday 3/31:
  NLP -- Midterm Report, 10 pts
  Group project progress report. 2000 words, ACL format, 10+ sources.
  Needs: lit review, data collected, preliminary experiments.

Due Wednesday 4/2:
  Big Data -- 4. Midterm report, 12 pts
  Worth 12 pts (part of 65% Final Project category).

The NLP report is the biggest lift -- 7+ hours of work. Start Saturday.
```

**Background alerts:** Every 3 hours, the heartbeat checks for new/changed deadlines and sends Telegram notifications. Format: "Course -- Assignment (due Date, Xd)"

**Deadline change detection:** If a professor changes a due date, OpenMind detects it and notifies: "Big Data -- 4. Midterm report: Apr 02 -> Apr 09 (extended 7d)"

### 5.2 Grade Monitoring

**Trigger phrases:** "How are my grades?", "What's my grade in NLP?", "Show all grades"

**Tools used:** `get_grades`, `get_all_grades`, `get_assignment_groups`

**What OpenMind does:**

1. Fetches enrollment data with current scores for each course
2. Shows percentage and estimated letter grade
3. Flags courses below 80% as needing attention
4. Can show assignment group breakdowns (how much each category is worth)

**Background alerts:** Grade changes are detected every 3 hours. Notifications show direction: "CS170: 92.5% (+2.5%)" or "CS188: 87.0% (-1.0%)"

### 5.3 GPA Calculator

**Trigger phrases:** "What's my GPA?", "What do I need on the final for a 3.5?"

**Tools used:** `gpa_calculator`

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| target_gpa | number | No | Target GPA for what-if analysis (e.g., 3.5) |

**How it works:**

1. Fetches current scores from all enrolled courses
2. Maps percentages to letter grades using standard 4.0 scale
3. Calculates weighted average (note: assumes equal course weights)
4. If target_gpa provided: identifies which courses to improve and by how much

**Important disclaimer:** This is an estimate based on Canvas percentages. Official GPA may differ based on units, grading basis (P/NP, S/U), and department scales. Students should check CalCentral for their official GPA.

**Commands:** `/gpa` or `/gpa 3.5`

### 5.4 Study Planning and Time Management

**Trigger phrases:** "Plan my week", "Help me manage my time", "What should I do this weekend?"

**Tools used:** `get_upcoming_assignments`, `todoist_list_tasks`, `calendar_list_events`, `calendar_add_event`, `todoist_add_task`

**What OpenMind does:**

1. **Gathers deadlines** from Canvas and Todoist
2. **Estimates time** per task using guidelines:
   - Short quiz/survey: 15-30 minutes
   - Writing prompt (1-2 pages): 1-2 hours
   - Lab/partner work: 1.5-3 hours
   - Midterm report/essay: 4-8 hours
   - Final project/paper: 10-20+ hours
   - Reading per chapter: 30-60 minutes
3. **Checks calendar** for existing commitments and free slots
4. **Creates schedule** with specific time blocks and Berkeley study locations
5. **Offers to sync**: add time blocks to Google Calendar and tasks to Todoist

**Priority formula:** urgency x grade weight x time needed

**Commands:** `/plan` or `/plan this weekend` or `/plan NLP midterm`

### 5.5 Canvas-to-Todoist Sync

**What it does:** Creates Todoist tasks for all unsubmitted Canvas assignments with due dates.

**How to trigger:**

- `/sync` -- manual one-time sync
- Automatic: runs every 3 hours in the heartbeat (when Telegram is active)

**Task format:** "Course Name -- Assignment Title" with due date

**Deduplication:** Tracked via `~/.openmind/state/todoist_sync.json`. Never creates duplicates.

**Skips:** Already submitted/graded assignments.

**Setup required:** `/setup todoist`

### 5.6 Canvas-to-Calendar Sync

**What it does:** Creates Google Calendar all-day events for significant assignments (5+ points).

**How to trigger:**

- Automatic: runs every 3 hours in the heartbeat
- Via `/plan` which offers to add time blocks

**Event format:**

- Title: "Course -- Assignment"
- Type: All-day event on due date
- Reminders: 1 day before + 1 hour before

**Deduplication:** Tracked via `~/.openmind/state/calendar_sync.json`.

**Setup required:** `/setup calendar`

### 5.7 Guided Socratic Tutoring

**Trigger phrases:** "Teach me about X", "Help me understand Y", "I don't get Z", "Explain recursion", `/learn [topic]`

**Tools used:** `get_modules`, `get_page_content`, `get_course_files`, `read_pdf`

**5-Phase Socratic Method:**

**Phase 1 -- Diagnose (1-2 questions):**
OpenMind asks what you already know to assess your starting point. "What do you already know about contextual integrity?"

**Phase 2 -- Teach One Concept:**
Explains one building block using analogies from your world (checks your profile interests). Gives a worked example showing step-by-step reasoning.

**Phase 3 -- Check Understanding:**
Asks a scenario-based question (never yes/no). "If the court applied strict scrutiny here, what would happen?"

**Phase 4 -- Respond Adaptively:**

| Student answer | OpenMind response |
|---------------|-------------------|
| Correct | Validate + extend: "Exactly. Now what if we changed [variable]?" |
| Partially correct | Acknowledge + probe: "Good start. But what about [missing piece]?" |
| Wrong | Hint ladder (see below) |

**Hint Ladder for Wrong Answers:**

1. Self-monitoring: "What do you notice about [specific thing]?"
2. Reveal constraint: "Remember that [rule/principle]..."
3. Worked example: "Let me show a simpler case..."
4. Direct guidance: "The key insight is..." (last resort only)

**Phase 5 -- Consolidate:**
Every 3-4 concepts: "Explain [topic] in your own words, like you're teaching a friend."

**Key principle:** OpenMind never gives the answer directly. It guides the student to discover it.

**Commands:** `/learn [topic]`

### 5.8 Study Guide Generation

**Trigger phrases:** "Make me a study guide", "Help me prepare for the midterm", "Create a review document", `/study [course]`

**Tools used:** `get_modules`, `get_page_content`, `get_course_files`, `read_pdf`, then `generate_study_guide`

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_name | string | Yes | Course name (e.g., "Info 205") |
| scope | string | No | "midterm", "final", "weeks 1-5" |
| source_material | string | Yes | Actual course content from Canvas |

**How it works:**

1. Student's model (MiMo/Sonnet/etc.) reads Canvas: fetches modules, lectures, readings
2. Compiles all content into source_material string
3. Calls `generate_study_guide` tool which internally calls Claude Opus
4. Opus writes 10-25 pages of teaching-quality LaTeX content
5. pdflatex compiles to professional two-column PDF
6. Saved to `~/.openmind/study_guides/`
7. In Telegram: PDF is sent back as a document

**PDF format:**

- Two-column layout, 10pt font
- Professional typesetting with section hierarchy
- Exam tip boxes and concept boxes
- Structure adapts to subject:
  - Law/Policy: Frameworks, Cases, Synthesis, Exam Prep
  - CS/Engineering: Concepts, Algorithms, Code Patterns, Problem Sets
  - Business: Theories, Frameworks, Case Studies, Application
  - Sciences: Principles, Methods, Experiments, Problem Solving

**Requirement:** pdflatex must be installed. macOS: `brew install --cask basictex`

**Commands:** `/study [course or topic]`

### 5.9 Exam Cheatsheet Generation

**Trigger phrases:** "Make me a cheatsheet", "I need a reference sheet", "Crib sheet for the exam", `/cheatsheet [course]`

**Parameters:** Same as study guide.

**Output:**

- 2-page PDF only
- 7.2pt font, ultra-tight margins (0.55cm)
- Two-column layout
- Maximum information density
- Designed to print and bring to open-note exams
- Key terms bold, every concept compressed to 1-2 lines
- Includes: definitions, comparisons, formulas, author maps, common mistakes

**Commands:** `/cheatsheet [course or topic]`

### 5.10 Email Monitoring

**What it does:** Checks for unread emails from @berkeley.edu senders every hour.

**Notification format:**

```
New Berkeley emails:
  Prof. Mulligan -- Zoom Class on Monday March 30
    Reminder: class will be on Zoom this Monday. Link in bCourses...
  GSI Sarah -- Lab 2 clarification
    Quick note: you can submit individually even if you worked with...
```

**Features:**

- Subject + sender + body preview (first 150 chars, HTML stripped)
- Preview shown for first 3 emails per notification
- Deduplication via `~/.openmind/state/emails.json`
- Only @berkeley.edu senders (professors, GSIs, bCourses notifications)

**Searchable in chat:** "Search my email for midterm", "Any emails from Professor X"

**Setup required:** `/setup gmail`

### 5.11 Morning Briefing

**Delivery:** Telegram, daily at 8am Pacific Time

**Contents:**

- Today's deadlines (with urgency flag)
- This week's upcoming assignments
- Grades below 80% (needing attention)
- Unread Berkeley email count
- Random spirit phrase

**Example:**

```
Good morning Kazybek! Here's your Monday:

Due today:
  Info Law and Policy -- Lab 2 (Submit)

Coming this week:
  NLP -- Midterm Report (Tue 3/31)
  Big Data -- 4. Midterm report (Wed 4/2)

Grades needing attention:
  MBA 231 Corporate: 71%

3 unread Berkeley emails

Fiat Lux!
```

**Sent once per day.** State tracked in `~/.openmind/state/briefing.json`.

### 5.12 PDF Reading and Summarization

**In Terminal:** "Summarize this PDF: [URL]" -- fetches and extracts text via `read_pdf` tool.

**In Telegram:** Send a PDF file directly to the bot. Add a caption for specific instructions: "summarize", "make flashcards", "find the key arguments".

**How it works:**

1. Downloads PDF (with SSRF protection)
2. Extracts text using pymupdf
3. Sends to LLM for processing
4. Returns summary, flashcards, or answers

**Limits:** PDFs truncated to 30K chars in Telegram, 100K in tool output.

### 5.13 Course Catalog Search

**Trigger phrases:** "What CS courses are good for AI?", "Find graduate courses about privacy", "What's CS 61A about?"

**Tool:** `berkeley_course_search`

**Database:** 11,169 Berkeley courses (6,771 undergrad + 4,398 graduate), bundled locally as CSV. Searchable by subject, keyword, or level. No API needed.

### 5.14 Campus Information

**Tools:** `berkeley_events`, `berkeley_library_hours`, `berkeley_study_rooms`

- **Events:** Live data from events.berkeley.edu JSON API
- **Library hours:** Scraped from lib.berkeley.edu
- **Study rooms:** LibCal booking links for Moffitt, Doe, etc.

### 5.15 Reminders

**Trigger phrases:** "Remind me about office hours Thursday 2pm", "Don't let me forget to email Prof. Smith"

**Tool:** `remind_me`

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| message | string | Yes | What to remind about |
| due_at | string | Yes | ISO 8601 datetime |

**Timezone:** Naive datetimes (without timezone) are automatically normalized to America/Los_Angeles (Pacific Time).

**Delivery:** Via Telegram, checked every hour by heartbeat.

**Storage:** `~/.openmind/reminders.json`

**Commands:** `/remind [text]`

---

## 6. Integrations -- Setup and Configuration

### 6.1 Telegram

**Command:** `/setup telegram` or `openmind setup telegram`

**Requirements:**

1. Create a bot via @BotFather on Telegram (send `/newbot`)
2. Get your user ID from @userinfobot
3. Enter both in the setup wizard

**Features when enabled:**

- Chat with OpenMind from your phone
- Quick-action buttons (Deadlines, Grades, GPA, Learn, Study Plan, Announcements)
- Streaming responses (placeholder message edited as tokens arrive)
- PDF upload and download
- All slash commands work
- Background notifications: deadlines, grades, emails, reminders, morning briefing

**Guide:** openmindbot.io/guides/telegram

### 6.2 Gmail

**Command:** `/setup gmail`

**Requirements:** Google OAuth credentials (credentials.json) from Google Cloud Console

**Steps:**

1. Create a Google Cloud project
2. Enable Gmail API
3. Configure OAuth consent screen (External, add gmail.readonly scope)
4. Create OAuth Client ID (Desktop app)
5. Download credentials.json
6. Provide path in setup wizard

**Access:** Read-only (gmail.readonly scope). Cannot send, delete, or modify emails.

**Guide:** openmindbot.io/guides/gmail

### 6.3 Google Calendar

**Command:** `/setup calendar`

**Requirements:** Same OAuth credentials as Gmail (auto-detected if Gmail is already set up)

**Access:** Read + Write. Can list events and create new events (the only write integration besides Todoist).

**Guide:** openmindbot.io/guides/calendar

### 6.4 Slack

**Command:** `/setup slack`

**Requirements:** Slack app with User OAuth Token (xoxp-...)

**Scopes needed:** channels:history, channels:read, search:read

**Access:** Read-only. Cannot post messages.

**Guide:** openmindbot.io/guides/slack

### 6.5 Todoist

**Command:** `/setup todoist`

**Requirements:** API token from todoist.com/app/settings/integrations/developer

**Access:** Read + Write. Lists tasks and creates new tasks.

**API:** Todoist API v1

### 6.6 Obsidian

**Command:** `/setup obsidian`

**Requirements:** Path to your Obsidian vault folder

**Access:** Local file read/write within the vault directory

**Path handling:** Backslash-escaped paths from terminal (e.g., `Mobile\ Documents`) are automatically unescaped.

### 6.7 Student Profile

**Command:** `/setup profile`

**Fields:** level, major, school, year, interests, career goals, dream companies, GPA goal, strengths, areas to improve, resume PDF path

**Resume import:** If a resume PDF is provided, text is extracted on first chat and the LLM parses skills, experience, and projects into the profile.

**Allowlisted fields:** Only 15 specific fields can be written (security measure against prompt injection).

---

## 7. All 43 Tools -- Reference

### 7.1 Core Tools (30 -- always available)

**Canvas LMS (13 tools):**

| # | Tool | Parameters | Returns |
|---|------|-----------|---------|
| 1 | get_upcoming_assignments | none | All upcoming events with assignment details |
| 2 | get_course_assignments | course_id (required) | Compact summary with UPCOMING_DEADLINES_NOT_SUBMITTED |
| 3 | get_assignment_details | course_id, assignment_id | Full assignment object |
| 4 | get_grades | course_id | Enrollment with current score |
| 5 | get_all_grades | none | Scores for all enrolled courses |
| 6 | get_assignment_groups | course_id | Grade categories with weights |
| 7 | get_modules | course_id | Module list with items |
| 8 | get_page_content | course_id, page_url | Page HTML body |
| 9 | get_course_files | course_id, search_term (optional) | File list with URLs |
| 10 | get_announcements | course_id (optional) | Recent announcements |
| 11 | get_syllabus | course_id | Syllabus body |
| 12 | get_discussion_topics | course_id | Discussion topic list |
| 13 | lookup_course_id | query | Resolves course nickname to ID |

**Berkeley Campus (3 tools):**

| # | Tool | Parameters | Returns |
|---|------|-----------|---------|
| 14 | berkeley_events | category, search (optional) | Live events from events.berkeley.edu |
| 15 | berkeley_library_hours | none | Library hours |
| 16 | berkeley_study_rooms | none | Study room booking links |

**Course Catalog (3 tools):**

| # | Tool | Parameters | Returns |
|---|------|-----------|---------|
| 17 | berkeley_course_search | query, subject, level (optional) | Matching courses from 11K catalog |
| 18 | berkeley_course_details | course_id | Full course description |
| 19 | berkeley_list_subjects | none | All department codes |

**GPA Calculator (1 tool):**

| # | Tool | Parameters | Returns |
|---|------|-----------|---------|
| 20 | gpa_calculator | target_gpa (optional) | Estimated GPA + what-if analysis |

**Profile (3 tools):**

| # | Tool | Parameters | Returns |
|---|------|-----------|---------|
| 21 | get_profile | none | Current student profile |
| 22 | update_profile | field, value | Updates an allowlisted field |
| 23 | import_resume | resume_text, parsed_skills, etc. | Imports resume data |

**Study Guide and Cheatsheet (2 tools):**

| # | Tool | Parameters | Returns |
|---|------|-----------|---------|
| 24 | generate_study_guide | course_name, source_material, scope | PDF path (10-25 pages) |
| 25 | generate_cheatsheet | course_name, source_material, scope | PDF path (2 pages) |

**Reminders (2 tools):**

| # | Tool | Parameters | Returns |
|---|------|-----------|---------|
| 26 | remind_me | message, due_at | Confirmation |
| 27 | list_reminders | none | Pending reminders |

**Web and PDF (3 tools):**

| # | Tool | Parameters | Returns |
|---|------|-----------|---------|
| 28 | web_fetch | url | Page text (SSRF protected) |
| 29 | web_search | query | DuckDuckGo results |
| 30 | read_pdf | url | Extracted PDF text |

### 7.2 Optional Tools (13 -- enabled per integration)

**Gmail (2):** gmail_search, gmail_read

**Slack (3):** slack_search, slack_read_channel, slack_list_channels

**Google Calendar (3):** calendar_list_events, calendar_add_event, calendar_add_deadlines

**Todoist (2):** todoist_add_task, todoist_list_tasks

**Obsidian (3):** obsidian_read, obsidian_write, obsidian_search

---

## 8. Background Alerts (Heartbeat)

### 8.1 Schedule

| Check | Frequency | Source |
|-------|-----------|--------|
| Morning briefing | Daily at 8am PT | Canvas + Gmail |
| Reminders | Every hour | Local reminders.json |
| Deadlines | Every 3 hours | Canvas upcoming_events |
| Submissions | Every 3 hours | Canvas assignments with submission status |
| Grade changes | Every 3 hours | Canvas enrollments |
| Announcements | Every 3 hours | Canvas announcements |
| Berkeley emails | Every 3 hours | Gmail API |
| Todoist sync | Every 3 hours | Canvas -> Todoist |
| Calendar sync | Every 3 hours | Canvas -> Google Calendar |

### 8.2 Notification Format

```
Deadline update:
  Info Law & Policy -- Lab 2 (Submit) (due Mar 31, 3d)
  NLP -- Midterm report (due Apr 01, 4d)
  Big Data -- 4. Midterm report (due Apr 02, 5d)
```

### 8.3 Quiet Hours

Low-priority notifications (headsup-level deadlines) are suppressed between midnight and 8am.

### 8.4 PID Lock

Only one heartbeat instance runs at a time, enforced via `~/.openmind/state/heartbeat.pid`.

---

## 9. Privacy and Security

### 9.1 Data Storage

| File | Location | Transmitted? |
|------|----------|-------------|
| API tokens | ~/.openmind/config.json | To their own service only |
| Student profile | ~/.openmind/profile.json | Fields included in LLM prompt |
| Conversation memory | ~/.openmind/memory.json | Summaries in system prompt |
| Reminders | ~/.openmind/reminders.json | Never |
| Heartbeat state | ~/.openmind/state/*.json | Never |
| Study guides | ~/.openmind/study_guides/ | Never |
| REPL history | ~/.openmind/repl_history | Never |
| Google OAuth tokens | ~/.openmind/gmail/ | To Google APIs only |
| Resume PDF | Original location | Never uploaded |

### 9.2 Security Measures

| Measure | Description |
|---------|-------------|
| SSRF protection | Fail-closed DNS, private IP blocking, redirect validation |
| Canvas HTTPS enforcement | Rejects http:// Canvas URLs |
| Per-turn tool authorization | Blocks unauthorized tools after processing untrusted content |
| Profile field allowlist | Only 15 specific fields writable |
| Prompt secrecy | System instructions never revealed to student |
| Atomic file writes | Tempfile + rename prevents corruption |
| File permissions | Sensitive files created with 0600 (owner-only) |
| Tool output limit | 100K chars safety net |

### 9.3 Read-Only Guarantees

| Service | Access Level |
|---------|-------------|
| Canvas (bCourses) | Read-only (GET only) |
| Gmail | Read-only (gmail.readonly scope) |
| Slack | Read-only (GET only) |
| Google Calendar | Read + Write (creates events) |
| Todoist | Read + Write (creates tasks) |

OpenMind cannot submit assignments, post discussions, send emails, or modify grades.

---

## 10. Testing Guide

### 10.1 Automated Tests

```
python -m pytest tests/ -v       # Run all 22 tests
python -m ruff check src/        # Lint check
python -m compileall src/        # Compile check
```

### 10.2 Manual Testing Checklist

**First Run:**
- [ ] Fresh install from GitHub
- [ ] Setup wizard: 3 steps complete
- [ ] Courses discovered correctly
- [ ] Model selection shows 4 options with prices

**REPL:**
- [ ] Type `/` -- autocomplete menu appears
- [ ] "What's due?" -- all deadlines shown with course names
- [ ] "How about [course]?" -- shows UPCOMING deadlines (not just completed)
- [ ] `/gpa` -- estimates GPA
- [ ] `/learn [topic]` -- Socratic tutoring starts
- [ ] `/plan` -- creates study plan with time blocks
- [ ] `/sync` -- syncs to Todoist
- [ ] `/setup model` -- changes model immediately
- [ ] Ctrl+C during response -- cancels cleanly
- [ ] Tool progress spinner updates ("Checking deadlines...")
- [ ] Response metadata shows time + model + tool count

**Telegram:**
- [ ] Welcome message with buttons on startup
- [ ] Streaming response (placeholder edited in real-time)
- [ ] Send PDF -- summarized and returned
- [ ] All slash commands work
- [ ] Quick-action buttons work
- [ ] Unauthorized user gets "private bot" message

**Time Management:**
- [ ] `/sync` creates Todoist tasks
- [ ] Calendar events created with reminders
- [ ] No duplicates on repeated sync
- [ ] `/plan` checks calendar for conflicts

**Error Handling:**
- [ ] Wrong API key -- helpful error + retry
- [ ] Out of credits -- "top up at openrouter.ai/credits"
- [ ] Network timeout -- actionable message
- [ ] Canvas 500 error -- graceful handling

---

## 11. Troubleshooting

| Problem | Solution |
|---------|----------|
| "openmind: command not found" | `pip install git+https://github.com/qazybekb/openmind.git` |
| Telegram not responding | Ensure openmind is running. Kill old: `pkill -f openmind` |
| "pdflatex not installed" | macOS: `brew install --cask basictex` |
| OAuth browser popup | Normal for first Gmail/Calendar use. Authorize once. |
| Missed deadline in response | Ask about the specific course: "How about Big Data?" |
| Want to change model | `/setup model` |
| Path with spaces not recognized | Wrap in quotes or use backslash escapes |
| Reset everything | `rm -rf ~/.openmind && openmind` |
| Update to latest | `pip install git+...openmind.git --force-reinstall --no-deps` |

---

## 12. Configuration Reference

### 12.1 Config File

Location: `~/.openmind/config.json`

Permissions: 0600 (owner read/write only)

### 12.2 State Files

| File | Purpose |
|------|---------|
| state/deadlines.json | Deadline urgency tracking + due dates |
| state/submissions.json | Seen submission IDs |
| state/grades.json | Previous grade values (for change detection) |
| state/announcements.json | Seen announcement IDs |
| state/emails.json | Seen email IDs |
| state/briefing.json | Last briefing date |
| state/todoist_sync.json | Synced Canvas-to-Todoist assignments |
| state/calendar_sync.json | Synced Canvas-to-Calendar assignments |
| state/heartbeat.pid | PID lock for single-instance enforcement |

### 12.3 Terminal Commands

| Command | Description |
|---------|-------------|
| `openmind` | Start (REPL + Telegram if enabled) |
| `openmind chat` | Terminal REPL only |
| `openmind config` | Show configuration panel |
| `openmind profile` | View student profile |
| `openmind privacy` | Privacy information |
| `openmind setup` | Full setup wizard |
| `openmind setup [name]` | Set up specific integration |
| `openmind --version` | Show version |

---

**Built at UC Berkeley School of Information**

Website: openmindbot.io | GitHub: github.com/qazybekb/openmind

Go Bears!
