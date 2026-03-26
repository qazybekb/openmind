"""Tests that lock public docs and release claims to runtime behavior."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from openmind.tools import get_all_tools
from openmind.tools.courses import _load_catalog, execute_course_tool

REPO_ROOT = Path(__file__).resolve().parents[1]


class ReleaseContractTests(unittest.TestCase):
    """Keep docs, stats, and public claims aligned with the shipped code."""

    def test_tool_counts_and_names_match_release_contract(self) -> None:
        """Expose the documented core and total tool counts with unique names."""
        core_tools = get_all_tools({})
        full_tools = get_all_tools(
            {
                "obsidian": {"enabled": True},
                "todoist": {"enabled": True},
                "gmail": {"enabled": True},
                "slack": {"enabled": True},
                "calendar": {"enabled": True},
            }
        )

        self.assertEqual(len(core_tools), 25)
        self.assertEqual(len(full_tools), 38)

        names = [tool["function"]["name"] for tool in full_tools]
        self.assertEqual(len(names), len(set(names)))

    def test_tools_reference_matches_registered_tools(self) -> None:
        """Document every registered tool exactly once."""
        tools_doc = (REPO_ROOT / "docs" / "TOOLS.md").read_text(encoding="utf-8")
        documented = {
            match.group(1)
            for match in re.finditer(r"^\| `([^`]+)` \|", tools_doc, flags=re.MULTILINE)
        }
        runtime = {
            tool["function"]["name"]
            for tool in get_all_tools(
                {
                    "obsidian": {"enabled": True},
                    "todoist": {"enabled": True},
                    "gmail": {"enabled": True},
                    "slack": {"enabled": True},
                    "calendar": {"enabled": True},
                }
            )
        }
        self.assertEqual(documented, runtime)

    def test_course_catalog_supports_public_stats(self) -> None:
        """Keep the marketed course counts anchored to the bundled catalog."""
        catalog = _load_catalog()
        self.assertGreaterEqual(len(catalog), 11_000)

        subjects_result = json.loads(execute_course_tool("berkeley_list_subjects", {}, {}))
        self.assertEqual(subjects_result["total_subjects"], 240)

    def test_privacy_copy_avoids_false_local_only_claims(self) -> None:
        """Avoid phrases that would misrepresent the hosted LLM data flow."""
        disallowed_phrases = (
            "all data stays on your machine",
            "api tokens are never transmitted",
        )
        files = (
            REPO_ROOT / "README.md",
            REPO_ROOT / "docs" / "SETUP.md",
            REPO_ROOT / "docs" / "PRIVACY.md",
            REPO_ROOT / "website" / "src" / "components" / "Privacy.astro",
        )

        for path in files:
            text = path.read_text(encoding="utf-8").lower()
            for phrase in disallowed_phrases:
                self.assertNotIn(phrase, text, msg=f"{path} still contains: {phrase}")


if __name__ == "__main__":
    unittest.main()
