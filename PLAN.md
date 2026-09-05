# Roadmap

## Shipped — 2.0.0

A read-only bCourses MCP server students run on their own machine: 12 tools, 5 prompts,
a deadline engine computed in code, opt-in local search over course materials, Socratic
tutoring shipped as data, and Berkeley catalog and class-schedule data refreshed by a
scheduled job rather than by a release. See [CHANGELOG.md](CHANGELOG.md).

## Next — after a pilot, not before

Everything below reuses `service.*` unchanged. None of it gets built until a handful of
real students have used 2.0 for a semester and asked for it. The version-1 lesson was
that features nobody requested (a Telegram bot, a heartbeat notifier, LaTeX study
guides) cost more to maintain than they returned.

### Scheduling and reminders, explicitly enabled
Local, opt-in notifications for work that is about to go overdue. Version 1 had a
3-hour background notifier that nobody could turn off; this would be off by default,
local only, and would reuse the same `agenda.py` priorities the tools already return.

### Spaced practice
Persist which concepts a student got wrong during a `practice` session and resurface
them. This means storing learning state, which 2.0 deliberately does not do — worth it
only if students say the practice mode is something they come back to.

### Self-hosted remote mode
`openmind-mcp --transport streamable-http` with a single-user token verifier, so a
student can run their own instance on a machine they control and reach it from Claude or
ChatGPT on their phone. Still their token, still their machine — **there will be no
OpenMind-operated server.** The seam is already there: only `_cfg` and `main()` change.

### One-click install
An `.mcpb` desktop extension for Claude Desktop, so setup is a double-click instead of
editing JSON. The most likely thing to double adoption.

### Better retrieval
FTS5 is keyword search. Semantic search over course materials would answer "the thing
about instrumental variables" when the slides say "IV estimation" — but it needs
embeddings, which means either a model in the server (ruled out) or a local embedding
model (a large dependency). Worth revisiting when small local embedders get cheap.

### Grade distributions and prerequisites
Berkeleytime has historical grade distributions and prerequisite chains that would make
course planning much stronger. Only if their terms of use allow it.

## Not planned

- **An OpenMind-hosted service.** Multi-tenant means holding other students' Canvas
  tokens, which is a liability this project will not take on.
- **Other universities.** The catalog pipeline, the class-schedule parser, and the
  Berkeley vocabulary are all campus-specific. Someone else's fork is the right shape
  for someone else's campus.
- **Writing anything to bCourses.** Not submissions, not discussion replies, not
  calendar events. Read-only is the whole safety argument.
