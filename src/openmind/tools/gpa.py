"""GPA calculator — compute current GPA and what-if scenarios."""

from __future__ import annotations

import json
import logging
from typing import Any, Final, TypeAlias

import httpx

from openmind.config import ConfigDict

logger = logging.getLogger(__name__)

ToolArgs: TypeAlias = dict[str, Any]
ToolDefinition: TypeAlias = dict[str, Any]

CANVAS_TIMEOUT_S: Final[float] = 30.0

# Standard 4.0 scale
GRADE_POINTS: Final[dict[str, float]] = {
    "A+": 4.0, "A": 4.0, "A-": 3.7,
    "B+": 3.3, "B": 3.0, "B-": 2.7,
    "C+": 2.3, "C": 2.0, "C-": 1.7,
    "D+": 1.3, "D": 1.0, "D-": 0.7,
    "F": 0.0,
}

GPA_TOOLS: list[ToolDefinition] = [
    {
        "type": "function",
        "function": {
            "name": "gpa_calculator",
            "description": (
                "Calculate the student's current GPA from Canvas grades. "
                "Also computes what grade is needed on remaining work to hit a target GPA. "
                "Use this when the student asks 'what's my GPA?', 'what do I need to get an A?', "
                "'can I still get a 3.5?', etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target_gpa": {
                        "type": "number",
                        "description": "Optional target GPA to calculate what's needed (e.g. 3.5)",
                    },
                },
                "required": [],
            },
        },
    },
]


def _score_to_letter(score: float) -> str:
    """Convert a percentage score to a letter grade."""
    if score >= 93:
        return "A"
    if score >= 90:
        return "A-"
    if score >= 87:
        return "B+"
    if score >= 83:
        return "B"
    if score >= 80:
        return "B-"
    if score >= 77:
        return "C+"
    if score >= 73:
        return "C"
    if score >= 70:
        return "C-"
    if score >= 67:
        return "D+"
    if score >= 63:
        return "D"
    if score >= 60:
        return "D-"
    return "F"


def _score_needed_for_letter(target_letter: str) -> float:
    """Return the minimum percentage needed for a letter grade."""
    thresholds = {"A+": 97, "A": 93, "A-": 90, "B+": 87, "B": 83, "B-": 80,
                  "C+": 77, "C": 73, "C-": 70, "D+": 67, "D": 63, "D-": 60, "F": 0}
    return thresholds.get(target_letter, 93)


def execute_gpa_tool(name: str, args: ToolArgs, cfg: ConfigDict) -> str:
    """Execute the GPA calculator tool."""
    if name != "gpa_calculator":
        return json.dumps({"error": f"Unknown GPA tool: {name}"})

    canvas_url = str(cfg.get("canvas_url", "")).rstrip("/")
    canvas_token = str(cfg.get("canvas_token", ""))
    courses = cfg.get("courses", {})

    if not canvas_url or not canvas_token or not courses:
        return json.dumps({"error": "Canvas is not configured."})

    target_gpa = args.get("target_gpa")
    headers = {"Authorization": f"Bearer {canvas_token}"}

    course_grades: list[dict[str, Any]] = []
    total_points = 0.0
    total_units = 0

    for course_id, course_name in courses.items():
        try:
            resp = httpx.get(
                f"{canvas_url}/courses/{course_id}/enrollments",
                params={"user_id": "self"},
                headers=headers,
                timeout=CANVAS_TIMEOUT_S,
            )
            if resp.status_code != 200:
                continue

            enrollments = resp.json()
            if not isinstance(enrollments, list):
                continue

            for enrollment in enrollments:
                if not isinstance(enrollment, dict):
                    continue
                grades = enrollment.get("grades", {})
                if not isinstance(grades, dict):
                    continue
                score = grades.get("current_score")
                if score is None:
                    continue

                try:
                    score_f = float(score)
                except (TypeError, ValueError):
                    continue

                letter = _score_to_letter(score_f)
                gp = GRADE_POINTS.get(letter, 0.0)

                course_grades.append({
                    "course": course_name,
                    "score": round(score_f, 1),
                    "letter": letter,
                    "grade_points": gp,
                })

                total_points += gp
                total_units += 1

        except Exception:
            logger.warning("GPA: failed to fetch grades for %s", course_id, exc_info=True)

    if not course_grades:
        return json.dumps({"error": "No grades found."})

    current_gpa = round(total_points / total_units, 2) if total_units else 0.0

    result: dict[str, Any] = {
        "estimated_gpa": current_gpa,
        "courses": course_grades,
        "total_courses": total_units,
        "disclaimer": (
            "This is an ESTIMATE based on Canvas percentages mapped to a standard 4.0 scale. "
            "It assumes equal weight per course and a standard letter-grade cutoff. "
            "Your official GPA may differ based on units, grading basis (P/NP, S/U), "
            "and your department's scale. Check CalCentral for your official GPA."
        ),
    }

    # What-if: what's needed to hit target GPA
    if target_gpa is not None:
        try:
            target = float(target_gpa)
            gap = target - current_gpa
            if gap <= 0:
                result["target_analysis"] = f"You're already above {target}! Current: {current_gpa}"
            else:
                # Find courses where improvement is most achievable
                improvable = []
                for cg in course_grades:
                    needed_gp = cg["grade_points"] + (gap * total_units / max(1, total_units))
                    if needed_gp <= 4.0:
                        for letter, gp in sorted(GRADE_POINTS.items(), key=lambda x: x[1]):
                            if gp >= needed_gp:
                                needed_score = _score_needed_for_letter(letter)
                                if needed_score > cg["score"]:
                                    improvable.append({
                                        "course": cg["course"],
                                        "current": f"{cg['score']}% ({cg['letter']})",
                                        "need": f"{needed_score}% ({letter})",
                                    })
                                break

                result["target_gpa"] = target
                result["gap"] = round(gap, 2)
                result["improvable_courses"] = improvable[:5]
        except (TypeError, ValueError):
            pass

    return json.dumps(result, default=str)
