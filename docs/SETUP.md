# Setup

Five minutes, three steps: install, connect your bCourses account, tell your AI app
where to find it.

## Before you start

- **Python 3.11 or newer.** `python3 --version` to check.
- **A desktop AI app that supports local MCP servers**: Claude Desktop, Claude Code,
  Cursor, or the ChatGPT desktop app. The web and mobile versions of these apps cannot
  run a local server — this has to be a program on your computer.
- **A bCourses account.** That's it. No OpenMind account exists.

## 1. Install

```bash
uv tool install openmind-berkeley
```

Or with pipx:

```bash
pipx install openmind-berkeley
```

Or run it without installing anything permanently:

```bash
uvx --from openmind-berkeley openmind setup
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
- lists your active courses and asks which ones to share. **Courses you leave out are
  invisible to every tool**, so leave out anything you would rather your AI app not see;
- builds a local index of the public Berkeley course catalog, for course planning.

Course *materials* — slides, readings, pages — are **not** stored unless you ask. See
step 4.

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

In settings, add a local (STDIO) MCP server with the command `openmind mcp` printed.
Local MCP support varies by plan — if you don't see the option, check your plan's
documentation.

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
