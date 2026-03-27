# ASCII Art & Terminal Branding — Knowledge Base

## Why ASCII Art Matters for CLI Tools

The startup banner is the first thing a user sees. It sets the tone — amateur vs professional, fun vs corporate. Tools like Claude Code, OpenClaw, GitHub Copilot CLI, and Warp all invest in their terminal branding because it creates an emotional connection before the user types anything.

## Best Fonts for Professional CLI Banners

### Recommended Figlet Fonts

| Font | Style | Best for |
|------|-------|----------|
| **ANSI Shadow** | Block letters with shadow depth | Product branding, splash screens |
| **Big Money** | Bold, chunky, high-impact | Headers, major announcements |
| **Slant** | Italic, dynamic, modern | Startup screens, stylish branding |
| **Standard** | Clean, balanced, readable | README headers, inline branding |
| **Small** | Compact, space-efficient | Inline comments, small terminals |
| **Block** | Solid, geometric, retro | Logos, attention-grabbing |
| **3D** | Depth with shadowing | Splash screens, game-like apps |
| **Calvin S** | Small but stylish | When vertical space is limited |

### How to Generate

```bash
# Using pyfiglet (Python)
pip install pyfiglet
python -c "import pyfiglet; print(pyfiglet.figlet_format('OpenMind', font='slant'))"

# Using figlet (system)
brew install figlet
figlet -f slant "OpenMind"
```

## Color Strategy

### Lessons from GitHub Copilot CLI

1. **Semantic colors, not literal** — Map roles (brand, accent, dim) to ANSI colors, not RGB
2. **4-bit ANSI palette** — Works across all terminals, respects user themes
3. **Graceful degradation** — Looks good in both light and dark terminals
4. **Accessibility** — Skip banners in screen-reader mode

### Color Codes for Rich (Python)

| Purpose | Rich Style | Example |
|---------|-----------|---------|
| Brand name | `bold white` | "Open" |
| Accent | `bold yellow` | "Mind" (Cal Gold) |
| Tagline | `dim` | "AI study buddy for UC Berkeley" |
| Version | `dim cyan` | "v0.1.0" |
| Border | `dim white` | Panel borders |

### ANSI Color Safety

- `bold white` + `bold yellow` works on ALL terminal themes
- Never rely on specific RGB — terminals override colors
- `dim` is universally supported for de-emphasized text
- Avoid `bright_black` — it's invisible on some dark terminals

## Design Principles

### From GitHub Copilot CLI's Engineering Blog

1. **Keep it under 3 seconds** — Never delay the user's first interaction
2. **Assume terminal inconsistency** — Test on iTerm, Terminal.app, VS Code, Warp
3. **Accessibility first** — Auto-skip for screen readers, respect `NO_COLOR` env var
4. **Modular layers** — Separate content (text), style (colors), and animation (if any)
5. **Non-blocking** — Never make the user wait for the banner to finish

### Best Practices

1. **Max 6-8 lines tall** — Taller banners push useful content off-screen
2. **Width under 60 characters** — Works on narrow terminal windows
3. **Include version number** — Users need to know what they're running
4. **Include one-line description** — New users need context
5. **Don't animate on every startup** — Show once, then skip (or use `--quiet`)
6. **Match the product's personality** — Playful for a student tool, serious for enterprise

## What the Best CLI Tools Do

### Claude Code
- Static ASCII mascot ("Clawd") with customizable colors
- Compact, recognizable, shows on every startup
- Customizable with arms, hats, color variants

### OpenClaw
- Lobster mascot in ASCII art
- Red color theme matching the brand
- Shows during `openclaw onboard`

### GitHub Copilot CLI
- Animated 3-second banner with the Copilot logo
- Semantic color system (4-bit ANSI)
- Auto-skips for screen readers
- ~20 frames, 11×78 character area

### Warp
- Clean text-based branding, no ASCII art
- Relies on the GUI terminal for visual impact

## Recommended Approach for OpenMind

1. **Font**: `slant` or `small_slant` — modern, fits on one screen
2. **Colors**: "Open" in white, "Mind" in yellow (Cal Gold)
3. **Height**: 6-7 lines max including tagline
4. **Info line**: version + tool count + "Go Bears!"
5. **Show**: On first run and `openmind --version`, skip during normal REPL
6. **Width**: Under 55 characters to fit narrow terminals
7. **Library**: Use `pyfiglet` or hardcode the art (no runtime dependency needed)

## Implementation Note

Hardcoding the ASCII art (not using pyfiglet at runtime) is better because:
- No extra dependency
- Consistent rendering across environments
- Can be precisely colored with Rich markup
- Tested once, works everywhere

Sources:
- [GitHub Blog: Engineering behind Copilot CLI's animated ASCII banner](https://github.blog/engineering/from-pixels-to-characters-the-engineering-behind-github-copilot-clis-animated-ascii-banner/)
- [xero/figlet-fonts — 600+ figlet fonts](https://github.com/xero/figlet-fonts)
- [oh-my-logo — ASCII logos with gradients](https://github.com/shinshin86/oh-my-logo)
- [DEV Community — Make Your Terminal Beautiful with Python](https://dev.to/nish2005karsh/make-your-terminal-beautiful-with-python-ascii-art-fancy-progress-bars--25f7)
