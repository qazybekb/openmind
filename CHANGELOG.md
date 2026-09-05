# Changelog

All notable changes to OpenMind are recorded here.

## 2.0.0 — 2026-09-05

OpenMind is now a **read-only bCourses (Canvas) MCP server** that you run on your own
computer and connect to Claude Desktop, Claude Code, Cursor, or the ChatGPT desktop app.
The AI app does the talking; OpenMind returns exact facts about your courses.

This is a rewrite, not an upgrade. Version 1 was a terminal chat assistant with its own
model; nothing about its setup carries over. Your old `~/.openmind` files are left alone
— version 2 uses `~/.openmind/mcp/` and asks for a fresh `openmind setup`.

### Added
- Twelve read-only tools and five prompts over MCP (`docs/TOOLS.md`).
- Deadline ranking computed in code: local due dates, calendar-day urgency, grade weight
  from assignment-group weights, hour estimates, and a start-by date. Overdue work is
  listed first and never mixed into the upcoming list.
- Every payload carries `as_of`, `tz`, `partial`, and `warnings[]`. A course that fails
  to load produces a warning naming it, never a shorter list.
- Opt-in, per-course local search of slides, readings, and pages, with page citations.
  Nothing is stored until you ask for a course by name.
- Socratic tutoring shipped as data — rules, a hint ladder, cited excerpts, and your
  course's own AI policy quoted from its syllabus — with no model inside the server.
- Berkeley catalog search with a per-term offerings table, both refreshed by a scheduled
  job rather than by a release, and both stamped with the date they were captured.
- `check_offering` for live sections from classes.berkeley.edu.
- `openmind doctor`, `openmind clear`, and `openmind config` for setup, diagnosis, and
  deletion.

### Changed
- The bCourses token now lives in your OS credential store, not in a config file.
- Canvas access is limited to a fixed list of routes and to the courses you choose at
  setup. Grades are requested for `self` only.
- Deadlines are rendered in your Canvas time zone. A deadline at 11:59 PM no longer
  shows up on the following day.
- Course materials are downloaded to memory, never to disk, under caps on size, pages,
  characters, and time. The Bearer token is dropped when a download redirects off
  bCourses.
- PDF text extraction moved from PyMuPDF (AGPL) to pypdf (BSD).

### Removed
- The terminal REPL, the Telegram bot, the 3-hour heartbeat notifier, and the internal
  OpenRouter chat loop, along with the OpenRouter dependency and the dead default model.
- Gmail, Slack, Todoist, Obsidian, and Google Calendar integrations.
- LaTeX study-guide generation, reminders, conversation memory, and the student profile.
- The generic `web_fetch`, `web_search`, and `read_pdf` tools.

### Fixed
- Deadline dates shifted by a day for late-evening due times (the UTC/local bug).
- Privacy copy that implied on-device AI. The docs and the website now say plainly that
  the host model's provider receives your course data.

## 1.0.0 — 2026-03-01

Initial release: a terminal Canvas study assistant for UC Berkeley.
