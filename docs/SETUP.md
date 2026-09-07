# Setup

Five minutes, three steps: install, connect your bCourses account, tell your AI app
where to find it.

## Before you start

- **Python 3.11 or newer.** `python3 --version` to check.
- **A desktop AI app that supports local MCP servers**: Claude Desktop, Claude Code,
  Cursor, or the ChatGPT desktop app. The web and mobile versions of these apps cannot
  run a local server — this has to be a program on your computer.
- **A bCourses account.** That's it. No OpenMind account exists.

## Who can use this

OpenMind is for a UC Berkeley student running their own copy on their own machine with
their own bCourses access token. That is what personal access tokens are for. Your token
is never shared, collected, pooled, or sent anywhere except bCourses; there is no
OpenMind server to send it to, and no OpenMind account exists. If you want a friend to
use it, they install it themselves and generate their own token — never hand yours over,
and never run one instance on someone else's behalf. Canvas asks applications that
operate *on behalf of other people* to use OAuth; this one operates only on behalf of
the person who installed it. The maintainer will ask Berkeley Research, Teaching, and
Learning for guidance on personal-token use and follow whatever comes back.

## 1. Install

```bash
uv tool install git+https://github.com/qazybekb/openmind.git
```

From a checkout of this repository:

```bash
uv tool install .
```

PyPI publication is pending. Once the corrected release is published, either of these
will install it into an isolated environment:

```bash
uv tool install openmind-berkeley
pipx install openmind-berkeley
```

## 2. Connect your bCourses account

```bash
openmind setup
```

You will be asked for a bCourses **access token**. Create one at:

> bCourses → Account → Settings → Approved Integrations → **+ New Access Token**

Give it a purpose ("OpenMind") and leave the expiry blank, or set one — OpenMind will
tell you clearly when a token expires. Copy the token immediately; bCourses shows it
once.

Paste it when asked. Nothing is echoed to the screen, and the token goes straight into
your operating system's credential store — macOS Keychain, Windows Credential Manager,
or the Secret Service on Linux. It is never written into a config file.

Setup then:

- confirms who you are and reads your time zone from your Canvas profile, so deadlines
  come out on the right day;
- lists your active courses and asks which ones to share. bCourses keeps every past
  course "active", so the list runs back years; pressing Enter shares the newest term's
  courses, typing `all` shares everything, and numbers pick exactly. **Courses you leave
  out are invisible to every tool**, so leave out anything you would rather your AI app
  not see. Re-run `openmind setup` any time to change the selection; press Enter at the
  token prompt to keep the token you already stored;
- builds a local index of the public Berkeley course catalog, for course planning.

Course *materials* — slides, readings, pages — are **not** stored unless you ask. See
step 5.

### If your machine has no credential store

Some minimal Linux setups have no Secret Service. Run:

```bash
openmind setup --allow-file-secrets
```

which stores the token in a `0600` file instead, and says so loudly.

## 3. Tell your AI app about it

```bash
openmind mcp
```

This prints copy-paste configuration for each supported app, with the absolute path of
the server. Nothing secret appears in it — the token stays in your credential store.

Or let OpenMind write the config for you:

```bash
openmind mcp --write claude-desktop     # or: cursor, claude-code
```

It backs up the existing file first, merges the `openmind` entry without touching any
other server you have configured, and prints the diff. It will not create a config file
that does not exist unless you add `--yes`.

### Claude Desktop

Open `claude_desktop_config.json`:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Add the block `openmind mcp` printed:

```json
{
  "mcpServers": {
    "openmind": {
      "command": "/absolute/path/to/openmind-mcp"
    }
  }
}
```

Restart Claude Desktop completely (quit, don't just close the window).

### Claude Code

```bash
claude mcp add --scope user openmind -- /absolute/path/to/openmind-mcp
```

### Cursor

Add the same JSON block to `~/.cursor/mcp.json`, then reload Cursor.

### ChatGPT desktop

Open Settings > MCP servers > Add server, choose STDIO, and enter the command
`openmind mcp` printed. Save and restart. See the
[official OpenAI MCP guide](https://learn.chatgpt.com/docs/extend/mcp) for current
desktop configuration; availability in your host must be checked during acceptance.

## 4. Ask a question

```
what's due this week?
```

You should get real deadlines with priorities. If the app says it has no such tool,
restart it — a host only reads its MCP config at launch.

## 5. Optional: make your course materials searchable

By default OpenMind can see the *names* of your files and modules, but not what is
inside them. To search inside slides and readings:

```bash
openmind index --course 1234
```

(`openmind config` lists your course ids, or ask your AI app to call `list_courses`.)

This extracts text from the course's PDFs, slides, pages, and syllabus into a private
`0600` SQLite file on your machine. Nothing is uploaded anywhere by OpenMind. Once a
course is indexed, tutoring and `find_materials` can quote it with page citations.

Undo it at any time:

```bash
openmind index --course 1234 --delete
```

## If something is wrong

```bash
openmind doctor
```

`doctor` checks your Python version, the credential store, whether the token still
works, your time zone, whether each enabled course is reachable, the index size, the
catalog snapshot date, and whether the server starts cleanly. It names what is broken
and what to run.

Common cases:

| Symptom | Fix |
|---|---|
| "Your bCourses token is invalid or expired" | Make a new token in bCourses and run `openmind setup` again |
| The AI app doesn't see the tools | Restart the app completely; check the path in its config is absolute |
| macOS asks for Keychain access after an upgrade | Allow it — `uv tool upgrade` replaces the interpreter, so macOS sees a new program |
| "This course does not share its file list" | The instructor disabled the Files tab; pages and the syllabus are still indexed |
| A PDF says "scanned document, no text layer" | It is an image scan; there is no text to extract. Open it in bCourses |

## Removing it

```bash
openmind clear --all           # delete the index, catalog, config, and stored token
uv tool uninstall openmind-berkeley
```

Then delete the access token in bCourses → Account → Settings → Approved Integrations.
