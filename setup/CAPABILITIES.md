# bCourses Bot — Full Capabilities Guide 🐻💙💛

Your personal AI study buddy for UC Berkeley, powered by Gemini 2.5 Pro.

---

## How It Works

The bot connects to your bCourses (Canvas LMS) account via the Canvas API. When you message it on Telegram, it fetches real data from your courses — assignments, grades, files, readings — and responds like a smart friend, not a corporate assistant.

It runs in Docker on your machine. Your data never leaves your computer except to talk to the Canvas API and Gemini.

---

## 1. Assignments & Deadlines

### What you can ask

| Prompt | What happens |
|--------|-------------|
| "What's due this week?" | Fetches ALL upcoming assignments across all courses, sorted by date |
| "What's due for NLP?" | Assignments for that specific course only |
| "What's due tomorrow?" | Only urgent deadlines |
| "Am I missing anything?" | Checks for unsubmitted assignments past their due date (within last 5 days) |
| "Show all my assignments" | Full list for a course with submission status |

### How it looks

```
You've got 3 things coming up 🐻

⚠️ Social Issues — Unit 8 writing prompt (due TOMORROW 11:59pm)
📋 NLP — Midterm report (due Fri Mar 21)
📚 Finance — Diamond case (due Apr 1)
```

### Urgency flags

| Flag | Meaning |
|------|---------|
| ⚠️ | Due within 24 hours |
| 📋 | Due in 2-3 days |
| 📚 | Due in 5+ days |
| 🚨 | Past due and not submitted |
| ✅ | Already submitted |

---

## 2. Grades

### What you can ask

| Prompt | What happens |
|--------|-------------|
| "What are my grades?" | Current grade for every active course |
| "How am I doing in Finance?" | Grade for a specific course |
| "What did I get on the NLP midterm?" | Score on a specific assignment |
| "What do I need on the final to get an A?" | Calculates using assignment weights from the syllabus |
| "What assignments am I doing worst on?" | Identifies weak areas |

### Grade calculation

The bot fetches assignment group weights (e.g., Homework 30%, Exams 40%, Final 30%) and your current scores, then calculates exactly what you need on remaining assignments to hit your target grade. Shows the math.

---

## 3. Course Content & Files

### What you can ask

| Prompt | What happens |
|--------|-------------|
| "Show me files for NLP" | Lists all course files with download links |
| "What's the latest file uploaded?" | Most recent file across courses |
| "Download the lecture 7 slides" | Provides direct download link |
| "What modules are in Info Law?" | Shows course structure week by week |
| "Show me the syllabus for Big Data" | Fetches and displays the full syllabus |

### Download links

Every file includes a direct download link that works in your browser — no need to log into bCourses separately. Links come directly from the Canvas API with proper authentication.

---

## 4. Readings

### What you can ask

| Prompt | What happens |
|--------|-------------|
| "What readings for Info Law this week?" | Fetches the module page, extracts reading list |
| "Summarize the readings for Social Issues unit 8" | Opens and summarizes each reading |
| "Summarize this article: [URL]" | Fetches any URL and summarizes it |
| "Read NLP lecture 7 slides and summarize" | Downloads the PDF, extracts text, gives summary |

### How it reads content

| Content type | Method |
|-------------|--------|
| **Canvas pages** (HTML) | Fetches directly from API — full text |
| **External articles** (web) | Fetches via web tool, extracts main content |
| **Canvas PDFs** (lectures, readings) | Downloads via API, extracts text with pymupdf |
| **Paywalled content** | Uses Playwright headless browser to try accessing |

### PDF reading

The bot can read lecture slides — even image-based PDFs exported from PowerPoint. It extracts text from every page and summarizes the key points. This works for both text-based academic papers and slide-based lectures.

---

## 5. Announcements & Discussions

### What you can ask

| Prompt | What happens |
|--------|-------------|
| "Any new announcements?" | Checks all courses for recent announcements |
| "What did the NLP professor announce?" | Specific course announcements |
| "What's the latest discussion in Social Issues?" | Shows current discussion topic and prompt |

---

## 6. Assignment Help

### What you can ask

| Prompt | What happens |
|--------|-------------|
| "Help me with the NLP midterm report" | Reads the prompt + rubric, gives specific guidance |
| "What's the prompt for the writing assignment?" | Fetches the exact assignment description from Canvas |
| "What does the rubric say about the Big Data paper?" | Shows grading criteria point by point |
| "What format does the professor want?" | Extracts requirements from assignment description |
| "Draft an outline for the Info Law lab" | Creates an outline based on the rubric |

### How it helps

1. Fetches the full assignment description from Canvas
2. Fetches the rubric if available
3. Identifies: what the professor is asking, word count, format requirements, grading criteria
4. Gives specific, actionable guidance referencing the rubric
5. Can save the outline to Obsidian for you to work on

---

## 7. Teach Me Mode

Interactive learning from YOUR actual course materials — not generic knowledge.

### How to start

| Prompt | What happens |
|--------|-------------|
| "Teach me about attention mechanism from NLP" | Step-by-step interactive teaching |
| "Explain algorithmic fairness from Social Issues" | Uses your course's readings and framing |
| "I don't understand transformers" | Starts from basics, builds up |
| "Quiz me on NLP lectures 6-9" | Practice questions from your course content |
| "Continue where we left off" | Resumes previous study session |

### How it works

1. **Finds source material** — fetches the relevant lecture slides and readings from YOUR course
2. **Explains one concept** — with an analogy or real-world example
3. **Asks you a real question** — not "got it?" but an actual scenario:
   - *"If I give you the sentence 'The bank was steep', how would a contextual embedding handle 'bank' differently than Word2Vec?"*
4. **Evaluates your answer**:
   - Correct → adds nuance, moves on
   - Partially correct → clarifies what you missed
   - Wrong → explains differently with a new analogy
5. **Gets progressively harder**:
   - Level 1: "What is it?" (recall)
   - Level 2: "How does it work?" (understanding)
   - Level 3: "What would happen if...?" (application)
   - Level 4: "Why is this better than...?" (analysis)
   - Level 5: "Design a system that..." (synthesis)
6. **Checkpoint every 3-4 concepts** — asks you to explain the concept in your own words
7. **Connects to assignments** — "This is exactly what Prof. Bamman wants in your midterm report"
8. **Saves progress** — tracks what you studied so you can continue later

### Example conversation

> **You:** Teach me about attention from NLP
>
> **Bot:** Think of reading a sentence. When you see "it" in "The cat sat on the mat because it was tired" — your brain instantly looks back to figure out "it" = "the cat." That's attention.
>
> In NLP, attention lets a model look at ALL words and decide which ones relate to each other. Instead of reading left to right, it sees everything at once.
>
> Quick check: if you have "The bank was steep after the rain" — which words would attention focus on to understand "bank"?
>
> **You:** steep and rain?
>
> **Bot:** Exactly right 🔥 "Steep" and "rain" tell the model this is a riverbank, not a financial bank. That's the power of attention — context from surrounding words resolves ambiguity.
>
> Now let's go deeper. Attention uses three things: queries, keys, and values...

---

## 8. Automatic Notifications

The bot checks Canvas every 3 hours and messages you on Telegram **only if something needs your attention**.

| Notification | Condition |
|-------------|-----------|
| ⚠️ Urgent deadline | Assignment due within 24 hours + not submitted |
| 📋 Upcoming deadline | Assignment due in 2-3 days + not submitted |
| 📚 Future deadline | Assignment due in 5 days + not submitted |
| 🚨 Overdue warning | Past due within 5 days + not submitted |
| 📢 Deadline changed | Professor modified a due date |
| 📄 New file uploaded | New slides or readings posted |
| 📣 Important announcement | Deadline changes, new assignments, class cancellations |
| *Nothing to report* | **Bot stays completely silent** |

The bot ignores:
- Routine announcements
- FYI posts
- Already-submitted assignments
- Assignments overdue more than 5 days

---

## 9. Todoist Integration (Optional)

Sync your Canvas assignments with Todoist for task management.

### What it does

| Feature | How |
|---------|-----|
| "Add assignments to Todoist" | Bulk-adds all upcoming assignments with due dates |
| Auto-detect new assignments | Heartbeat adds new Canvas assignments to Todoist |
| Due date sync | When a professor changes a deadline, Todoist task updates |
| Manual task creation | "Add task: review NLP slides by Friday" |
| View tasks | "What's in my Todoist?" |

### Task format

Tasks are created as: `[Course] — [Assignment name]` with the correct due date.

Example: `NLP — Midterm report` due March 21

---

## 10. Obsidian Knowledge Graph (Optional)

Build a connected knowledge base from your course materials.

### What it does

| Feature | How |
|---------|-----|
| Reading summaries | Saved to `Readings/` with author, course, key arguments |
| Assignment outlines | Saved to `Assignments/` with rubric checklist |
| Concept notes | Saved to `Concepts/` with links to related concepts |
| Study session logs | Saved to `Study Sessions/` with topics covered |

### Knowledge graph structure

```
Concepts/
├── Attention Mechanism.md → links to [[Transformers]], [[Neural Networks]]
├── Algorithmic Fairness.md → links to [[AI Ethics]], [[Classification]]
└── ...

Readings/
├── Vaswani 2017 Attention Is All You Need.md → links to [[Attention Mechanism]]
└── Barocas Selbst 2016.md → links to [[Algorithmic Fairness]]

Assignments/
├── NLP Midterm Report.md → links to [[Attention Mechanism]], [[Language Models]]
└── ...
```

All notes use `[[double bracket]]` links. Open Obsidian's **Graph View** to see your knowledge web visualized.

---

## 11. Web Browsing

The bot has a headless browser (Playwright + Chromium) for accessing web content.

| Feature | How |
|---------|-----|
| Read external articles | Opens and summarizes any URL |
| Access paywalled content | Attempts to read via browser |
| Web search | DuckDuckGo search for any topic |

---

## Course Nickname System

You define short nicknames for your courses in USER.md. Use these when chatting:

| Instead of typing | Just say |
|------------------|---------|
| "Natural Language Processing" | "NLP" |
| "Corporate Finance MBA 231" | "Finance" |
| "Social Issues of Information INFO 203" | "Social Issues" |
| "Information Law and Policy" | "Info Law" |

The bot matches your nickname to the correct Canvas course automatically.

---

## Bot Personality

The bot talks like a UC Berkeley study buddy:

- 🐻 Cal pride — references campus, uses "Go Bears"
- Casual and direct — never corporate or robotic
- Gets excited about good news — "Nice, A on the paper! 🔥"
- Urgent about deadlines — "This is due TOMORROW, have you started?"
- Honest about grades — no sugarcoating, but always constructive
- Never says "of course", "one moment", "let me check", "certainly"
- Never sends filler messages — just answers directly

---

## Privacy & Security

| | |
|---|---|
| **Data storage** | Everything stays on YOUR machine |
| **Canvas token** | Stored in YOUR local config file only |
| **Chat history** | Stored locally, never sent externally |
| **Who can use the bot** | Only YOUR Telegram account |
| **APIs contacted** | Canvas (bcourses.berkeley.edu), Gemini (Google), Telegram |
| **Analytics/tracking** | None |
| **Delete everything** | `docker rm -f bcourses-bot && rm -rf ~/.bcourses-bot` |

---

## Cost

| Service | Cost |
|---------|------|
| Gemini 2.5 Pro | Free tier: 50 requests/day. Paid: ~$1-3/month |
| Canvas API | Free |
| Telegram | Free |
| Docker | Free |
| Todoist (optional) | Free |
| Obsidian (optional) | Free |
| **Total** | **$0-3/month** |

---

*Go Bears! 🐻 Fiat Lux! 💡*
