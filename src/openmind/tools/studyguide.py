"""Generate professional study guide PDFs from course materials.

Uses Claude Opus via OpenRouter for content generation — the most capable
model for deep, structured educational writing. The student's default model
is used for normal chat; Opus is used only for study guide generation.
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Final, TypeAlias

from openmind.config import CONFIG_DIR, ConfigDict

logger = logging.getLogger(__name__)

ToolArgs: TypeAlias = dict[str, Any]
ToolDefinition: TypeAlias = dict[str, Any]

OUTPUT_DIR: Final[Path] = CONFIG_DIR / "study_guides"
OPUS_MODEL: Final[str] = "anthropic/claude-opus-4-6"
# Common pdflatex locations
_PDFLATEX_PATHS: Final[tuple[str, ...]] = (
    "pdflatex",
    "/Library/TeX/texbin/pdflatex",
    "/usr/local/texlive/2026/bin/universal-darwin/pdflatex",
    "/usr/bin/pdflatex",
)

STUDY_GUIDE_TOOLS: list[ToolDefinition] = [
    {
        "type": "function",
        "function": {
            "name": "generate_study_guide",
            "description": (
                "Generate a comprehensive study guide PDF for a course or topic. "
                "This is a LEARNING document — not a cheatsheet. A reader should be able to "
                "pick it up from scratch and learn the entire subject thoroughly.\n\n"
                "Provide: course_name (required), scope (optional, e.g. 'midterm', 'weeks 1-5'), "
                "and source_material (required — the actual course content to cover, from Canvas "
                "modules/lectures/readings. Fetch these BEFORE calling this tool).\n\n"
                "The tool uses Claude Opus to generate the content and compiles to PDF.\n"
                "Output: 10-25 page two-column professional PDF saved to ~/.openmind/study_guides/"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "course_name": {
                        "type": "string",
                        "description": "Course name (e.g. 'Info 205 — Information Law & Policy')",
                    },
                    "scope": {
                        "type": "string",
                        "description": "What to cover: 'midterm', 'final', 'weeks 1-5', 'all' (default: all)",
                    },
                    "source_material": {
                        "type": "string",
                        "description": "The actual course content — lecture notes, readings, module content from Canvas. The more detail, the better the guide.",
                    },
                },
                "required": ["course_name", "source_material"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_cheatsheet",
            "description": (
                "Generate a dense 2-page exam cheatsheet PDF. Unlike a study guide, this is a "
                "REFERENCE document — maximum information in minimum space. Designed to be printed "
                "and brought to an open-note exam.\n\n"
                "Format: 2 columns, 7pt font, ultra-tight margins, no wasted space. "
                "Every concept compressed to 1-2 lines. Key terms in bold. "
                "Includes: frameworks, key definitions, case briefs (1-2 lines each), "
                "comparisons, exam tips, author→concept maps, common mistakes.\n\n"
                "Fetch course materials from Canvas BEFORE calling this tool.\n"
                "Uses Claude Opus. Output: 2-page PDF at ~/.openmind/study_guides/"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "course_name": {
                        "type": "string",
                        "description": "Course name",
                    },
                    "scope": {
                        "type": "string",
                        "description": "What to cover: 'midterm', 'final', etc.",
                    },
                    "source_material": {
                        "type": "string",
                        "description": "Course content from Canvas — lectures, readings, notes.",
                    },
                },
                "required": ["course_name", "source_material"],
            },
        },
    },
]

_LATEX_PREAMBLE = r"""\documentclass[10pt,letterpaper]{article}
\usepackage[margin=0.6in]{geometry}
\usepackage{multicol}
\usepackage{enumitem}
\usepackage{titlesec}
\usepackage{fancyhdr}
\usepackage{xcolor}
\usepackage[hidelinks]{hyperref}

% Colors
\definecolor{calgold}{RGB}{253,181,21}
\definecolor{calblue}{RGB}{0,50,98}
\definecolor{tipbg}{RGB}{255,249,230}
\definecolor{tipborder}{RGB}{200,160,50}

% Compact spacing
\setlength{\parindent}{0pt}
\setlength{\parskip}{3pt}
\setlength{\columnsep}{18pt}
\setlist[itemize]{noitemsep,topsep=2pt,leftmargin=*}
\setlist[enumerate]{noitemsep,topsep=2pt,leftmargin=*}

% Section formatting
\titleformat{\section}{\large\bfseries}{\thesection}{1em}{}
\titleformat{\subsection}{\normalsize\bfseries}{\thesubsection}{0.8em}{}
\titleformat{\subsubsection}{\small\bfseries}{\thesubsubsection}{0.6em}{}
\titlespacing*{\section}{0pt}{10pt}{4pt}
\titlespacing*{\subsection}{0pt}{8pt}{3pt}
\titlespacing*{\subsubsection}{0pt}{6pt}{2pt}

% Exam tip boxes (works without tcolorbox)
\newenvironment{examtip}{%
  \par\smallskip\noindent\colorbox{tipbg}{\parbox{\dimexpr\columnwidth-2\fboxsep}{%
  \small\textbf{EXAM TIP:} \ignorespaces}}%
  \par\noindent\fbox{\parbox{\dimexpr\columnwidth-2\fboxsep}{\small\ignorespaces}}}{}

% Core concept boxes
\newenvironment{corebox}[1][Core Argument]{%
  \par\smallskip\noindent\fcolorbox{calblue}{white}{\parbox{\dimexpr\columnwidth-2\fboxsep-2\fboxrule}{%
  \small\textbf{#1}\par\smallskip\ignorespaces}}}{}

% Header
\pagestyle{fancy}
\fancyhf{}
\rfoot{\small\thepage}
\renewcommand{\headrulewidth}{0pt}
"""

_CHEATSHEET_PREAMBLE = r"""\documentclass[8pt,twocolumn]{article}
\usepackage{times}
\usepackage{latexsym}
\usepackage{amsmath,amssymb}
\usepackage{enumitem}
\usepackage{titlesec}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[hidelinks]{hyperref}

% Ultra-tight margins for cheatsheet
\usepackage[letterpaper,top=0.55cm,bottom=0.55cm,left=0.65cm,right=0.65cm]{geometry}
\setlength{\columnsep}{0.35cm}
\setlength{\parskip}{1pt}
\setlength{\parindent}{0pt}

% Compact sections
\titleformat{\section}{\normalfont\bfseries\footnotesize}{\thesection}{0.3em}{}
\titlespacing*{\section}{0pt}{4pt}{1pt}
\titleformat{\subsection}{\normalfont\bfseries\scriptsize}{\thesubsection}{0.2em}{}
\titlespacing*{\subsection}{0pt}{2pt}{0.5pt}

% Compact lists
\setlist{nosep,leftmargin=0.9em,topsep=0pt,parsep=0pt,partopsep=0pt,itemsep=0.5pt}

\pagestyle{empty}
\raggedbottom
"""

_CHEATSHEET_OPUS_PROMPT = """You are creating an ultra-dense 2-page exam cheatsheet.

This is NOT a study guide. This is a REFERENCE SHEET for an open-note exam.
Every pixel of space matters. The goal: maximum information in exactly 2 pages.

Writing rules:
- Compress every concept to 1-2 lines maximum
- Use bold for key terms, no unnecessary words
- Abbreviate where clear (gov't, req't, etc.)
- Use → for implications, ≈ for equivalences, = for definitions
- Case briefs: Facts (1 line), Holding (1 line), Key point (1 line)
- Frameworks: Name — core idea — key components (all one line if possible)
- Use numbered lists, not paragraphs
- Include: author→concept maps, key comparisons, exam tips, common mistakes
- Include a glossary of key definitions (1 line each)
- NO explanations, NO examples unless critical for the exam
- Every line must be exam-relevant

LaTeX rules:
- Use the provided preamble exactly (8pt, two-column, ultra-tight margins)
- Font: \\fontsize{7.2pt}{8.5pt}\\selectfont at start of document
- Use \\section{} and \\subsection{} for organization
- Use \\textbf{} for key terms, \\textit{} for emphasis
- MUST fit in exactly 2 pages — no more, no less

Return ONLY the complete LaTeX document. No commentary."""


def _ensure_output_dir() -> None:
    """Create the study guides directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _find_pdflatex() -> str | None:
    """Find the pdflatex binary."""
    import shutil
    for path in _PDFLATEX_PATHS:
        if path == "pdflatex":
            found = shutil.which("pdflatex")
            if found:
                return found
        elif Path(path).exists():
            return path
    return None


def _compile_latex(latex_content: str, title: str, pdflatex_bin: str = "pdflatex") -> str | None:
    """Compile LaTeX to PDF. Returns the output path or None on failure."""
    _ensure_output_dir()

    # Sanitize filename
    safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)
    safe_title = safe_title.strip().replace(" ", "_")[:80]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"{safe_title}_{timestamp}"

    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = Path(tmpdir) / f"{filename}.tex"
        tex_path.write_text(latex_content, encoding="utf-8")

        # Try pdflatex (2 passes for ToC/references)
        for _pass in range(2):
            result = subprocess.run(
                [pdflatex_bin, "-interaction=nonstopmode", "-halt-on-error", str(tex_path)],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0 and _pass == 1:
                logger.warning("LaTeX compilation failed:\n%s", result.stdout[-2000:])
                return None

        pdf_path = Path(tmpdir) / f"{filename}.pdf"
        if not pdf_path.exists():
            return None

        # Copy to output directory
        output_path = OUTPUT_DIR / f"{filename}.pdf"
        output_path.write_bytes(pdf_path.read_bytes())
        return str(output_path)


_OPUS_SYSTEM_PROMPT = """You are an expert educator creating a comprehensive study guide.

Your goal: produce a document that a student can read from scratch and LEARN the entire subject.
This is NOT a cheatsheet or reference card. This is a teaching document.

Writing principles:
- EXPLAIN concepts thoroughly — assume the reader is encountering them for the first time
- Use concrete examples for every abstract idea
- Show the reasoning behind conclusions, not just the conclusions
- Connect ideas across topics — show how they relate and build on each other
- Include "why this matters" for every concept
- Add exam tips, common mistakes, and practice questions throughout
- Use analogies to make complex ideas accessible
- Bold key terms on first use and define them clearly

Structure: Adapt to the subject. Do NOT use a fixed template. Consider:
- Law/policy: Frameworks & theories → Case analysis → Cross-cutting themes → Exam prep
- CS/engineering: Core concepts → Algorithms with examples → Code patterns → Problem-solving strategies
- Business: Foundational theories → Analytical frameworks → Case applications → Strategic thinking
- Sciences: Fundamental principles → Methods & experiments → Quantitative tools → Problem sets
- Humanities: Key thinkers & arguments → Thematic analysis → Critical connections → Essay preparation

Always end with: key comparisons/contrasts, common exam mistakes, glossary of terms.

LaTeX formatting:
- Full document with \\documentclass[10pt,letterpaper]{article}
- Two-column layout with \\usepackage{multicol}, \\begin{multicols}{2}
- Use the provided preamble (tcolorbox for exam tips, section/subsection hierarchy)
- Tables for comparisons, itemize for lists, bold for key terms
- Target 10-25 pages of dense, high-quality content
- Every section should TEACH, not just list

Return ONLY the complete LaTeX document. No commentary outside the LaTeX."""


def _generate_content_with_opus(cfg: ConfigDict, course_name: str, scope: str, source_material: str, *, cheatsheet: bool = False) -> str | None:
    """Call Claude Opus via OpenRouter to generate LaTeX content."""
    api_key = str(cfg.get("openrouter_api_key", ""))
    if not api_key:
        return None

    try:
        from openai import OpenAI

        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            timeout=300.0,  # 5 min — Opus needs time for long content
        )

        scope_text = f" (scope: {scope})" if scope else ""

        if cheatsheet:
            system_prompt = _CHEATSHEET_OPUS_PROMPT
            preamble = _CHEATSHEET_PREAMBLE
            max_tokens = 8000
            instruction = (
                f"Create an ultra-dense 2-page cheatsheet for: {course_name}{scope_text}\n\n"
                f"Use this LaTeX preamble (copy it exactly):\n{preamble}\n"
                f"\\begin{{document}}\n"
                f"\\fontsize{{7.2pt}}{{8.5pt}}\\selectfont\n\n"
                f"Source material:\n\n{source_material[:80000]}\n\n"
                f"Generate the complete LaTeX document. MUST fit in exactly 2 pages."
            )
        else:
            system_prompt = _OPUS_SYSTEM_PROMPT
            preamble = _LATEX_PREAMBLE
            max_tokens = 16000
            instruction = (
                f"Create a comprehensive study guide for: {course_name}{scope_text}\n\n"
                f"Use this LaTeX preamble (copy it exactly as the start of your document):\n"
                f"{preamble}\n"
                f"\\begin{{document}}\n\n"
                f"Now here is the source material from the course. Use ALL of it:\n\n"
                f"{source_material[:80000]}\n\n"
                f"Generate the complete LaTeX document now. Remember: this must TEACH, not just list."
            )

        response = client.chat.completions.create(
            model=OPUS_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": instruction},
            ],
            max_tokens=max_tokens,
        )

        if not response.choices:
            return None

        content = response.choices[0].message.content or ""
        return content.strip()

    except Exception:
        logger.exception("Failed to generate study guide content with Opus")
        return None


def execute_study_guide_tool(name: str, args: ToolArgs, cfg: ConfigDict) -> str:
    """Execute study guide or cheatsheet generation."""
    if name not in ("generate_study_guide", "generate_cheatsheet"):
        return json.dumps({"error": f"Unknown tool: {name}"})

    course_name = str(args.get("course_name", "")).strip()
    scope = str(args.get("scope", "")).strip()
    source_material = str(args.get("source_material", "")).strip()

    if not course_name:
        return json.dumps({"error": "Missing required argument: course_name."})
    if not source_material:
        return json.dumps({"error": "Missing required argument: source_material. Fetch course content from Canvas first (modules, lectures, readings)."})

    # Check if pdflatex is available
    pdflatex_bin = _find_pdflatex()
    if not pdflatex_bin:
        return json.dumps({
            "error": "pdflatex is not installed. Install LaTeX: brew install --cask basictex (macOS) or apt install texlive (Linux). Then: sudo tlmgr install tcolorbox environ etoolbox pgf"
        })

    # Generate content with Opus
    is_cheatsheet = name == "generate_cheatsheet"
    doc_type = "cheatsheet" if is_cheatsheet else "study guide"
    logger.info("Generating %s with Claude Opus for: %s", doc_type, course_name)
    latex_content = _generate_content_with_opus(cfg, course_name, scope, source_material, cheatsheet=is_cheatsheet)

    if not latex_content:
        return json.dumps({"error": "Failed to generate study guide content. Check your OpenRouter API key and try again."})

    # Clean up — extract just the LaTeX if Opus wrapped it in markdown code blocks
    if "```latex" in latex_content:
        latex_content = latex_content.split("```latex", 1)[1].rsplit("```", 1)[0]
    elif "```" in latex_content:
        latex_content = latex_content.split("```", 1)[1].rsplit("```", 1)[0]

    # If Opus didn't include the preamble, prepend it
    if r"\documentclass" not in latex_content:
        preamble = _CHEATSHEET_PREAMBLE if is_cheatsheet else _LATEX_PREAMBLE
        latex_content = preamble + r"\begin{document}" + "\n" + latex_content + "\n" + r"\end{document}"

    label = "Cheatsheet" if is_cheatsheet else "Study Guide"
    title = f"{course_name} — {scope.capitalize() + ' ' if scope else ''}{label}"
    output_path = _compile_latex(latex_content, title, pdflatex_bin=pdflatex_bin)

    if output_path is None:
        # Save the raw LaTeX for debugging
        debug_path = OUTPUT_DIR / "last_failed.tex"
        try:
            _ensure_output_dir()
            debug_path.write_text(latex_content, encoding="utf-8")
        except OSError:
            pass
        return json.dumps({
            "error": f"LaTeX compilation failed. Raw LaTeX saved to {debug_path} for debugging."
        })

    return json.dumps({
        "result": f"Study guide generated: {title}",
        "path": output_path,
        "message": f"Your study guide is ready! Open it at: {output_path}",
        "model": OPUS_MODEL,
    })
