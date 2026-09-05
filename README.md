# OpenMind

**Your bCourses, in Claude.** A read-only Canvas connector for UC Berkeley students that
runs on your own laptop.

Ask your AI app *"what's due this week?"* and get the real answer — with due dates in
your time zone, what each item is worth, how long it will take, and when you need to
start. Ask it to tutor you on a topic and it teaches from your own lecture slides,
citing the page.

```
You:  what's due this week?

Claude:  Two things, and one is overdue.

         OVERDUE — Causal Inference: Problem Set 4, was due Tue Sep 1, 11:59 PM.
         Still submittable; it's 20% of your grade.

         HIGH — Causal Inference: Problem Set 3, due tonight at 11:59 PM.
         20% of the grade, about 6 hours. You should already be working on it.

         HIGH — Causal Inference: Midterm 1, due Thu Sep 10, 11:59 PM.
         30% of your grade, ~4 hours of study. Start by Wednesday.

         Nothing else in NLP until the Final Project on Sep 13.
```

## What it is

OpenMind is an [MCP](https://modelcontextprotocol.io) server: a small program you run
that gives an AI app a set of tools. It has twelve, and all of them read.

The division of labour is deliberate. **The model talks; the code computes.** Deadlines,
grade weights, hour estimates, and start-by dates are worked out in Python and handed
over as labelled facts — because a due date off by a day, or a wrong "this is 5% of your
grade", is worse than an unhelpful answer. No LLM runs inside OpenMind.

Works with **Claude Desktop**, **Claude Code**, **Cursor**, and the **ChatGPT desktop
app**.

## Install

```bash
uv tool install openmind-berkeley     # or: pipx install openmind-berkeley
openmind setup                        # paste a bCourses token, pick your courses
openmind mcp                          # prints the config for your AI app
```

Then paste that config into your AI app, restart it, and ask "what's due this week?".
Full walkthrough: [docs/SETUP.md](docs/SETUP.md).

## What you can ask

| You say | What happens |
|---|---|
| "What's due this week?" | Real deadlines, ranked, with weights and start-by dates |
| "Is my Tuesday deadline actually Tuesday?" | Your time zone, from your Canvas profile |
| "What's my grade in STAT 156?" | What bCourses shows, broken down by assignment group |
| "Explain problem set 3 using the week 3 slides" | The assignment, the rubric, and cited excerpts from your materials |
| "Tutor me on confounding" | Socratic tutoring from your own course materials — questions first, answers only if you ask |
| "Quiz me on this week's reading" | Retrieval practice, one question at a time, with citations |
| "What should I take next semester if I'm into NLP?" | Catalog matches filtered to what's actually offered, with the advisor caveat |
| "Is STAT 156 offered this fall?" | Live sections, times, instructors, and seats from the class schedule |

See [docs/TOOLS.md](docs/TOOLS.md) for every tool and prompt.

## What it will not do

There is no tool to submit work, post a discussion reply, send a message, upload a file,
change a grade, or fetch an arbitrary URL. Read-only is enforced in code: the Canvas
routes are a fixed list, course access is limited to the courses you picked at setup,
and grades are requested for yourself only.

## Privacy, honestly

OpenMind runs on your machine with your own token. There is no OpenMind server, no
account, and no telemetry.

**But the AI is not local.** When Claude or ChatGPT answers, your course data goes to
that provider under their privacy policy. OpenMind cannot change that, and does not
pretend otherwise. If a course is sensitive, don't enable it.

Your deadlines and grades are never written to disk. Course documents are stored only
for courses you explicitly index, and `openmind clear` deletes everything.

Full detail — including all four network destinations — in
[docs/PRIVACY.md](docs/PRIVACY.md).

## Commands

```bash
openmind setup          # store a token, choose courses
openmind mcp            # print config for Claude, Cursor, or ChatGPT
openmind doctor         # check everything end to end
openmind index --course 1234   # make a course's slides and readings searchable
openmind update-data    # refresh the public Berkeley catalog
openmind config         # show or change settings
openmind clear --all    # delete everything OpenMind stores
```

## Requirements

Python 3.11 or newer, a bCourses account, and a desktop AI app that supports local MCP
servers. macOS, Windows, and Linux.

## Not affiliated with UC Berkeley

OpenMind is an independent student project. "UC Berkeley", "bCourses", and "Berkeley
Academic Guide" are referred to only to describe what this connects to. It is not
endorsed by or affiliated with the University of California.

MIT licensed. Built by a Berkeley student who was tired of finding out about deadlines
too late.
