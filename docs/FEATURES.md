# OpenMind — Features Guide

Everything you can do with OpenMind.

## Assignments & Deadlines

| Ask this | What happens |
|----------|-------------|
| "What's due this week?" | Shows all upcoming assignments sorted by priority (urgency x grade weight) |
| "What's due for NLP?" | Assignments for that specific course |
| "Am I missing anything?" | Checks for unsubmitted assignments past their due date (within 5 days) |
| "What did I submit?" | Shows submission status for recent assignments |

### Priority scoring

Assignments are sorted by how soon they're due multiplied by how much they're worth. A 30% midterm due in 3 days outranks a 1% attendance quiz due tomorrow.

### Urgency flags

| Flag | Meaning |
|------|---------|
| Due within 24 hours | Urgent |
| Due in 2-3 days | Reminder |
| Due in 5+ days | Heads up |
| Past due, not submitted | Warning |

---

## Grades

| Ask this | What happens |
|----------|-------------|
| "What are my grades?" | Current grade for every active course |
| "How am I doing in Finance?" | Grade for a specific course |
| "What do I need for an A?" | Calculates from assignment weights and current scores, shows the math |
| "What if I skip the writing prompt?" | Recalculates your grade without that assignment |

---

## Readings & Course Content

| Ask this | What happens |
|----------|-------------|
| "What readings for Info Law this week?" | Fetches the module page, extracts reading list, summarizes each |
| "Summarize the NLP lecture 7 slides" | Downloads the PDF, extracts text, gives a summary |
| "Summarize this article: [URL]" | Fetches the web page and summarizes it |
| "Show me files for NLP" | Lists all course files with download URLs |
| "What modules are in Big Data?" | Shows the course structure week by week |
| "Show me the syllabus" | Displays the full syllabus |

### How readings work

1. OpenMind fetches the module page from bCourses
2. Parses the HTML for reading links
3. For each link:
   - **External article**: fetches via web and summarizes
   - **Canvas PDF**: downloads via API, extracts text with pymupdf, summarizes
   - **YouTube**: notes as video with title
4. Returns: title, author, 2-3 sentence summary per reading

---

## Assignment Help

| Ask this | What happens |
|----------|-------------|
| "Help me with the NLP midterm report" | Reads the full assignment description + rubric, gives specific guidance |
| "What's the prompt for the writing assignment?" | Fetches the exact assignment description from bCourses |
| "What does the rubric say?" | Shows grading criteria point by point |
| "Draft an outline for the Info Law lab" | Creates an outline based on the rubric requirements |

---

## Teach Me Mode

Interactive learning from your actual course materials.

| Ask this | What happens |
|----------|-------------|
| "Teach me about attention mechanisms" | Step-by-step teaching with real questions |
| "Explain algorithmic fairness" | Uses your course's readings, not generic knowledge |
| "I don't understand transformers" | Starts from basics, builds up |

### How it works

1. Finds relevant lecture slides/readings from your course
2. Explains one concept with an analogy
3. Asks a real scenario question (not "got it?")
4. Waits for your answer
5. If correct: adds nuance, moves on. If wrong: explains differently.
6. Every 3-4 concepts: asks you to explain in your own words

---

## Flashcards

| Ask this | What happens |
|----------|-------------|
| "Make flashcards for NLP lecture 7" | Generates 10-15 Q&A pairs from the lecture content |
| "Flashcards for algorithmic fairness" | Q&A pairs from relevant readings |

Flashcards are formatted as numbered Q/A lists. If Obsidian is enabled, they're saved to `Flashcards/[Course] [Topic].md`.

---

## Announcements & Discussions

| Ask this | What happens |
|----------|-------------|
| "Any new announcements?" | Checks all courses for recent announcements |
| "What did the NLP professor announce?" | Course-specific announcements |
| "What's the latest discussion?" | Shows current discussion topic and prompt |

---

## Gmail (optional)

| Ask this | What happens |
|----------|-------------|
| "Check my email" | Shows recent important emails |
| "Any emails from professors?" | Searches by berkeley.edu senders |
| "Did my professor reply?" | Searches for recent replies |
| "Summarize my unread emails" | Groups by course-related vs other |

Gmail is read-only — OpenMind cannot send, draft, or delete emails.

---

## Todoist (optional)

| Ask this | What happens |
|----------|-------------|
| "Add my assignments to Todoist" | Creates tasks for upcoming assignments with due dates |
| "Add task: review NLP slides by Friday" | Creates a custom task |
| "What's in my Todoist?" | Lists active tasks |

Tasks are formatted as: `[Course] — [Assignment name]` with the correct due date.

---

## Obsidian (optional)

| Ask this | What happens |
|----------|-------------|
| "Save this reading summary" | Writes to `Readings/[Author] [Title].md` |
| "Search my notes for fairness" | Searches vault by filename and content |
| "What notes do I have?" | Lists recent notes |

---

## Automatic Notifications (Telegram only)

When Telegram is enabled, OpenMind checks bCourses every 3 hours and messages you only if something needs your attention:

| Notification | When |
|-------------|------|
| Deadline alert | Assignment due within 24 hours + not submitted |
| Upcoming deadline | Assignment due in 2-3 days + not submitted |
| Submission check | Assignment was due in the last 24 hours — submitted or not? |
| Grade change | Your grade went up or down since last check |
| New announcement | Professor posted in the last 3 hours |

If nothing to report, the bot stays completely silent.

### Deduplication

- Deadlines: keyed by `course_id:assignment_id` — won't repeat for the same assignment unless urgency escalates
- Submissions: keyed by `course_id:assignment_id` — each assignment checked only once
- Announcements: keyed by announcement ID — each announcement reported only once
- Grades: keyed by course ID — only reports actual score changes

---

## Terminal Slash Commands

When using the terminal REPL (`openmind chat`):

| Command | What it does |
|---------|-------------|
| `/help` | Show available commands |
| `/courses` | List your courses with IDs |
| `/grades` | Quick grade check (asks the LLM) |
| `/clear` | Clear conversation history |
| `/config` | Show config directory path |
| `/quit` | Exit |

---

## Bot Personality

OpenMind talks like an actual Berkeley student:

- Says "hella" naturally (not forced)
- References real campus spots (Moffitt, Doe, Main Stacks, Free Speech Cafe, Croads)
- Gets urgent about deadlines, celebrates wins
- Might shade Stanford if the moment is right
- Says "Fiat Lux!" when things go well
- Never sounds like ChatGPT — no "Great question!", no "I hope this helps!"
- Never announces what it's doing — just does it and shows results
