# Contributing to OpenMind

## Getting Started

```bash
git clone https://github.com/qazybekb/openmind.git
cd openmind
pip install -e .
openmind --help
```

The `-e` flag installs in editable mode — your code changes take effect immediately.

## Project Structure

```
src/openmind/
├── cli.py              # Typer CLI — entry point, routes to setup/REPL/bot
├── setup_wizard.py     # Interactive onboarding wizard
├── config.py           # ~/.openmind/config.json management
├── universities.py     # UC Berkeley config + personality data
├── personality.py      # System prompt generation
├── llm.py              # OpenRouter client + tool-calling loop
├── repl.py             # Terminal REPL (prompt_toolkit + rich)
├── bot.py              # Telegram bot + heartbeat launcher
├── heartbeat.py        # Background checks (deadlines, grades, submissions, announcements)
└── tools/
    ├── __init__.py     # Tool registry — loads tools based on config
    ├── canvas.py       # 13 Canvas API tools with pagination
    ├── berkeley.py     # Campus events, library hours, study rooms
    ├── courses.py      # Bundled Berkeley catalog search
    ├── profile.py      # Student profile + resume-derived data
    ├── pdf.py          # PDF download + text extraction
    ├── web.py          # Web fetch + DuckDuckGo search + SSRF protection
    ├── gmail.py        # Gmail search + read (optional)
    ├── slack.py        # Slack search + channel reads (optional)
    ├── calendar.py     # Google Calendar events (optional)
    ├── todoist.py      # Todoist task management (optional)
    └── obsidian.py     # Obsidian vault read/write/search (optional)
```

## Adding a New Tool

1. Create a function and tool definition in the appropriate `tools/*.py` file (or a new file)
2. The tool definition follows the OpenAI function calling schema:

```python
MY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "my_tool_name",
            "description": "What this tool does — the LLM reads this to decide when to call it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "param1": {"type": "string", "description": "What this param is"},
                },
                "required": ["param1"],
            },
        },
    },
]
```

3. Create an executor function:

```python
from typing import Any

from openmind.config import ConfigDict


def execute_my_tool(name: str, args: dict[str, Any], cfg: ConfigDict) -> str:
    if name != "my_tool_name":
        return json.dumps({"error": f"Unknown tool: {name}"})

    param1 = str(args.get("param1", "")).strip()
    if not param1:
        return json.dumps({"error": "Missing required argument: param1."})

    return json.dumps({"result": "..."})
```

4. Register in `tools/__init__.py`:

```python
from openmind.tools.mymodule import MY_TOOLS, execute_my_tool

_TOOL_GROUPS = {
    ...
    "mymodule": (MY_TOOLS, execute_my_tool),
}
```

5. Add to `get_all_tools()` (conditionally if optional):

```python
if cfg.get("mymodule", {}).get("enabled"):
    tools.extend(MY_TOOLS)
```

## Adding Agent Instructions

If your tool needs the LLM to use it in a specific way, add instructions to `personality.py` in the `agent_instructions` string. Follow the existing pattern:

```python
### "My feature"
1. Call my_tool_name with the relevant parameter
2. Process the result
3. Show to user in this format
```

## Code Standards

- Python 3.11+
- No unnecessary dependencies — check if httpx/stdlib can do it first
- All external HTTP calls need `timeout=` set
- All tool executors must return JSON strings
- All tool executors must handle errors gracefully — return `{"error": "..."}`, never raise
- Canvas API calls use Bearer auth headers, never URL query params
- Keep the Berkeley personality authentic — reference real places, use real slang

## Security Checklist

Before submitting:

- [ ] No secrets in code (tokens, keys, passwords)
- [ ] External URL tools check `_is_safe_url()` (blocks localhost, private IPs)
- [ ] File system tools check `is_relative_to()` (blocks path traversal)
- [ ] New integrations are read-only by default
- [ ] Optional dependencies are in `[project.optional-dependencies]`, not `dependencies`

## Testing

Run the Python validation suite:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py' -v
ruff check src/openmind tests
python3 -m compileall src/openmind
```

Verify the CLI:

```bash
PYTHONPATH=src python3 -m openmind --help
PYTHONPATH=src python3 -c "from openmind.tools import get_all_tools; print(len(get_all_tools({})))"
PYTHONPATH=src python3 -c "from openmind.tools import get_all_tools; print(len(get_all_tools({'obsidian': {'enabled': True}, 'todoist': {'enabled': True}, 'gmail': {'enabled': True}, 'slack': {'enabled': True}, 'calendar': {'enabled': True}})))"
```

Build the website before changing public-facing copy:

```bash
cd website
npm ci
npm run build
```

## Berkeley Knowledge Base (Phase 1)

We're planning a bundled knowledge base of Berkeley-specific information (campus, safety, health, transit, student life). See `PLAN.md` for details. If you want to contribute knowledge files, they're simple markdown:

```markdown
# SafeWalk

SafeWalk provides free walking escorts on campus.

- **Hours**: 8pm - 2am, every night during the semester
- **Phone**: (510) 642-WALK (9255)
- **App**: BearWalk
- **Coverage**: Anywhere on campus + a few blocks off-campus
```

## Submitting Changes

1. Fork the repo
2. Create a branch: `git checkout -b my-feature`
3. Make your changes
4. Test: unit tests, lint, `python -m openmind --help`, and the website build
5. Commit with a clear message
6. Open a PR describing what you changed and why
