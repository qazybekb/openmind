# Privacy

OpenMind runs on your computer, under your account, with your own bCourses token. This
document says exactly what that does and does not mean.

## What "local" means here, and what it does not

**It means** you hold the credential, the data lives on your machine, and no OpenMind
server exists to hold either. There is no OpenMind account, no sign-up, no hosted
service, and nobody at OpenMind can see your courses.

**It does not mean the AI is local.** OpenMind is a connector for Claude, Cursor, or
ChatGPT. When you ask one of those apps a question, it calls OpenMind, gets your course
data back, and sends that data to its own provider to write the answer. Your deadlines,
grades, and quoted course material go to whichever AI provider you chose, under their
privacy policy — not OpenMind's. If that is not acceptable for a particular course, do
not enable that course.

No LLM runs inside OpenMind. The server does arithmetic and retrieval; the host model
does the talking.

## Who can use this

OpenMind is for a UC Berkeley student running their own copy on their own machine with
their own bCourses access token. That is what personal access tokens are for. Your token
is never shared, collected, pooled, or sent anywhere except bCourses; there is no
OpenMind server to send it to, and no OpenMind account exists. If you want a friend to
use it, they install it themselves and generate their own token — never hand yours over,
and never run one instance on someone else's behalf. Canvas asks applications that
operate *on behalf of other people* to use OAuth; this one operates only on behalf of
the person who installed it. The maintainer has raised the token policy with Berkeley
Research, Teaching, and Learning and will follow whatever guidance comes back.

## Every place OpenMind connects to

Four destinations. There is no general web-fetch tool, so there is no fifth.

| Destination | When | What is sent |
|---|---|---|
| `bcourses.berkeley.edu` | Every tool call that reads course data | Your bCourses token, in an `Authorization` header |
| The file host bCourses redirects to (currently AWS S3) | Only when a course document is downloaded for indexing or reading | Nothing. The token is **dropped** before the redirect is followed |
| `raw.githubusercontent.com` / `github.com` | At most once a day, when a catalog tool runs | Nothing about you — a public file request. Turn it off with `openmind config --set data_updates=false` |
| `classes.berkeley.edu` | Only when `check_offering` is called | The course code you asked about. No token, no identifier |

Set `data_updates: false` and the GitHub request never happens; the catalog then stays
at whatever snapshot shipped with your version.

## What is stored, and where

Everything lives under `~/.openmind/mcp/` (or `$OPENMIND_HOME`).

| File | Contents | When it exists |
|---|---|---|
| OS credential store | Your bCourses token | After `openmind setup`. Not a file — macOS Keychain, Windows Credential Manager, or Secret Service |
| `config.json` (mode 0600) | Enabled course ids and nicknames, your Canvas time zone, your name, preferences | After setup |
| `index.db` (mode 0600) | Extracted text of course materials, **only for courses you explicitly index** | Only after you run `openmind index` or the `index_course` tool |
| `catalog.db` | The public Berkeley course catalog | After setup |
| `data_check` | A timestamp of the last catalog update check | If updates are on |

`token` (mode 0600) appears only if you ran setup with `--allow-file-secrets` on a
machine with no credential store, and setup prints a warning when it does.

## What is not stored, ever

- **Deadlines and grades.** Fetched live, held in memory for five minutes, gone when the
  server stops. Nothing about your grades is written to disk.
- **Conversations.** OpenMind never sees your chat with the AI app, only the tool calls.
- **Your answers during tutoring.** No learning profile, no progress tracking, no
  spaced-repetition state.
- **Telemetry.** No analytics, no crash reporting, no usage counters, no phone-home.
- **Course materials for courses you did not index.** Nothing is stored by default.

## Reading your data is opt-in twice

At setup you pick which courses OpenMind may read at all — courses you leave out are
invisible to every tool. Storing materials on disk is a second, separate choice, made
per course. `list_courses` shows which courses are indexed.

## Deleting everything

```bash
openmind clear          # delete the indexed course materials
openmind clear --all    # also delete the catalog, your config, and your stored token
```

Your bCourses account is untouched. To cut access off at the source, delete the access
token in bCourses: Account → Settings → Approved Integrations.

## What OpenMind cannot do

Read-only is enforced in code, not by convention. There is no tool that submits work,
posts a reply, sends a message, uploads a file, or writes to your calendar. The Canvas
routes are a fixed list in `canvas.py`; course ids are checked against your enabled
courses on every call; grade requests are scoped to `self`; and downloads are checked
against SSRF rules on every redirect.

Text from your course documents is passed to the AI app as *evidence*, in a labelled
block marked untrusted. A document that contains instructions cannot change what any
tool does — the tool surface is fixed before any document is read.

## Questions worth asking

**Is this allowed?** You are using your own access token to read your own courses on
your own machine, which is what personal access tokens are for. OpenMind never asks for
anyone else's credentials and never operates a shared service.

**Can my instructor see this?** No. OpenMind makes the same read requests bCourses
serves to your browser.

**What if I stop using it?** Run `openmind clear --all`, uninstall the package, and
delete the token in bCourses. Nothing remains anywhere else, because there is nowhere
else.
