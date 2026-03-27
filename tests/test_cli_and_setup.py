"""Tests for CLI commands and setup flows."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from typer.testing import CliRunner

from openmind.cli import app
from openmind.setup_wizard import DEFAULT_MODEL, run_first_setup

runner = CliRunner()


class CliTests(unittest.TestCase):
    """Verify the public CLI behavior."""

    def test_help_lists_public_commands(self) -> None:
        """Expose the expected named commands in help output."""
        result = runner.invoke(app, ["--help"])
        self.assertEqual(result.exit_code, 0)
        for command in ("setup", "config", "chat", "profile", "privacy"):
            self.assertIn(command, result.stdout)

    def test_profile_shows_empty_state(self) -> None:
        """Guide the student to setup when the profile is empty."""
        with patch("openmind.tools.profile.load_profile", return_value={}):
            result = runner.invoke(app, ["profile"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("No profile data yet", result.stdout)
        self.assertIn("openmind setup profile", result.stdout)

    def test_privacy_command_mentions_llm_and_external_services(self) -> None:
        """Explain the real privacy boundary in CLI output."""
        result = runner.invoke(app, ["privacy"])
        self.assertEqual(result.exit_code, 0)
        out = result.stdout.lower()
        self.assertIn("no openmind server", out)
        self.assertIn("sent to your llm provider", out)
        self.assertIn("never sent to the llm", out)


class SetupWizardTests(unittest.TestCase):
    """Verify first-run onboarding defaults."""

    def test_run_first_setup_saves_minimal_config(self) -> None:
        """Persist the minimal first-run config and disable optional integrations."""
        university = {
            "name": "UC Berkeley",
            "mascot": "Bear",
            "spirit": "Go Bears!",
            "colors": "Blue Gold",
            "canvas_url": "https://bcourses.berkeley.edu",
        }

        with (
            patch("openmind.setup_wizard.get_university", return_value=university),
            patch("openmind.setup_wizard.load_config", return_value={}),
            patch("openmind.setup_wizard._setup_canvas", return_value=("canvas-token", "Qazy", {"1": "NLP"})),
            patch("openmind.setup_wizard._setup_openrouter_key", return_value="or-key"),
            patch("openmind.setup_wizard.Prompt.ask", return_value="1"),
            patch("openmind.setup_wizard.console.print"),
            patch("openmind.setup_wizard.save_config") as save_config,
        ):
            run_first_setup()

        saved = save_config.call_args.args[0]
        self.assertEqual(saved["canvas_token"], "canvas-token")
        self.assertEqual(saved["user_name"], "Qazy")
        self.assertEqual(saved["courses"], {"1": "NLP"})
        self.assertEqual(saved["openrouter_api_key"], "or-key")
        self.assertEqual(saved["model"], DEFAULT_MODEL)
        for integration in ("telegram", "todoist", "gmail", "calendar", "slack", "obsidian"):
            self.assertEqual(saved[integration], {"enabled": False})


if __name__ == "__main__":
    unittest.main()
