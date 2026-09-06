# Acceptance checklist

Run before tagging a release. The host and live-account checks need a real AI app and
your own bCourses account, so none of them are established by CI. Public catalog checks
need no bCourses account. Record the host version and account tier, and mark each line
pass or fail — a partial pass is a fail. Never mark a fixture or stdio test as a host pass.

Automated first: `ruff check src tests scripts`, `pytest -q`, `python -m build`,
`twine check dist/*`, and the website build. All regression tests live under `tests/`;
no ignored workspace scripts are required.

## Per host

Do this for **Claude Desktop**, **ChatGPT desktop**, **Claude Code**, and **Cursor**.

| # | Step | Pass |
|---|---|---|
| 0 | Install the newly built wheel on a clean machine; public catalog tools work without setup or a token | |
| 1 | `openmind setup` with your own token: connects, names you, reports your time zone, lists your courses | |
| 2 | `openmind mcp --write claude-desktop` / `--write cursor` / `--write claude-code`; ChatGPT desktop: add the printed command in the app | |
| 3 | Restart the host completely. It lists 12 tools and 5 prompts | |
| 4 | **"What's due this week?"** — a direct answer, real deadlines, times in your zone, priorities and weights shown as given | |
| 5 | **"Explain \<an assignment\> using the slides"** — the assignment and rubric, plus an excerpt citing a real title and page (index the course first) | |
| 6 | Run the **`tutor`** prompt on a topic — it asks before it tells, gives hints rather than answers, and honours `/answer` when you type it | |
| 7 | **"What should I take next semester if I'm into \<topic\>?"** — catalog rows with offered terms, no duplicate cross-listings, ends with the advisor caveat | |
| 8 | **`check_offering`** on a course you know is running — live sections with times and instructors | |
| 9 | `openmind doctor` — no problems, and the host row says "configured and current" | |

Record: host name and version, account tier, OS and version, date.

## Correctness spot-checks

Do these once, on any host.

- A deadline you know is due at **11:59 PM** shows on that day, not the next.
- A course you did **not** enable at setup is invisible: ask about it by name and the
  host is told it is not one of your courses.
- Ask for something with many results (`get_deadlines` over a month) and follow
  `next_offset` to the end — nothing repeated, nothing missing.
- `openmind clear --all` removes the index, catalog, config, and token; `openmind doctor`
  then says setup is needed.

## Windows subset

On a Windows machine, with Claude Desktop:

- Install the new wheel, then `openmind setup` — the token goes into Credential
  Manager, and `getpass` does not echo it.
- `openmind mcp --write claude-desktop --yes` writes `%APPDATA%\Claude\claude_desktop_config.json`.
- `openmind doctor` runs clean, with no encoding errors in the output.
- One tool call from Claude Desktop returns real data.
- From a path containing spaces, `openmind mcp --write claude-code` registers the full
  command. Printed PowerShell commands also run without splitting the path.

## Data pipeline

- Trigger `refresh-data.yml` manually. It runs the parser fixtures first, then the
  crawl; confirm it publishes a `data-<date>-<content-id>` asset, verifies its digest,
  and only then commits `src/openmind/data/`.
- Commit a locally refreshed snapshot with a blank hash, then use `publish_only`.
  Confirm the asset and final manifest are published without a crawl. Rerunning it
  with unchanged data must reuse the asset without a commit.
- On a fresh `OPENMIND_HOME` with no token, run `openmind update-data`. It builds from
  the packaged snapshot, then picks up the published asset and verifies its SHA-256.
- Corrupt a copy of the asset and confirm the client rejects it and keeps the old
  catalog.
- A same-day correction with a different hash is installed. An older-date snapshot
  is rejected, including with a forced update.
- `openmind config --set data_updates=false`, then confirm no GitHub request is made.

## Before tagging

- `CHANGELOG.md` describes this version in the words a student would use.
- The website builds and its install command names an available source or release.
- The "Who can use this" paragraph reads the same in `docs/SETUP.md`, `docs/PRIVACY.md`,
  and the connect guide.
- `docs/PRIVACY.md` still lists exactly the network destinations the code contacts.
