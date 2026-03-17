# bCourses Bot — Capabilities 🐻💙💛

## What is it?

An AI study buddy that connects to your UC Berkeley bCourses (Canvas LMS) via Telegram. It knows your courses, assignments, grades, and readings — and talks to you like a friend, not a robot.

Powered by Gemini 2.5 Pro + Nanobot.

---

## Assignments & Deadlines

| You say | Bot does |
|---------|---------|
| "What's due this week?" | Shows all upcoming assignments with urgency flags |
| "What's due for NLP?" | Assignments for a specific course |
| "Am I missing anything?" | Checks for unsubmitted past-due assignments |
| "Add assignments to Todoist" | Creates tasks with due dates |

**Urgency flags:**
- ⚠️ Due within 24 hours
- 📋 Due in 2-3 days
- 📚 Due in 5+ days

---

## Grades

| You say | Bot does |
|---------|---------|
| "What are my grades?" | Current grade for every course |
| "How am I doing in Finance?" | Specific course grade |
| "What do I need to get an A?" | Calculates based on assignment weights |

---

## Course Content & Readings

| You say | Bot does |
|---------|---------|
| "What readings for Info Law this week?" | Fetches readings from Canvas, summarizes each |
| "Show me files for NLP" | Lists all course files with download links |
| "Summarize NLP lecture 7 on attention" | Downloads the PDF, extracts text, summarizes |
| "Show me the syllabus for Big Data" | Fetches and displays the syllabus |
| "Any new announcements?" | Checks for recent professor announcements |

---

## Assignment Help

| You say | Bot does |
|---------|---------|
| "Help me with the NLP midterm report" | Reads the assignment prompt + rubric, gives guidance |
| "What's the prompt for the writing assignment?" | Fetches exact assignment description |
| "What does the rubric say?" | Shows grading criteria |

---

## Teach Me Mode

Interactive learning from YOUR course materials.

| You say | Bot does |
|---------|---------|
| "Teach me about attention from NLP" | Step-by-step teaching with comprehension checks |
| "Explain transformers in simple terms" | Analogies and examples from your lectures |
| "Quiz me on lectures 6-9" | Practice questions with feedback |

**How it works:**
1. Bot explains one concept with an analogy
2. Asks you a real question (not just "got it?")
3. Evaluates your answer — explains why right or wrong
4. Gets progressively harder
5. Checkpoint every 3-4 concepts
6. Connects to your assignments: "This is what the rubric wants"

---

## Automatic Notifications

Every 3 hours, the bot checks Canvas and messages you ONLY if something needs attention:

| Notification | When |
|-------------|------|
| ⚠️ Assignment due tomorrow, not submitted | Always |
| 📋 Assignment due in 2-3 days, not submitted | Always |
| 🚨 Overdue (within 5 days), not submitted | Always |
| 📢 Deadline changed | ~8am and ~8pm |
| 📄 New file uploaded | ~8am and ~8pm |
| 📣 Important announcement | ~8am and ~8pm |
| Nothing to report | **Silent** |

---

## Optional Integrations

### Todoist
- Auto-creates tasks from Canvas assignments
- Includes due dates
- Detects new assignments and deadline changes

### Obsidian
- Saves reading summaries to your vault
- Creates assignment outlines with rubric checklists
- Builds knowledge graph with [[linked concepts]]
- Tracks study session progress

### Web Browsing (Playwright)
- Opens and reads external articles
- Accesses content behind simple logins
- Summarizes web pages

---

## Privacy & Cost

**Privacy:**
- Runs 100% on your machine
- No data stored anywhere except your local files
- Only you can talk to the bot

**Cost:**
- Gemini: Free (50 requests/day) or ~$1-3/month paid
- Canvas API: Free
- Telegram: Free
- Todoist: Free
- Total: **$0-3/month**

---

## Example Conversation

> **You:** What's due this week?
>
> **Bot:** You've got 2 things coming up 🐻
> ⚠️ Social Issues — Unit 8 writing prompt (due TOMORROW 11:59pm)
> 📋 NLP — Midterm report (due Friday)
>
> **You:** Help me with the NLP midterm
>
> **Bot:** Just pulled up the assignment. Prof. Bamman wants a 5-page report on your NLP project. The rubric breaks down like this:
> - Research question (20pts) — needs to be specific and novel
> - Methodology (20pts) — describe your approach clearly
> - Results (20pts) — include quantitative evaluation
> ...want me to draft an outline based on the rubric?
>
> **You:** Teach me about attention mechanism
>
> **Bot:** Ok let's break this down 🐻
>
> Think of reading a sentence. When you see the word "it" in "The cat sat on the mat because it was tired" — your brain instantly looks back to figure out "it" = "the cat." That's attention.
>
> In NLP, attention is a mechanism that lets a model look at ALL words in a sentence and decide which ones are most relevant to each other.
>
> Quick check: if I have the sentence "The bank was steep after the rain" — which other words would the attention mechanism focus on to understand "bank"?

---

*Go Bears! 🐻 Fiat Lux! 💡*
