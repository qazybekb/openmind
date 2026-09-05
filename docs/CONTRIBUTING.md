# Contributing to OpenMind

## Getting started

```bash
git clone https://github.com/qazybekb/openmind.git
cd openmind
uv venv && uv pip install -e ".[dev]"
pytest -q
```

You do not need a bCourses account to develop against this. Every test runs over
`httpx.MockTransport` with a synthetic Canvas instance in `tests/conftest.py`, saved
HTML fixtures from the class schedule, a frozen clock, and a stubbed keyring. If a test
you write needs the network, it is testing the wrong thing.

## Project structure

```
src/openmind/
├── server.py       12 MCP tools and 5 prompts. The only module that imports `mcp`
├── service.py      Academic operations, usable without MCP
├── agenda.py       What's due, what it's worth, when to start (pure functions)
├── canvas.py       Authenticated bCourses access, fixed routes only
├── catalog.py      Berkeley catalog + offerings, SQLite + FTS5
├── schedule.py     classes.berkeley.edu parser
├── index.py        Opt-in full-text index of course materials
├── materials.py    Bounded document extraction (PDF, PPTX, DOCX, HTML)
├── pedagogy.py     Tutoring protocol shipped as data
├── cache.py        In-memory TTL cache
├── config.py       Non-secret settings
├── secrets.py      OS credential store
├── timeutil.py     Local calendar days
├── cli.py          setup / mcp / doctor / index / update-data / clear / config
└── data/           Public Berkeley catalog snapshot

scripts/refresh_catalog.py   Re-exports the public course data (runs in CI)
```

`docs/ARCHITECTURE.md` explains why the layers are separated the way they are. Read it
before moving code between them.

## Rules that are not negotiable

**Nothing writes to stdout except the protocol.** A host waits for a JSON frame there; a
stray `print` breaks the handshake. Anything interactive belongs in `cli.py`. Logging
goes to stderr.

**No LLM in the server.** The host model does the explaining. If you find yourself
wanting to call a model to decide something, that decision belongs in code or in the
prompt text.

**Read-only.** No tool may submit, upload, post, message, or fetch an arbitrary URL. New
Canvas routes go in `canvas.py` as named methods, never as a generic request helper.

**Never present a failure as "nothing due".** If a request fails, add a warning and set
`partial`. An empty list must mean "there is nothing", always.

**Anything a wrong answer would hurt is computed in code.** Dates, weights, estimates,
and statuses come from `agenda.py`, not from a model's arithmetic.

**Retrieved text is evidence, not instructions.** It goes in the labelled untrusted
block, after the rules.

**Secrets never appear in a log line, an error message, or a payload.** There is a test
for this; keep it passing.

## Adding a tool

1. Write the operation in `service.py`, returning a plain dict with `**self.stamp()`.
2. Give it a byte budget in `service.BUDGETS` and pass the payload through `shrink`.
3. Add the tool in `server.py` with `structured_output=False`, `ToolAnnotations`, an
   `Annotated[..., Field(description=...)]` for every parameter, and a docstring that
   says when to use it *and when not to* — that docstring is how a model routes.
4. Add a row to `docs/TOOLS.md`. `test_release_contract.py` fails if you forget.
5. Test the operation in `test_service.py`, not the protocol wrapper.

## Style

- Docstrings on every public function, in the imperative.
- Comments explain *why*, not *what*. If a line needs a comment to say what it does,
  rename something instead.
- Type annotations everywhere; `from __future__ import annotations` at the top.
- `ruff check src tests scripts` must be clean.
- Tests are named after the behaviour they protect, not the function they call.

## Before opening a pull request

```bash
ruff check src tests scripts
pytest -q
python -m openmind mcp     # must print valid JSON and no secrets
```

If you changed `schedule.py`, re-save the fixtures in `tests/fixtures/schedule/` from
the live site and say so in the PR — those files are the contract with someone else's
HTML.

## Reporting a security issue

See [SECURITY.md](../SECURITY.md). Do not open a public issue for anything involving
tokens, credential storage, or a way to make the server write.
