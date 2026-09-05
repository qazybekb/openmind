# Distribution

OpenMind ships as a single PyPI package, `openmind-berkeley`, with two console scripts.

| Script | Purpose |
|---|---|
| `openmind` | The CLI: setup, doctor, index, config, clear |
| `openmind-mcp` | The MCP server itself, over stdio. This is what an AI app launches |

## Installing

```bash
uv tool install openmind-berkeley     # recommended: isolated, on PATH
pipx install openmind-berkeley        # equivalent
pip install openmind-berkeley         # into an environment you manage
uvx --from openmind-berkeley openmind setup   # no permanent install
```

`uv tool` and `pipx` are preferred because they put `openmind-mcp` on a stable absolute
path, which is what an AI app's config needs.

## What is in the wheel

- The `openmind` package.
- `openmind/data/*.csv` — the public Berkeley catalog snapshot (about 6 MB), so the
  catalog works offline from the first launch.
- `openmind/data/catalog_meta.json` — when that snapshot was captured, which terms it
  covers, and the SHA-256 of the matching published asset.

CI asserts the CSVs are present in the built wheel; a catalog that silently vanished
from a release would leave course planning broken with no error.

## Dependencies

| Package | Why |
|---|---|
| `mcp` | The protocol. Pinned `>=2.1,<3`; only `server.py` imports it |
| `httpx` | HTTP to bCourses and the class schedule |
| `pypdf` | PDF text extraction. BSD licensed — PyMuPDF is AGPL and this project is MIT |
| `keyring` | The OS credential store |
| `tzdata` | Windows only; it has no system time zone database |

No LLM SDK, no chat framework, no messaging client. Version 1's `typer`, `rich`,
`prompt-toolkit`, `openai`, `pymupdf`, `python-telegram-bot`, and the Google API
clients are all gone, and a test asserts they do not come back.

## Releasing

```bash
python -m build
python -m twine check dist/*
python -m twine upload dist/*
git tag v2.0.0 && git push --tags
```

Before tagging, run through [docs/ACCEPTANCE.md](ACCEPTANCE.md) — the manual checks that need a real host and a real account — and the summary below.

## Data releases are separate from code releases

Course data changes on the university's calendar. `.github/workflows/refresh-data.yml`
runs `scripts/refresh_catalog.py` daily, and when the data actually changed it commits
the CSVs and publishes a `data-<date>` release with a `catalog-<date>.tar.gz` asset.

Installed clients check that manifest at most once a day, verify the SHA-256, and
rebuild their local catalog. Students get current course data without upgrading the
package, and the job keeps working with only the repository token.

Turn the check off entirely with `openmind config --set data_updates=false`.

## Acceptance

Before a release:

- `pytest -q` and `ruff check src tests scripts` clean on macOS, Linux, and Windows.
- `openmind doctor` reports no problems on a fresh install.
- The server starts in under a second, writes nothing to stdout, and makes no network
  request until the first tool call.
- A real question answered in Claude Desktop, Claude Code, and ChatGPT desktop.
- A deadline at 11:59 PM renders on the correct local day.
- One course returning 403 produces `partial: true` with a warning — never "nothing due".
- A forced data-refresh run with unchanged data produces no commit.
