# Canvas Bot (@qb_bcoursesbot) — Improvement Roadmap

## Current State

- **Model**: Gemini 2.5 Pro
- **Tools**: Canvas API (via web_fetch), Todoist MCP, Playwright + Chromium, DuckDuckGo
- **Heartbeat**: Every 3 hours — deadline alerts + announcement checks
- **Personality**: Cal study buddy 🐻

---

## 1. Performance & Speed

### Problem: Bot makes too many API calls per request
Every "what's due?" query fetches data live from Canvas, which is slow (2-5 seconds per API call, multiple calls = 10-20 second response).

### Solution: Local course data cache
- Create a cron job that runs every 6 hours and saves all course data to a JSON file in the workspace:
  - All assignments with due dates and submission status
  - All grades
  - Module structures
  - Recent announcements
- Bot reads the local file first (instant), only hits Canvas API for fresh data when explicitly asked
- File: `~/.nanobot-canvas/workspace/course_cache.json`
- Heartbeat task: "Update course cache from Canvas API"

### Impact: 10x faster responses for common questions

---

## 2. Proactive Study Planning

### Weekly Study Plan Generator
- Every Sunday evening, auto-generate a study plan for the week
- Based on: assignments due, their weights, estimated difficulty
- Factors in: rubric complexity, past grades in similar assignments
- Output to Telegram + save as Obsidian note
- Example: "This week focus on: NLP midterm report (30% of grade, due Fri) → Big Data midterm (due next week, start outline)"

### Smart Priority Scoring
- Weight assignments by: due date proximity × grade percentage × difficulty
- "What should I work on first?" → bot calculates priority score
- Considers: how much of your grade each assignment is worth

---

## 3. Reading Management

### Reading Tracker
- Track which readings you've completed vs still need to do
- Save to a workspace file: `readings_tracker.json`
- "Mark Info Law week 3 readings as done"
- "What readings am I behind on?"
- Weekly: "You have 12 unread readings across 4 courses"

### Reading Summaries Library
- After summarizing a reading, save it to Obsidian
- Folder structure: `Readings/[Course]/[Week] - [Title].md`
- Build a searchable knowledge base over the semester
- "What did we read about algorithmic fairness?" → search saved summaries

### PDF Processing Pipeline
- Download Canvas PDFs to a local folder (mounted volume)
- Use a PDF-to-text tool inside Docker for better extraction
- Option: Add `pymupdf` or `pdfplumber` Python package to Dockerfile
- Much better than Playwright snapshot for dense academic PDFs

---

## 4. Grade Intelligence

### GPA Dashboard
- "How's my GPA looking?" → calculate estimated GPA across all courses
- Track grade trends over time: "Your NLP grade went from B+ to A- this month"
- Save grade snapshots weekly to track progress

### What-If Scenarios
- "What if I skip the writing prompt?" → recalculate grade
- "What's my worst-case grade if I get B on everything remaining?"
- "What assignments can I afford to do poorly on?"

### Grade Alerts
- Add to heartbeat: if a new grade is posted, notify immediately
- "You got an A on the Info Law lab! 🔥 Your course grade is now 92%"
- Track: fetch grades every heartbeat, compare with previous, alert on changes

---

## 5. Assignment Help Upgrades

### Assignment Draft Outlines
- "Start the NLP midterm report" → bot reads the prompt + rubric, generates an outline
- Saves as Obsidian note: `Assignments/NLP/Midterm Report Outline.md`
- Includes: section headings, what to cover per rubric criteria, suggested word count per section

### Rubric Checklist
- "Give me a checklist for the Big Data midterm report"
- Converts rubric criteria into a checkable todo list
- Save to Todoist as subtasks under the main assignment task

### Peer Review Prep
- "What should I look for when reviewing [assignment]?"
- Fetches the rubric and generates a peer review guide
- Based on actual grading criteria

---

## 6. Exam Preparation

### Study Guide Generator
- "Prepare me for the NLP midterm"
- Fetches: syllabus topics covered, all reading summaries, assignment prompts, quiz questions
- Generates a comprehensive study guide
- Saves to Obsidian

### Practice Quiz Mode
- Fetch past quiz questions from Canvas
- Generate new questions in the same style
- Interactive: ask question → wait for answer → give feedback
- Track score: "You got 7/10 on transformers practice"

### Flashcard Generation
- "Make flashcards for Info Law week 5"
- Generate Q&A pairs from readings and lecture notes
- Format for Anki export or just show in Telegram

---

## 7. Better Notifications

### Grade-Aware Deadline Urgency
- Don't just alert by time — consider grade impact
- ⚠️ "NLP midterm report is due in 2 days AND it's worth 30% of your grade" (high urgency)
- 📋 "Social Issues attendance quiz due tomorrow, worth 1%" (low urgency, just a reminder)

### Submission Confirmation
- After a deadline passes, check if you submitted
- "Did you submit the Info Law Lab 2? I see it was due at midnight and... ✅ looks like you did! Nice."
- Or: "🚨 Info Law Lab 2 was due 2 hours ago and I don't see a submission. Did you submit?"

### Quiet Hours
- No notifications between 11pm-7am Pacific
- Batch morning alerts for anything that happened overnight

---

## 8. Multi-Course Intelligence

### Cross-Course Connections
- "Where does [concept] appear across my courses?"
- Search all course pages, readings, and assignments for a topic
- "Machine learning ethics comes up in Ethical AI (week 4), Social Issues (week 8), and NLP (midterm project)"

### Workload Balancing
- "Which week has the most deadlines?"
- Visual: show a heatmap of assignments per week
- Alert if a week is overloaded: "Next week you have 5 assignments due across 4 courses — might want to start early"

### Semester Overview
- "How much of each course is left?"
- Show: completed vs remaining assignments, current grade trajectory
- "NLP: 60% done, on track for A-. Finance: 40% done, B+ trending"

---

## 9. Integration Improvements

### Todoist Project Structure
- Create a Todoist project per course instead of dumping everything in Inbox
- Subtasks for multi-part assignments
- Labels: #urgent, #reading, #writing, #group-project

### Google Calendar Sync
- Auto-create calendar events for assignment deadlines
- Block study time before major deadlines
- Add lecture times from Canvas calendar

### Obsidian Integration
- Add Obsidian vault to Canvas bot (mount the volume)
- Save all generated content: study guides, reading summaries, assignment outlines
- Build a semester-long knowledge base
- "Search my notes for [topic]" → searches saved summaries

---

## 10. UX Polish

### Quick Commands
- Train the bot to understand shortcuts:
  - "d" or "due" → what's due this week
  - "g" → grades
  - "r [course]" → readings for that course
  - "h" → help/commands list

### Context Memory
- Remember what we were discussing: "summarize the next reading" without re-specifying the course
- "What about the second one?" → knows which reading list we were looking at

### Error Recovery
- If Canvas API is down, say so clearly instead of a generic error
- Cache last known data so bot can still answer from cache
- "Canvas seems to be down right now. Based on what I last checked 2 hours ago: [data]"

### Conversation History
- Don't repeat information already shown in the current conversation
- "You already have these in Todoist from our earlier chat"

---

## Implementation Priority

| Priority | Improvement | Effort | Impact |
|----------|------------|--------|--------|
| 🔴 High | Course data cache (speed) | Medium | Huge — 10x faster |
| 🔴 High | Grade alerts in heartbeat | Low | High — never miss a grade |
| 🔴 High | Submission confirmation | Low | High — prevents missed deadlines |
| 🟡 Medium | Reading tracker | Medium | Good — stay on top of readings |
| 🟡 Medium | Obsidian integration | Low | Good — knowledge base |
| 🟡 Medium | Todoist project structure | Medium | Good — better organization |
| 🟡 Medium | Assignment draft outlines | Low | Good — faster start on assignments |
| 🟡 Medium | PDF text extraction (pymupdf) | Medium | Good — better reading summaries |
| 🟢 Low | Study guide generator | Medium | Nice — exam prep |
| 🟢 Low | Practice quiz mode | Medium | Nice — active recall |
| 🟢 Low | Cross-course connections | High | Nice — deeper learning |
| 🟢 Low | Quick commands | Low | Nice — faster interaction |
| 🟢 Low | Quiet hours | Low | Nice — no 3am alerts |

---

## Cost Estimate After Improvements

| Current | After improvements |
|---------|-------------------|
| ~$3-5/month Gemini | Same or less (caching reduces API calls) |
| 50 free Gemini requests/day | Fewer needed with cache |
| Canvas API: unlimited | Same |
| Todoist: free | Same |

---

*Go Bears! 🐻💙💛*
