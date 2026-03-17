# Obsidian + bCourses Bot — Full Utilization Strategy

## Current State
- Fresh vault at ~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Berkeley
- Folders: Concepts, Courses, Readings, Assignments, Study Sessions
- Bot can read/write via filesystem MCP
- iCloud sync — accessible on iPhone, iPad, Mac

---

## 1. Auto-Generated Course Maps

### What
At the start of each semester, bot crawls every course's modules and syllabus, and creates a **master course map** note.

### How
For each course:
```markdown
# NLP — Course Map

## Course Info
- Professor: [name]
- Office Hours: [from syllabus]
- Grading: Midterm 30%, Final Report 40%, Participation 10%, Assignments 20%

## Weekly Topics
- Week 1: [[NLP/Week 1 - Intro to NLP]]
- Week 2: [[NLP/Week 2 - Text Processing]]
- ...

## Assignments
- [[Assignments/NLP Midterm Report]] (due Apr 1, 30%)
- [[Assignments/NLP Final Report]] (due May 12, 40%)

## Key Concepts
- [[Transformers]]
- [[Attention Mechanism]]
- [[Word Embeddings]]
```

### Value
- One-click overview of entire course
- Links auto-connect everything
- Graph view shows course structure visually

---

## 2. Daily Learning Journal

### What
Bot auto-creates a daily note every time you interact with it.

### How
File: `Study Sessions/2026-03-17.md`
```markdown
# March 17, 2026

## What I studied
- [[Algorithmic Fairness]] from Social Issues (30 min)
- Read [[Barocas Selbst 2016]] for Info Law

## Key takeaways
- You can't satisfy all fairness definitions simultaneously
- Disparate impact ≠ disparate treatment

## Questions I still have
- How does group fairness work in practice?

## Tomorrow's priorities
- NLP midterm report (due in 4 days)
- Social Issues writing prompt (due tomorrow)
```

### Value
- Track what you actually studied vs what you planned
- Review before exams: "What did I study last week?"
- Pattern recognition: which courses get neglected?

---

## 3. Reading Pipeline

### What
Every reading from every course flows through a pipeline:

**Canvas → Bot reads it → Summary note → Linked to concepts → Linked to assignments**

### How
When bot summarizes a reading:
1. Creates: `Readings/[Author Year] [Title].md`
2. Links to relevant `[[Concepts]]`
3. Links to the `[[Assignment]]` it's needed for
4. Tags: `#unread`, `#read`, `#key-reading`

Dashboard note: `Readings/Reading Dashboard.md`
```markdown
# Reading Dashboard

## Unread
- [[Readings/Winner 1980 Do Artifacts Have Politics]] — Social Issues Week 1
- [[Readings/Lessig 2006 Code v2]] — Info Law Week 3

## Read
- [[Readings/Barocas Selbst 2016]] — Social Issues Week 8 ✅
```

### Value
- Never lose track of what you've read
- Exam prep: review all reading summaries in one place
- "What's the most important reading I haven't done?" — bot checks dashboard

---

## 4. Exam Prep Vaults

### What
Before each exam, bot generates a comprehensive study vault.

### How
"Prepare me for the NLP midterm"

Bot creates: `Courses/NLP/Midterm Prep.md`
```markdown
# NLP Midterm Prep

## Topics Covered (Weeks 1-7)
- [[Word Embeddings]] — key: Word2Vec, GloVe, contextual embeddings
- [[Transformers]] — key: self-attention, positional encoding
- [[Language Models]] — key: perplexity, GPT architecture
- ...

## Practice Questions
1. Explain the difference between static and contextual embeddings
2. Why does self-attention scale quadratically?
3. ...

## Key Readings to Review
- [[Readings/Vaswani 2017 Attention Is All You Need]]
- [[Readings/Devlin 2018 BERT]]

## Past Assignment Insights
- In [[Assignments/NLP AP1]], you scored well on X but lost points on Y
- Focus on: [areas from rubric feedback]

## Cheat Sheet
[Key formulas, definitions, dates]
```

### Value
- Everything for exam prep in one note
- Linked to all source materials
- Can quiz yourself from practice questions

---

## 5. Assignment Workbench

### What
For each assignment, bot creates a working note that evolves from outline → draft → final.

### How
"Help me start the Big Data midterm report"

Bot creates: `Assignments/Big Data Midterm Report.md`
```markdown
# Big Data Midterm Report

## Assignment Info
- Course: Big Data and Development
- Due: March 31, 2026
- Weight: 25% of grade
- [[Download prompt|Link to full prompt]]

## Rubric Checklist
- [ ] Research question clearly defined (20pts)
- [ ] Literature review (20pts)
- [ ] Methodology explained (20pts)
- [ ] Data sources identified (20pts)
- [ ] Writing quality (20pts)

## My Outline
### 1. Introduction
- ...

### 2. Literature Review
- [[Readings/...]]
- [[Readings/...]]

### 3. Methodology
- ...

## Notes & Ideas
- [brain dump space]

## Related Concepts
- [[Big Data Ethics]]
- [[Development Economics]]
```

### Value
- Rubric is right there — can't miss what professor wants
- Links to readings you need to cite
- Progress tracking via checkboxes
- Bot can review your outline against the rubric

---

## 6. Cross-Course Concept Web

### What
The real power of Obsidian — concepts that span multiple courses form a web.

### Example
```
[[Privacy]]
├── Info Law: legal frameworks, GDPR, CCPA
├── Social Issues: surveillance, power dynamics
├── Ethical AI: data collection ethics
├── Big Data: privacy in development contexts
└── Needed for: [[Assignments/Info Law Lab 2]], [[Assignments/Social Issues Essay 2]]
```

### How
Every concept note includes a "Courses" section listing where it appears. Obsidian's graph view automatically shows the connections.

### Value
- "How does privacy come up across my courses?" — open the note, see all connections
- Essay writing: pull perspectives from multiple courses
- Deeper understanding through interdisciplinary thinking

---

## 7. Semester Dashboard

### What
One master note that's your home base.

### How
`Dashboard.md`
```markdown
# Spring 2026 Dashboard 🐻

## Quick Links
- [[Courses/Big Data/Big Data]]
- [[Courses/NLP/NLP]]
- [[Courses/Social Issues/Social Issues]]
- [[Courses/Info Law/Info Law]]
- [[Courses/Finance/Finance]]
- [[Courses/Ethical AI/Ethical AI]]

## This Week
![[Study Sessions/2026-03-17]]

## Grade Tracker
| Course | Current | Target |
|--------|---------|--------|
| Big Data | B | A- |
| Social Issues | B- | B+ |
| NLP | — | A |
| Info Law | — | A- |
| Finance | — | B+ |
| Ethical AI | — | A |

## Reading Progress
- 📚 Total readings: 45
- ✅ Completed: 18
- 📖 In progress: 3
- ⏳ Not started: 24

## Upcoming Deadlines
[auto-updated by bot]
```

### Value
- Open Obsidian → see everything at a glance
- Track progress across the entire semester

---

## 8. Template System

### What
Pre-built templates the bot uses consistently.

### Templates needed
- `Templates/Concept.md` — for new concept notes
- `Templates/Reading.md` — for reading summaries
- `Templates/Assignment.md` — for assignment workbenches
- `Templates/Daily.md` — for daily study journal
- `Templates/Exam Prep.md` — for exam prep notes

### Value
- Consistent format across all notes
- Bot always creates structured, useful notes
- Easy to scan and review

---

## Implementation Priority

| Priority | Feature | Impact |
|----------|---------|--------|
| 🔴 Do now | Dashboard + Course Maps | Foundation for everything |
| 🔴 Do now | Reading pipeline + dashboard | Track what you've read |
| 🟡 Do soon | Assignment workbench | Better assignment workflow |
| 🟡 Do soon | Daily learning journal | Track study habits |
| 🟢 Do later | Exam prep vaults | Finals are weeks away |
| 🟢 Do later | Cross-course concept web | Builds naturally over time |
| 🟢 Do later | Semester dashboard | Nice to have, not urgent |

---

## What This Looks Like In Practice

**Monday morning:**
1. Open Obsidian → Dashboard shows your week
2. Message bot: "What readings for Info Law this week?"
3. Bot fetches, summarizes, saves to Obsidian with [[links]]
4. You read them, bot quizzes you
5. Bot saves study session to daily journal

**Before an assignment:**
1. Message bot: "Help me start the NLP midterm report"
2. Bot creates assignment workbench with rubric, outline, linked readings
3. You work on it in Obsidian
4. Message bot: "Does my outline cover all rubric points?"
5. Bot checks and gives feedback

**Before an exam:**
1. Message bot: "Prepare me for Social Issues midterm"
2. Bot generates exam prep note linking all concepts, readings, past quizzes
3. You review in Obsidian, graph view shows connections
4. Message bot: "Quiz me on week 5-8 topics"
5. Bot creates practice questions from course materials

---

*Fiat Lux! 💡🐻*
