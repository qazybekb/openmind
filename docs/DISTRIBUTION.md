# Distribution

OpenMind builds as a single Python package, `openmind-berkeley`, with two console
scripts. PyPI publication is pending trusted-publisher configuration by the owner.

| Script | Purpose |
|---|---|
| `openmind` | The CLI: setup, doctor, index, config, clear |
| `openmind-mcp` | The MCP server itself, over stdio. This is what an AI app launches |

## Installing

```bash
uv tool install git+https://github.com/qazybekb/openmind.git
uv tool install .                    # from a checkout of the corrected source
```

After the corrected release reaches PyPI: `uv tool install openmind-berkeley`, or
`pipx install openmind-berkeley`. Public catalog tools need no token; reading your own
courses needs `openmind setup`.

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

## Releasing code

Versions 2.0.0, 2.0.1, and 2.0.2 are already tagged. Do not move a tag or upload changed
files under the same version; every change ships as a new patch version.

```bash
uv run python -m build --outdir .context/release-dist
uv run python -m twine check .context/release-dist/*
```

Before tagging, run [ACCEPTANCE.md](ACCEPTANCE.md), including real-host checks, and
confirm the public repository contains the intended commit. Creating and pushing a
new `v2.0.x` tag starts `publish.yml`; do not also run `twine upload` locally. A manual
workflow run on a branch only builds artifacts, while a tag permits PyPI publication.

### PyPI owner action

For a project that does not yet exist, configure a **pending trusted publisher** in
your PyPI account with project name `openmind-berkeley`, owner `qazybekb`, repository
`openmind`, workflow `publish.yml`, and environment `pypi`. The first successful
publish creates the project; there is no need for a placeholder upload. For an
existing project, add the publisher under that project's publishing settings.
[PyPI's first-project instructions](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).
Do not rerun the old 2.0.0 upload to release these fixes; release the new version after
verification. Account configuration is the owner's, not a CI check.

## Data releases are separate from code releases

Course data changes on the university's calendar. `.github/workflows/refresh-data.yml`
runs in the canonical `qazybekb/openmind` repository only. Crawling and publication
are separate, so an unchanged crawl cannot strand a missing asset:

1. `refresh_catalog.py` optionally refreshes the CSVs, preserving prior offerings if
   the schedule site blocks the runner.
2. `prepare_data_release.py` always builds a deterministic archive of the four data
   files, fills the outer manifest's `data_sha256`, and assigns an immutable
   `data-<catalog_as_of>-<content-id>` release tag. Same-day corrections get a new tag.
3. The workflow uploads the archive and verifies its GitHub asset digest. An existing
   identical asset is reused; a conflicting asset is never overwritten.
4. Only after verification does it commit the manifest and data to the default branch,
   where clients read the manifest. Fully published, unchanged snapshots need no commit.

Installed clients check that manifest at most once a day, verify the SHA-256, and
rebuild their local catalog. A changed hash on the same date is accepted; an older
snapshot is not. The job uses only the repository token. A failed upload leaves the
published manifest untouched, and a failed push can be retried without replacing assets.

Turn the check off entirely with `openmind config --set data_updates=false`.

### The offerings half has to be refreshed by hand

As of 2026-09-05, `classes.berkeley.edu` answers GitHub-hosted runner IP ranges with
HTTP 403. The same URLs return 200 from a laptop with the identical user agent, so it is
an origin block rather than a bug or an outage.

The scheduled job therefore degrades instead of failing: the Coursedog catalogs still
refresh, `term_offerings.csv` is kept exactly as it is, and the manifest describes the
snapshot that actually ships — the previous `offerings_as_of`, `terms_known` and
`offering_count`, plus an `offerings_note` saying why. `openmind doctor` and the catalog
tool payloads repeat that note, so a stale offerings date is never read as "this course
is not offered".

To refresh the offerings, run this from a machine that can reach the site — the
maintainer's, or a self-hosted runner:

```bash
python3 scripts/refresh_catalog.py --out src/openmind/data
```

It prints `changed` or `unchanged` on stdout and progress on stderr. Commit and push
the refreshed files to the canonical repository, then run **Refresh Berkeley course
data** from its Actions tab with **publish_only** enabled. Or, after that push:

```bash
gh workflow run refresh-data.yml --repo qazybekb/openmind --ref main -f publish_only=true
```

This skips another crawl and performs preparation, verified publication, and the
final manifest commit. The local refresh intentionally leaves a blank hash, which
clients ignore until publication completes. The next scheduled run will also repair
an unpublished snapshot even if its crawl reports `unchanged`. Do not treat the local
refresh commit alone as a completed data release.

## Acceptance

Before a release:

- `pytest -q` and `ruff check src tests scripts` clean on macOS, Linux, and Windows.
- `openmind doctor` reports no problems on a fresh install.
- The server starts in under a second, writes nothing to stdout, and makes no network
  request until the first tool call.
- A real question answered in Claude Desktop, Claude Code, and ChatGPT desktop.
- A deadline at 11:59 PM renders on the correct local day.
- One course returning 403 produces `partial: true` with a warning — never "nothing due".
- An unchanged, already-published snapshot produces no commit; an unpublished one is
  repaired by `publish_only`, with its asset available before its hash is committed.
