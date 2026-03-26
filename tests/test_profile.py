"""Tests for student profile persistence."""

from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openmind.tools import profile


class ProfileTests(unittest.TestCase):
    """Verify profile storage and tool behavior."""

    def setUp(self) -> None:
        """Reset the in-memory profile cache before each test."""
        profile._profile_cache = None

    def tearDown(self) -> None:
        """Reset the in-memory profile cache after each test."""
        profile._profile_cache = None

    def test_save_profile_round_trips_and_restricts_permissions(self) -> None:
        """Write profile data atomically with owner-only permissions."""
        payload = {
            "major": "Computer Science",
            "interests": ["AI", "product"],
            "career_goals": ["AI PM"],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            profile_file = Path(tmpdir) / ".openmind" / "profile.json"

            with patch.object(profile, "PROFILE_FILE", profile_file):
                profile.save_profile(payload)
                stored = json.loads(profile_file.read_text(encoding="utf-8"))
                self.assertEqual(stored, payload)

                if os.name != "nt":
                    self.assertEqual(stat.S_IMODE(profile_file.parent.stat().st_mode), 0o700)
                    self.assertEqual(stat.S_IMODE(profile_file.stat().st_mode), 0o600)

    def test_get_profile_reports_missing_fields(self) -> None:
        """Return missing fields when the profile is incomplete."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_file = Path(tmpdir) / ".openmind" / "profile.json"
            payload = {"major": "Data Science", "interests": ["NLP"]}

            with patch.object(profile, "PROFILE_FILE", profile_file):
                profile.save_profile(payload)
                result = json.loads(profile.execute_profile_tool("get_profile", {}, {}))

        self.assertEqual(result["profile"]["major"], "Data Science")
        self.assertIn("missing_fields", result)
        self.assertIn("level", result["missing_fields"])
        self.assertIn("career_goals", result["missing_fields"])

    def test_import_resume_deduplicates_skills(self) -> None:
        """Merge resume skills without duplicating existing entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_file = Path(tmpdir) / ".openmind" / "profile.json"
            starting_profile = {"resume": {"skills": ["Python", "SQL"]}}

            with patch.object(profile, "PROFILE_FILE", profile_file):
                profile.save_profile(starting_profile)
                result = json.loads(
                    profile.execute_profile_tool(
                        "import_resume",
                        {
                            "resume_text": "Example resume text",
                            "parsed_skills": ["Python", "Machine Learning"],
                            "parsed_projects": ["Study Buddy"],
                        },
                        {},
                    )
                )
                saved = profile.load_profile()

        self.assertEqual(result["result"], "Resume imported to profile.")
        self.assertEqual(saved["resume"]["skills"], ["Python", "SQL", "Machine Learning"])
        self.assertEqual(saved["resume"]["projects"], ["Study Buddy"])


if __name__ == "__main__":
    unittest.main()
