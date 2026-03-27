# OpenMind Website — Typography Knowledge Base

## Dark Mode Typography Rules

### Contrast Ratios (WCAG 2.2 AA)
- Body text: minimum **4.5:1** against background
- Large text (18px+ bold or 24px+ regular): minimum **3:1**
- Pure white on pure black is too harsh — use off-white (#E8E8ED) on near-black (#09090b)

### Our Background: #09090b
| Role | Color | Contrast | WCAG |
|------|-------|----------|------|
| Headings | #fafafa | 19.1:1 | Pass |
| Body text | #d4d4d8 (zinc-300) | 13.5:1 | Pass |
| Secondary text | #a1a1aa (zinc-400) | 7.8:1 | Pass |
| Muted/captions | #71717a (zinc-500) | 4.1:1 | Borderline — only for large text |
| Cal Gold | #FDB515 | 11.2:1 | Pass |
| OLD muted #52525b | ~~2.6:1~~ | **FAIL** — unreadable |

### Font Sizes (dark mode adjustments)
- Body text: **16px minimum** (1rem). Increase by 1-2px over light mode.
- Small text: **13px minimum** for anything that must be read (not decorative)
- Nav links: **14px minimum**
- Captions/labels: **12px** only if contrast is 7:1+

### Font Weight
- Body: **400** (regular) — avoid thin/light weights, they disappear on dark backgrounds
- Headings: **700-900** — bold enough to anchor the page
- Nav/labels: **500** (medium) — slightly bolder than body for clarity
- Never use font-weight 300 or lighter on dark backgrounds

### Line Height
- Body text: **1.6-1.75** (more generous than light mode)
- Headings: **1.1-1.2**
- Small text: **1.5-1.6**
- Dark mode text feels more compressed — always err toward more line height

### Letter Spacing
- Body: **0 to 0.01em** (default or very slight opening)
- Small text: **0.01-0.02em** (open up for readability)
- ALL CAPS labels: **0.05-0.1em** (wide tracking for uppercase)
- Headings: **-0.02em** (tighten for visual density)

### Font Family
- Sans-serif optimized for screens: **Inter, Geist, SF Pro, IBM Plex**
- Monospace for code: **JetBrains Mono, Fira Code, SF Mono**
- Inter is our choice — it was designed for computer screens with adjustable optical sizing

### Color Rules
- Primary text (#fafafa): headings, important content, interactive elements
- Body text (#d4d4d8): paragraphs, descriptions, readable content
- Secondary (#a1a1aa): nav links, labels, less prominent but still readable
- Muted (#71717a): only for decorative text, timestamps, or large-size captions
- Never use #52525b or darker for text that needs to be read

Sources:
- Material Design 3 type scale
- WCAG 2.2 Level AA contrast requirements
- "Typography in Dark Mode" — Design Shack
- "Dark Mode Font Readability" — RAIS Project
