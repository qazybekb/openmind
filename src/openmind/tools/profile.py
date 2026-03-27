"""Student profile management — read, update, and import from resume."""

from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path
from typing import Any, Final, TypeAlias

from openmind.config import ConfigDict, PROFILE_FILE

logger = logging.getLogger(__name__)

ToolArgs: TypeAlias = dict[str, Any]
ToolDefinition: TypeAlias = dict[str, Any]
ProfileDict: TypeAlias = dict[str, Any]

IMPORTANT_FIELDS: Final[list[str]] = [
    "level", "major", "year", "interests", "career_goals",
]

PROFILE_TOOLS: list[ToolDefinition] = [
    {
        "type": "function",
        "function": {
            "name": "get_profile",
            "description": "Get the student's profile — major, interests, career goals, skills, resume data. Returns missing_fields if the profile is incomplete.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_profile",
            "description": "Update a field in the student's profile. Use when the student shares new information about themselves (interests, goals, skills, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "description": "Profile field to update (e.g. 'interests', 'career_goals', 'strengths', 'areas_to_improve', 'dream_companies')",
                    },
                    "value": {
                        "description": "New value for the field (string or list of strings)",
                    },
                },
                "required": ["field", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "import_resume",
            "description": "Parse extracted resume text and save structured data to the student's profile. Call this after reading a resume PDF with read_pdf.",
            "parameters": {
                "type": "object",
                "properties": {
                    "resume_text": {
                        "type": "string",
                        "description": "The raw text extracted from the resume PDF",
                    },
                    "parsed_skills": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Skills extracted from the resume",
                    },
                    "parsed_experience": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "role": {"type": "string"},
                                "company": {"type": "string"},
                                "summary": {"type": "string"},
                            },
                        },
                        "description": "Work experience entries",
                    },
                    "parsed_projects": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Project names or descriptions",
                    },
                    "parsed_education": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Education entries",
                    },
                },
                "required": ["resume_text", "parsed_skills"],
            },
        },
    },
]


_profile_cache: ProfileDict | None = None


def load_profile() -> ProfileDict:
    """Load the student profile, using an in-memory cache when available."""
    global _profile_cache
    if _profile_cache is not None:
        return _profile_cache

    if not PROFILE_FILE.exists():
        return {}
    try:
        data = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
        _profile_cache = data if isinstance(data, dict) else {}
        return _profile_cache
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to load profile from %s", PROFILE_FILE, exc_info=True)
        return {}


def save_profile(profile: ProfileDict) -> None:
    """Save the student profile to disk atomically with owner-only permissions."""
    global _profile_cache
    import tempfile

    PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(PROFILE_FILE.parent, stat.S_IRWXU)
    content = json.dumps(profile, indent=2, ensure_ascii=False)

    fd, tmp_path = tempfile.mkstemp(dir=PROFILE_FILE.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        tmp_file = Path(tmp_path)
        tmp_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        tmp_file.replace(PROFILE_FILE)
        _profile_cache = profile.copy()
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def _json_result(payload: Any) -> str:
    return json.dumps(payload, default=str)


def _error_result(message: str) -> str:
    return _json_result({"error": message})


def _get_missing_fields(profile: ProfileDict) -> list[str]:
    """Return important profile fields that are empty or missing."""
    missing = []
    for field in IMPORTANT_FIELDS:
        val = profile.get(field)
        if not val:
            missing.append(field)
        elif isinstance(val, list) and not any(val):
            missing.append(field)
    return missing


def execute_profile_tool(name: str, args: ToolArgs, cfg: ConfigDict) -> str:
    """Execute a profile tool and return a JSON string."""
    del cfg  # Profile tools don't need config

    try:
        return _execute_profile_tool(name, args)
    except Exception:
        logger.exception("Profile tool '%s' failed unexpectedly", name)
        return _error_result("Profile tool failed unexpectedly.")


def _execute_profile_tool(name: str, args: ToolArgs) -> str:
    if name == "get_profile":
        profile = load_profile()
        missing = _get_missing_fields(profile)
        result: dict[str, Any] = {"profile": profile}
        if missing:
            result["missing_fields"] = missing
            result["hint"] = f"Ask the student about: {', '.join(missing)}. Or suggest: openmind profile"
        return _json_result(result)

    if name == "update_profile":
        field = str(args.get("field", "")).strip()
        value = args.get("value")
        if not field:
            return _error_result("Missing required argument: field.")
        if value is None:
            return _error_result("Missing required argument: value.")

        # Allowlist writable fields to prevent prompt injection via profile
        _ALLOWED_FIELDS = {
            "level", "major", "school", "year", "expected_graduation",
            "interests", "career_goals", "dream_companies", "gpa_goal",
            "strengths", "areas_to_improve", "preferences",
        }
        if field not in _ALLOWED_FIELDS:
            return _error_result(f"Cannot update field '{field}'. Allowed: {', '.join(sorted(_ALLOWED_FIELDS))}")

        # Sanitize string values — strip control characters and cap length
        if isinstance(value, str):
            value = "".join(c for c in value if c.isprintable() or c in "\n\t")
            value = value[:500]
        elif isinstance(value, list):
            value = [str(v)[:200] for v in value[:20]]

        profile = load_profile()
        profile[field] = value
        save_profile(profile)
        return _json_result({"result": f"Updated '{field}' in profile.", "field": field, "value": value})

    if name == "import_resume":
        resume_text = str(args.get("resume_text", ""))
        if not resume_text:
            return _error_result("Missing required argument: resume_text.")

        profile = load_profile()

        # Merge resume data into profile
        skills = args.get("parsed_skills", [])
        if isinstance(skills, list) and skills:
            existing = profile.get("resume", {}).get("skills", []) if isinstance(profile.get("resume"), dict) else []
            merged_skills = list(dict.fromkeys(existing + skills))  # Deduplicate preserving order
            profile.setdefault("resume", {})["skills"] = merged_skills

        experience = args.get("parsed_experience", [])
        if isinstance(experience, list) and experience:
            profile.setdefault("resume", {})["experience"] = experience

        projects = args.get("parsed_projects", [])
        if isinstance(projects, list) and projects:
            profile.setdefault("resume", {})["projects"] = projects

        education = args.get("parsed_education", [])
        if isinstance(education, list) and education:
            profile.setdefault("resume", {})["education"] = education

        save_profile(profile)

        summary = {
            "skills": len(skills),
            "experience": len(experience),
            "projects": len(projects),
            "education": len(education),
        }
        return _json_result({"result": "Resume imported to profile.", "summary": summary})

    return _error_result(f"Unknown profile tool: {name}")
