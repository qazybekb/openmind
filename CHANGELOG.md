# Changelog

All notable changes to OpenMind are recorded here.

## 2.0.2 — 2026-09-06

Found by running a real account through every Canvas-backed tool over stdio.

### Changed
- `openmind setup` marks the newest term's courses and shares only those by default.
  bCourses keeps every past course "active" with no term end date, so "Enter for all"
  shared two years of courses. Type `all` to share everything; re-running setup keeps
  the stored token when you press Enter at the token prompt.
- Course nicknames keep their full title (up to 60 characters), drop a leading
  "Fall 2026, " or trailing "(Fall 2026)", which the term field already carries, and
  keep the whole name when the part after the last " - " has no letters in it
  ("SHAPE Student Training - UCB - 2026-2027" is not called "2026-2027").
- `openmind setup` with no terminal (piped or closed stdin) keeps the stored token
  instead of dying in `getpass` with an EOFError traceback.
- `get_deadlines` reads the Planner first and fetches grade weights only for courses
  with work in the window, a few at a time. A twenty-course account went from 13 s to
  about 2 s.
- Deadline items are leaner: one human `start_by` date, no URL (derivable from the ids),
  and confidence only when it is low. Budgets for `list_courses`, `get_deadlines`, and
  `get_grades` are sized for twenty enabled courses, and the omission note for course
  lists says to share fewer courses rather than to narrow a query.
- A catalog answer that refreshed its snapshot from GitHub reports that as `data_note`,
  not as a warning: the answer is more complete, not less, so `partial` stays false.

### Fixed
- "Final Project Team Interest Form" was estimated at 15 hours; forms, questionnaires,
  consent and intake items are now paperwork (0.25 h) whatever they are forms for.
- Subprocess tests never consult the developer's real credential store or reach GitHub.
  `OPENMIND_CREDENTIAL_STORE=none` disables the OS store for a process.
- The daily data job republished an identical graduate catalog on 2026-09-06 because
  Coursedog served the same rows in a different order. Catalog rows are now sorted
  before rendering, and the packaged files are sorted once, so an unchanged catalog
  stops the job without a new asset, manifest commit, or client download.

## 2.0.1 — 2026-09-05

### Changed
- Install and data-publication instructions distinguish preparation from successful
  publication, while `openmind-berkeley` is not yet on PyPI.

### Fixed
- Incomplete Canvas listings no longer delete unseen indexed materials.
- Materials that reappear or receive a new source revision can be indexed again;
  obsolete failure notes and exhausted retry counts no longer strand them.
- Claude Code registration preserves executable paths and arguments containing spaces.
  Printed shell commands are quoted for POSIX shells or Windows PowerShell.
- Unchanged crawls can publish missing catalog assets. Deterministic, immutable assets
  are verified before the matching manifest is committed, with a publish-only repair mode.
- Same-day catalog corrections install when their verified hash changes, without
  permitting older-date rollbacks.
- PDF, PPTX, and DOCX parsing runs in a subprocess that is killed and reaped on timeout,
  instead of checking elapsed time only after a potentially blocking parser returns.

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
- Berkeley catalog search with a per-term offerings table, refreshed by a scheduled job
  rather than by a release, and both stamped with the date they were captured. The class
  schedule blocks GitHub-hosted runners, so the offerings half is refreshed from a machine
  it will answer; the job keeps the catalogs current and says so in the manifest
  (`docs/DISTRIBUTION.md`).
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

### Fixed before release, found by driving the server over stdio
- Catalog search buried the obvious answer: searching "causal inference" never returned
  STAT 156, the course actually called Causal Inference.
- A page of ten catalog results was silently cut to six by the response size limit.
- The Berkeley catalog could not be built without a bCourses token, even though it is
  public data that ships in the package.
- Tutoring prompts failed with a generic error instead of saying "run `openmind setup`"
  when no token was stored.
- `pytest` and `python -m pytest` disagreed about whether the test suite could load.

### Fixed before release, found by an implementation review
- `get_deadlines` promised a next page it had not delivered, so 19 of 30 assignments
  were unreachable, and overdue work had no continuation at all.
- Every page of a non-indexed course's materials returned the first page again.
- A slide longer than the response limit returned "nothing left to read" and could never
  be read at all.
- The data refresh job published an empty offerings table when the class schedule was
  down, which would have told every student their courses were not offered.
- Document extraction limits were declared but not enforced: a 624-byte slide deck
  expanded to 400,100 characters and reported itself complete.
- A course list that hit the page limit was cached as if it were the whole list.
- A pagination link could downgrade the connection to plain HTTP and carry the bCourses
  token with it.
- A document that failed to extract once was never retried, and the failure count reset
  to zero while it was still broken.
- A page deleted from bCourses kept being quoted from the local index with no warning.
- Long assignment descriptions and syllabi could push a response past its size limit.
- Cross-listed courses appeared once per code, so three of ten course suggestions could
  be the same class.

## 1.0.0 — 2026-03-01

Initial release: a terminal Canvas study assistant for UC Berkeley.
