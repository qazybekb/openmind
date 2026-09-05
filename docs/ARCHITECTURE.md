# Architecture

About 2,600 lines of Python, in three layers that never reach past each other.

```
AI host (Claude, Cursor, ChatGPT)
        │  MCP over stdio
        ▼
   server.py          12 tools, 5 prompts. The only module that imports `mcp`.
        │
        ▼
   service.py         Academic operations. Usable without MCP, which is what makes
        │             the CLI and the tests possible.
        │
        ├── agenda.py     What's due, what it's worth, when to start (pure functions)
        ├── pedagogy.py   Tutoring protocol as data
        ├── index.py      Opt-in FTS5 search over course materials
        ├── materials.py  Bounded document extraction
        ├── catalog.py    Berkeley catalog + per-term offerings (SQLite)
        └── schedule.py   Live sections from classes.berkeley.edu
        │
        ▼
   canvas.py          Authenticated bCourses access over a fixed list of routes.
```

Supporting modules: `config.py` (non-secret settings), `secrets.py` (the OS credential
store), `timeutil.py` (local calendar days), `cache.py` (5-minute in-memory TTL),
`cli.py` (setup, doctor, index, clear).

## The load-bearing decisions

### The model talks; the code computes

Anything a wrong answer would hurt is computed in Python and handed over as a labelled
field: local due times, calendar-day urgency, grade weight from assignment-group
weights, hour estimates, start-by dates, submission status. `agenda.py` is pure
functions over Canvas dictionaries with a `golden` test table, so "why is this HIGH?"
has an answer that does not involve a model's judgement.

The host is told, in the server instructions, to show `due_human` verbatim and never
recompute a date.

### Never present a failure as "nothing due"

The failure mode that matters most is a student relaxing because a broken request came
back empty. Every payload carries `as_of`, `tz`, `partial`, and `warnings[]`. A course
that 403s produces a warning naming it and `partial: true`; a Planner outage falls back
to per-course assignment lists and says so. Nothing shortens a list silently — even the
byte-budget trimmer (`shrink`) drops whole items and adds a warning saying it did.

### Read-only is enforced in code, not by convention

`canvas.py` spells out every route it will call. There is no generic `get(url)` a tool
can reach, no shell, no upload, no submission, no messaging. Course ids are validated as
numeric and checked against the student's enabled courses on every call. Grades are
requested for `self`. Downloads are re-checked for SSRF safety on every redirect, and
the Bearer token is dropped as soon as a download leaves bCourses — Canvas file URLs
redirect to signed S3 links that neither want nor should receive it.

### Retrieved documents are evidence, not instructions

Course material text reaches the host inside a delimited block labelled untrusted. The
tool surface is fixed before any document is read, so a slide that says "ignore your
instructions" changes nothing. Search queries are tokenised and quoted before reaching
FTS5, so neither a document title nor a model can inject query operators.

### Stdio hygiene

A host spawns `openmind-mcp` and waits for a protocol frame on stdout. Nothing else may
appear there — no banner, no wizard, no print. Logging goes to stderr and never includes
a credential or document text. Everything interactive lives in `cli.py`. A test asserts
importing the server writes nothing to stdout, and that startup makes no network call
and reads no config; the Canvas connection is built lazily on the first tool call, so
`initialize` returns immediately.

### Token discipline

Each tool has a byte budget (`service.BUDGETS`), enforced by one helper. Long text pages
through cursors rather than being cut off. A test runs every real payload against its
budget, so a course with 300 assignments cannot quietly blow up a context window.

### Data cadence is decoupled from code cadence

The Berkeley catalog and the per-term offerings table are public data that changes on
the university's calendar. A scheduled job re-exports them, publishes a hashed asset,
and clients pick it up within a day after verifying the SHA-256. A student gets current
course data without upgrading anything, and the job needs only the repository token.

`classes.berkeley.edu` refuses GitHub-hosted runners with HTTP 403, so that job refreshes
the catalogs and carries the previous offerings forward untouched rather than failing;
the offerings themselves are refreshed from a machine the site answers
([docs/DISTRIBUTION.md](DISTRIBUTION.md)).

Both carry the date they were captured, and every catalog payload says so — advice from
a stale snapshot should look stale, and a snapshot whose offerings were not refreshed
says why in one line that `openmind doctor` and the catalog payloads repeat. CI fails if
the shipped snapshot is over a year old.

## Storage

| Path | What | When |
|---|---|---|
| OS credential store | The bCourses token | After setup |
| `~/.openmind/mcp/config.json` | Enabled courses, time zone, preferences (0600) | After setup |
| `~/.openmind/mcp/index.db` | Extracted course material text (0600) | Only for courses you index |
| `~/.openmind/mcp/catalog.db` | The public Berkeley catalog | After setup |

Deadlines and grades are never written to disk. They live in a 5-minute in-memory cache
that dies with the process.

## What the tests pin

`httpx.MockTransport` over a synthetic Canvas instance, HTML fixtures saved from the
live class schedule, a frozen clock, and a stubbed keyring — no network, no real
account, no developer credentials.

The suite exists to catch specific classes of mistake:

- a deadline landing on the wrong local day (`test_timeutil`, DST both directions);
- a priority or weight rule changing by accident (`test_agenda`'s golden table);
- a failed course looking like an empty week (`test_service`);
- a document or a model injecting search syntax (`test_materials_and_index`);
- the token appearing in a log line, an error, or a payload (`test_config_and_secrets`);
- a redirect carrying the token off bCourses (`test_materials_and_index`);
- the class schedule being restyled (`test_schedule`, which fails loudly rather than
  reporting that no courses are offered);
- the tool surface, the docs, and stdout hygiene drifting apart (`test_release_contract`).

## Phase 2, deliberately not built

Local scheduling and notifications; spaced-practice state; a self-hosted remote transport
so a student can reach their own instance from a phone; a one-click desktop extension.
Each reuses `service.*` unchanged. None of them is worth building before a pilot shows
students want it.
