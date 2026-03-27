"""Generate professional study guide PDFs from course materials."""

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

STUDY_GUIDE_TOOLS: list[ToolDefinition] = [
    {
        "type": "function",
        "function": {
            "name": "generate_study_guide",
            "description": (
                "Generate a professional two-column PDF study guide for a course or topic. "
                "The student provides the course name and optional scope (e.g. 'midterm', 'final', 'weeks 1-5'). "
                "You must provide the full LaTeX content — the tool handles compilation to PDF.\n\n"
                "IMPORTANT: Generate comprehensive, detailed content. Aim for 10-25 pages.\n\n"
                "LaTeX format rules:\n"
                "- Use \\documentclass[10pt,letterpaper]{article}\n"
                "- Use \\usepackage{multicol} with \\begin{multicols}{2}\n"
                "- Use \\section{}, \\subsection{}, \\subsubsection{} for hierarchy\n"
                "- Use \\textbf{} for key terms, \\textit{} for emphasis\n"
                "- Use \\begin{tcolorbox} for exam tips and key concepts\n"
                "- Use itemize/enumerate for lists\n"
                "- Use \\begin{tabular} for comparison tables\n"
                "- Structure should adapt to the subject (not fixed — CS, law, business, etc. all differ)\n\n"
                "Adapt the structure to the subject:\n"
                "- Law/policy: Frameworks → Cases → Synthesis → Exam Prep\n"
                "- CS/engineering: Concepts → Algorithms → Code Patterns → Problem Sets\n"
                "- Business: Theories → Frameworks → Case Studies → Application\n"
                "- Science: Principles → Methods → Key Experiments → Problem Solving\n"
                "- Humanities: Themes → Key Authors → Analysis → Essay Prep\n\n"
                "Always include: exam tips, key comparisons, common mistakes, glossary."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Study guide title (e.g. 'Info 205 — Midterm Study Guide')",
                    },
                    "latex_content": {
                        "type": "string",
                        "description": (
                            "Complete LaTeX document content starting from \\documentclass. "
                            "Must be a full compilable LaTeX document. 10-25 pages recommended."
                        ),
                    },
                },
                "required": ["title", "latex_content"],
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
\usepackage{tcolorbox}
\usepackage{tabularx}
\usepackage{hyperref}

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

% Exam tip boxes
\newtcolorbox{examtip}{
    colback=tipbg,colframe=tipborder,
    fonttitle=\small\bfseries,title=EXAM TIP,
    boxrule=0.5pt,arc=2pt,left=4pt,right=4pt,top=2pt,bottom=2pt
}

% Core concept boxes
\newtcolorbox{corebox}[1][Core Argument]{
    colback=white,colframe=calblue,
    fonttitle=\small\bfseries,title=#1,
    boxrule=0.5pt,arc=2pt,left=4pt,right=4pt,top=2pt,bottom=2pt
}

% Header
\pagestyle{fancy}
\fancyhf{}
\rfoot{\small\thepage}
\renewcommand{\headrulewidth}{0pt}
"""


def _ensure_output_dir() -> None:
    """Create the study guides directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _compile_latex(latex_content: str, title: str) -> str | None:
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
                ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", str(tex_path)],
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


def execute_study_guide_tool(name: str, args: ToolArgs, cfg: ConfigDict) -> str:
    """Execute the study guide generation tool."""
    if name != "generate_study_guide":
        return json.dumps({"error": f"Unknown tool: {name}"})

    title = str(args.get("title", "")).strip()
    latex_content = str(args.get("latex_content", "")).strip()

    if not title:
        return json.dumps({"error": "Missing required argument: title."})
    if not latex_content:
        return json.dumps({"error": "Missing required argument: latex_content."})

    # Check if pdflatex is available
    try:
        subprocess.run(["pdflatex", "--version"], capture_output=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return json.dumps({
            "error": "pdflatex is not installed. Install LaTeX: brew install --cask mactex-no-gui (macOS) or apt install texlive-full (Linux)."
        })

    # If the LLM didn't include a full document, wrap it with our preamble
    if r"\documentclass" not in latex_content:
        latex_content = _LATEX_PREAMBLE + r"\begin{document}" + "\n" + latex_content + "\n" + r"\end{document}"

    output_path = _compile_latex(latex_content, title)
    if output_path is None:
        return json.dumps({
            "error": "LaTeX compilation failed. The content may have syntax errors. Try simplifying the LaTeX."
        })

    return json.dumps({
        "result": f"Study guide generated: {title}",
        "path": output_path,
        "pages": "Check the PDF for page count",
        "message": f"Your study guide is ready at: {output_path}",
    })
