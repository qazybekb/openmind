# OpenMind Documentation

**AI Study Buddy + Personal Time Manager for UC Berkeley**

Version 1.0.0 | Spring 2026

---

## What is OpenMind?

OpenMind is an AI-powered study assistant built specifically for UC Berkeley students. It connects to your bCourses (Canvas), reads your actual courses, assignments, and grades, and helps you study smarter. Available as a terminal CLI and Telegram bot.

Install in 30 seconds:
```
pip install git+https://github.com/qazybekb/openmind.git
openmind
```

Website: openmindbot.io

---

## Use Cases

### 1. Check What's Due

**What you say:**
- "What's due this week?"
- "What should I work on?"
- "Any deadlines coming up?"

**What OpenMind does:**
- Reads all your bCourses assignments across every course
- Sorts by urgency x grade weight (a 30% midterm beats a 1% quiz)
- Shows submission status (submitted vs not)
- Includes course name, due date, and points

**Example response:**

> Due Monday 3/30:
> - Info Law and Policy -- Lab 2 (Submit), 10 pts
>   Partner lab, ~90 min. Make a copy of the Google Doc, turn responses red
>
> Due Tuesday 3/31:
> - NLP -- Midterm Report, 10 pts
>   Group project progress report. 2000 words, ACL format, 10+ sources
>
> The NLP report is the bigger lift. I'd start there this weekend.

**Commands:** Just ask naturally, or type `/grades`

---

### 2. Check Your Grades

**What you say:**
- "How are my grades?"
- "What's my grade in NLP?"
- "Show me all my grades"

**What OpenMind does:**
- Pulls current scores from every enrolled course
- Shows percentage + letter grade
- Flags courses below 80%

**Example response:**

> Here are your current grades:
>
> - Deep Tech Commercialization: 94% (A)
> - Special Topics in Info: 96.67% (A)
> - Info Law and Policy: 100% (A)
> - NLP: 100% (A)
> - Data Structures: 88.69% (B+)
> - Big Data and Development: 83% (B)
> - MBA 231 Corporate: 71.43% (C-)
>
> That MBA 231 grade needs attention. Want me to check what's dragging it down?

**Commands:** `/grades` or `/gpa` or `/gpa 3.5` (for what-if analysis)

---

### 3. Plan Your Week

**What you say:**
- "Plan my week"
- "Help me manage my time"
- "What should I do this weekend?"

**What OpenMind does:**
- Checks all your deadlines (Canvas + Todoist)
- Estimates time needed for each task
- Looks at your Google Calendar for free slots
- Creates day-by-day schedule with time blocks
- Offers to add blocks to Calendar and tasks to Todoist

**Example response:**

> Weekend Study Plan:
>
> Saturday:
>   10:00-11:30  Info Law -- Lab 2 with partner (1.5h) at Moffitt
>   1:00-3:00    NLP -- Lit review, find 10+ sources (2h) at Doe
>   3:30-5:30    NLP -- Write methodology section (2h) at Doe
>
> Sunday:
>   10:00-1:00   NLP -- Finish midterm report draft (3h) at Main Stacks
>   2:00-3:00    Review + proofread + submit (1h)
>
> Want me to block these on Google Calendar?

**Commands:** `/plan` or `/plan this weekend`

---

### 4. Sync Deadlines to Todoist and Calendar

**What you say:**
- "Sync my deadlines"
- "Add my assignments to Todoist"
- "Put my deadlines on Google Calendar"

**What OpenMind does:**
- Creates Todoist tasks for every unsubmitted Canvas assignment
- Creates Google Calendar events for assignments worth 5+ points
- Calendar events include reminders (1 day before + 1 hour before)
- Deduplicates -- never creates duplicates
- Runs automatically every 3 hours in background

**Commands:** `/sync` for manual sync. Automatic sync runs in background when Telegram is active.

**Setup required:** `/setup todoist` and `/setup calendar`

---

### 5. Learn Something (Guided Tutoring)

**What you say:**
- "Teach me about contextual integrity"
- "Help me understand binary search"
- "I don't get attention mechanisms"
- "Explain recursion"

**What OpenMind does:**
- Uses Socratic method -- asks questions instead of lecturing
- Starts by checking what you already know
- Teaches one concept at a time with analogies
- Tests understanding with scenario questions (never yes/no)
- If you're wrong: gives hints, not answers
- Uses your actual course materials from bCourses

**Example conversation:**

> You: Teach me about contextual integrity
>
> OpenMind: What do you already know about Nissenbaum's contextual integrity?
>
> You: Something about privacy norms?
>
> OpenMind: Good start! There are 3 independent parameters. If a doctor asks
> your age -- that's fine. But if a stranger does? Same data, different actors.
> What's the second parameter?
>
> You: The type of information?
>
> OpenMind: Exactly! Medical data in a hospital = appropriate. Same data sold
> to advertisers = violation. That's information type. One more parameter --
> hint: think about how data flows.

**Commands:** `/learn [topic]` or just ask naturally

---

### 6. Generate Study Guides

**What you say:**
- "Make me a study guide for the NLP midterm"
- "Create a review document for Info 205"
- "Help me prepare for the final"

**What OpenMind does:**
- Reads your course materials from bCourses (modules, lectures, readings)
- Sends everything to Claude Opus (most capable AI model)
- Generates a 10-25 page professional PDF
- Two-column LaTeX format, organized by topic
- Teaches from scratch -- not a cheatsheet
- Adapts structure to subject (law vs CS vs business)
- Saved to ~/.openmind/study_guides/

**Commands:** `/study [course or topic]`

**Requirements:** pdflatex installed (brew install --cask basictex on macOS)

---

### 7. Generate Exam Cheatsheets

**What you say:**
- "Make me a cheatsheet for the Info 205 midterm"
- "I need a reference sheet for the exam"
- "Create a crib sheet"

**What OpenMind does:**
- Same as study guide but ultra-compressed
- 2-page PDF, 7pt font, maximum information density
- Designed to print and bring to open-note exams
- Key terms, comparisons, formulas, brief definitions
- Powered by Claude Opus

**Commands:** `/cheatsheet [course or topic]`

---

### 8. GPA Calculator

**What you say:**
- "What's my GPA?"
- "What do I need on the final to get a 3.5?"
- "Calculate my GPA"

**What OpenMind does:**
- Calculates estimated GPA from Canvas grades
- Shows each course with letter grade and grade points
- What-if analysis: tells you what score you need to hit a target GPA
- Includes disclaimer: this is an estimate, check CalCentral for official GPA

**Commands:** `/gpa` or `/gpa 3.5`

---

### 9. Read and Summarize PDFs

**What you say (terminal):**
- "Summarize this PDF: [URL]"
- "What's in this lecture slide?"

**What you do (Telegram):**
- Send a PDF file to the bot
- Optionally add a caption: "summarize this" or "make flashcards from this"

**What OpenMind does:**
- Extracts text from PDF using pymupdf
- Summarizes key points
- Can create flashcards, answer questions about content
- Telegram: sends generated PDFs back as documents

---

### 10. Email Notifications

**What happens (automatic):**
- Every hour, checks for unread emails from @berkeley.edu
- Sends Telegram notification with sender, subject, and body preview

**Example notification:**

> New Berkeley emails:
> - Prof. Mulligan -- Zoom Class on Monday March 30
>   Reminder: class will be on Zoom this Monday. Link in bCourses...
> - GSI Sarah -- Lab 2 clarification
>   Quick note: you can submit individually even if you worked with...

**Setup required:** `/setup gmail` + `/setup telegram`

---

### 11. Morning Briefing

**What happens (automatic at 8am PT):**

> Good morning Kazybek! Here's your Monday:
>
> Due today:
>   Info Law and Policy -- Lab 2 (Submit)
>
> Coming this week:
>   NLP -- Midterm Report (Tue 3/31)
>   Big Data -- 4. Midterm report (Wed 4/2)
>
> Grades needing attention:
>   MBA 231 Corporate: 71%
>
> 3 unread Berkeley emails
>
> Fiat Lux!

**Setup required:** `/setup telegram` (must be running for delivery)

---

### 12. Search Course Catalog

**What you say:**
- "What CS courses are good for AI?"
- "Find graduate courses about privacy"
- "What's CS 61A about?"

**What OpenMind does:**
- Searches 11,169 Berkeley courses (6,771 undergrad + 4,398 graduate)
- Filters by subject, keyword, or level
- Bundled locally -- no API needed

---

### 13. Campus Information

**What you say:**
- "What events are happening this week?"
- "Library hours?"
- "Where can I book a study room?"

**What OpenMind does:**
- Live events from events.berkeley.edu
- Library hours (Moffitt, Doe, etc.)
- Study room booking links (LibCal)

---

### 14. Set Reminders

**What you say:**
- "Remind me about office hours Thursday 2pm"
- "Don't let me forget to email Prof. Smith"
- "Remind me Monday 9am about the midterm"

**What OpenMind does:**
- Creates reminder with date/time (normalized to Pacific time)
- Delivers via Telegram when due
- Checks every hour

**Commands:** `/remind [text]`

---

### 15. Slack Integration

**What you say:**
- "Search Slack for midterm review session"
- "What did the TA say about the homework in #cs188?"
- "Show me recent messages in the NLP channel"

**Setup:** `/setup slack`
**Access:** Read-only

---

## Setup

### 3-Step First Run

1. **bCourses token** -- go to bCourses, Profile, Settings, + New Access Token
2. **Choose model** -- MiMo ($1/$3), Sonnet ($3/$15), GPT-5.4 ($2.50/$15), or Gemini ($1.25/$10)
3. **OpenRouter key** -- get one at openrouter.ai/keys (free credits available)

### Optional Integrations

Set up from inside the chat with `/setup [name]`:

| Integration | Command | What it adds |
|-------------|---------|-------------|
| Telegram | `/setup telegram` | Chat from phone + push notifications |
| Gmail | `/setup gmail` | Search professor emails + email alerts |
| Calendar | `/setup calendar` | Auto-sync deadlines with reminders |
| Slack | `/setup slack` | Search course Slack channels |
| Todoist | `/setup todoist` | Task management + auto-sync |
| Obsidian | `/setup obsidian` | Save notes to your vault |
| Profile | `/setup profile` | Personalized advice based on your goals |
| Model | `/setup model` | Switch AI model |

Detailed guides: openmindbot.io/guides

---

## All Commands

| Command | What it does |
|---------|-------------|
| `/learn [topic]` | Guided Socratic tutoring |
| `/study [course]` | Generate study guide PDF (10-25 pages) |
| `/cheatsheet [course]` | Generate 2-page exam cheatsheet |
| `/grades` | Check all grades |
| `/gpa [target]` | GPA calculator with what-if |
| `/plan [scope]` | Create study plan with time blocks |
| `/sync` | Sync Canvas deadlines to Todoist |
| `/remind [text]` | Set a reminder |
| `/courses` | List enrolled courses |
| `/new` | Save context + start fresh |
| `/clear` | Clear conversation |
| `/setup [name]` | Set up an integration |
| `/restart` | Restart OpenMind |
| `/help` | Show all commands |
| `/quit` | Exit |

---

## Privacy

**Stays on your machine:**
- API tokens, profile, conversation memory, reminders, study guides, REPL history

**Sent to your AI model (via OpenRouter):**
- Your messages, course list, profile fields, Canvas data when you ask

**Never sent:**
- API tokens, resume PDF, heartbeat state, terminal history

There is no OpenMind server. Everything runs locally.

Delete everything: `rm -rf ~/.openmind`

---

## Technical Details

- **43 tools** (30 core + 13 from optional integrations)
- **Python 3.11+** required
- **9 dependencies** -- all bundled, no extras needed
- **Models:** MiMo V2 Pro (default), Claude Sonnet 4.6, GPT-5.4, Gemini 2.5 Pro
- **Study guides:** Claude Opus (separate, automatic)
- **pdflatex** needed for /study and /cheatsheet

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "command not found" | `pip install git+https://github.com/qazybekb/openmind.git` |
| Telegram not responding | Make sure openmind is running. Kill old instances: `pkill -f openmind` |
| "pdflatex not installed" | `brew install --cask basictex` (macOS) |
| OAuth browser popup | Normal for first Gmail/Calendar use. Authorize once. |
| Want to change model | `/setup model` |
| Reset everything | `rm -rf ~/.openmind && openmind` |
| Update to latest | `pip install git+https://github.com/qazybekb/openmind.git --force-reinstall --no-deps` |

---

**Built at UC Berkeley School of Information**

Website: openmindbot.io | GitHub: github.com/qazybekb/openmind

Go Bears!
