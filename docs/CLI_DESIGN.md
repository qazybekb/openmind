# CLI Design — Knowledge Base

Comprehensive guide for designing professional command-line interfaces. Based on research from clig.dev, GitHub Copilot CLI engineering blog, Rich library docs, and modern CLI tool analysis (2025-2026).

---

## Core Principles

### 1. Human-First Design
Modern CLIs are designed for humans first, machines second. The terminal should feel like a conversation, not a machine interface.

### 2. Immediate Feedback
Print something to the user in under 100ms. Silence creates the illusion of failure. If a command takes time, show a spinner or progress bar immediately.

### 3. Show, Don't Tell
Use visual formatting (tables, panels, colors) instead of raw text dumps. A colored table is faster to scan than 20 lines of plain text.

### 4. Progressive Disclosure
Show the essentials first. Offer details on request. Don't overwhelm with information on every command.

---

## Output Formatting

### When to Use Each Rich Component

| Component | Use for | Example |
|-----------|---------|---------|
| **Panel** | Framing important information, setup steps, status summaries | Config display, welcome messages |
| **Table** | Structured data with multiple columns | Course list, grades, tool inventory |
| **Text with markup** | Inline emphasis, status indicators | `[bold green]Connected![/]` |
| **Spinner/Status** | Operations that take 1-30 seconds | API calls, file processing |
| **Progress bar** | Operations with known length | Downloading, processing multiple items |
| **Markdown** | Rendering help text, documentation | `--help` output |
| **Rule** | Visual separation between sections | `console.rule("Setup")` |
| **Columns** | Side-by-side information | Before/after comparisons |
| **Tree** | Hierarchical data | File structures, nested config |

### Color Usage

```
Green:   Success, connected, done         ✅
Yellow:  Warning, needs attention          ⚠️
Red:     Error, failed, critical           ❌
Cyan:    Commands, paths, interactive      💡
Dim:     Secondary info, hints, metadata   📝
Bold:    Headings, important labels        📌
```

Rules:
- Respect `NO_COLOR` environment variable
- Detect TTY — skip colors when piped
- Use semantic colors (success/warning/error), not decorative
- Max 4-5 colors total — more creates visual noise
- Bold white for emphasis, dim for de-emphasis

---

## Error Messages

### Bad
```
Error: HTTPStatusError: 401 Unauthorized
```

### Good
```
❌ Canvas token is invalid or expired.

  To fix: go to bCourses → Profile → Settings → + New Access Token
  Then run: openmind setup
```

### Principles
1. **Say what happened** in plain language
2. **Say what the user can do** to fix it
3. **Include the exact command** to run
4. **Don't show stack traces** to end users (log them)
5. **Position the fix at the end** — that's where eyes go

---

## Setup Wizards

### Best Practices

1. **Minimum viable setup first** — Get to value as fast as possible
2. **Validate immediately** — Don't let the user enter 5 things then fail on #1
3. **Show progress** — "Step 1 of 2" or a progress indicator
4. **Defaults for everything** — Press Enter = skip
5. **Celebrate completion** — Emoji, color, "You're ready!"
6. **Show what to do next** — Not just "Done" but "Run: openmind chat"

### Visual Structure (using Rich Panels)

```python
from rich.panel import Panel

console.print(Panel(
    "[bold]Step 1 of 2[/bold] — Connect to bCourses\n\n"
    "Get your token:\n"
    "bCourses → Profile → Settings → + New Access Token",
    title="🐻 OpenMind Setup",
    border_style="yellow",
))
```

### Feedback Patterns

```
Connecting...  → ✅ Connected! Hey Oski 🐻
Validating...  → ✅ 6 courses found
Saving...      → ✅ Config saved to ~/.openmind/
```

Never leave the user with a blank line after "Connecting..." — always resolve it.

---

## REPL Design

### Prompt
- Clear prompt character: `You →` or `> ` or `❯ `
- Show context if useful: current model, course count
- Keep it short — the prompt shouldn't be longer than the answer

### Status Bar (optional)
```
🐻 OpenMind · 6 courses · gemini-2.5-pro
───────────────────────────────────────
You →
```

### Thinking Indicator
```python
with console.status("[dim]Thinking...[/dim]", spinner="dots"):
    response = chat(...)
```

Use `spinner="dots"` — it's the most professional. Avoid `spinner="bouncingBall"` and novelty spinners.

### Response Rendering
- Render LLM responses as Markdown (`rich.markdown.Markdown`)
- Add a blank line before and after the response for breathing room
- Don't add borders/panels around LLM responses — they're already the main content

---

## Command Help

### Structure
```
Usage: openmind [command]

Commands:
  setup     Set up OpenMind or a specific integration
  chat      Start the terminal REPL
  config    Show current configuration
  profile   View your student profile
  privacy   Show what data goes where

Run 'openmind setup --help' for integration-specific help.
```

### Principles
1. **Lead with examples**, not abstract descriptions
2. **Group related commands** visually
3. **Show the most common command first**
4. **Include "Run X for more" breadcrumbs**

---

## Config Display (openmind config)

### Bad
```
canvas_token: sk-...
canvas_url: https://bcourses.berkeley.edu/api/v1
model: google/gemini-2.5-pro
telegram: enabled
gmail: disabled
```

### Good (Rich Panel + Table)
```
┌ OpenMind Configuration ──────────────────┐
│                                           │
│  University:    UC Berkeley               │
│  Model:         google/gemini-2.5-pro     │
│  Courses:       6                         │
│                                           │
│  Integrations:                            │
│    ✅ Telegram    ✅ Gmail                 │
│    ⬚ Calendar    ⬚ Slack                 │
│    ⬚ Todoist     ⬚ Obsidian              │
│                                           │
│  Profile:       ✅ Set up                 │
│                                           │
│  Add more: openmind setup <name>          │
│  Config: ~/.openmind/config.json          │
└───────────────────────────────────────────┘
```

---

## Progress and Loading

### Short operations (1-5 seconds)
Use a spinner:
```python
with console.status("[dim]Checking deadlines...[/dim]", spinner="dots"):
```

### Longer operations (5-30 seconds)
Use a spinner with detail:
```python
with console.status("[dim]Reading 3 PDFs...[/dim]", spinner="dots"):
```

### Multi-step operations
Show each step:
```
  Fetching assignments... ✅
  Checking submissions... ✅
  Checking grades... ✅
  Checking announcements... ✅
```

---

## Notifications and Alerts

### Urgency levels
```
✅ Good news:     Green text
📋 Informational: Default text
⚠️ Warning:       Yellow text
❌ Error:          Red text
🚨 Critical:      Red + bold
```

### Pattern
```python
console.print("[green]✅ Connected![/green] Hey Oski 🐻")
console.print("[yellow]⚠️ Gmail isn't set up yet.[/yellow] Run: [cyan]openmind setup gmail[/cyan]")
console.print("[red]❌ Canvas token expired.[/red] Get a new one in bCourses Settings.")
```

---

## What the Best CLI Tools Do

| Tool | Banner | Colors | Tables | Panels | Progress | Notes |
|------|--------|--------|--------|--------|----------|-------|
| **Claude Code** | ASCII mascot | Semantic | Markdown | No | Spinner | Customizable mascot |
| **GitHub Copilot CLI** | Animated ASCII | 4-bit ANSI | No | No | Animation | 3-second intro |
| **OpenClaw** | ASCII lobster | Brand red | No | No | No | Conversational onboarding |
| **Warp** | Text only | Minimal | Yes | No | Native | Relies on GUI terminal |
| **fzf** | None | Highlight | No | No | No | Pure utility |
| **npm** | Text logo | Green/yellow | No | No | Progress bar | "npm i" feedback |

---

## OpenMind Improvement Opportunities

Based on this research, here's what would have the highest impact:

### Already done ✅
- ASCII banner with brand colors
- Spinner during LLM calls
- Markdown rendering for responses
- Color-coded status messages
- Progressive setup wizard

### Should add next
1. **Rich Panels for setup steps** — frame each step visually
2. **Rich Tables for config/courses/grades** — structured data deserves tables
3. **Status indicators for integrations** — ✅/⬚ instead of text lists
4. **Better error messages** — actionable, with exact fix commands
5. **Rule separators** — `console.rule()` between sections

### Nice to have later
- `openmind --version` with banner
- `NO_COLOR` env var support
- `--json` flag for machine-readable output
- Animated setup completion (brief, <1 second)

---

Sources:
- [clig.dev — Command Line Interface Guidelines](https://clig.dev/)
- [GitHub Blog — Engineering behind Copilot CLI's animated ASCII banner](https://github.blog/engineering/from-pixels-to-characters-the-engineering-behind-github-copilot-clis-animated-ascii-banner/)
- [ArjanCodes — Rich Python Library for Advanced CLI Design](https://arjancodes.com/blog/rich-python-library-for-interactive-cli-tools/)
- [DEV Community — Terminal Renaissance: CLI Tools in 2026](https://dev.to/hassanjan/the-terminal-renaissance-why-cli-tools-are-eating-dev-workflows-in-2026-5a7)
- [Opensource.com — 3 Steps to Awesome CLI UX](https://opensource.com/article/22/7/awesome-ux-cli-application)
- [Rich Documentation](https://rich.readthedocs.io/en/latest/)
