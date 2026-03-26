"""Tests for config persistence and validation."""

from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openmind import config


class ConfigTests(unittest.TestCase):
    """Verify config safety guarantees."""

    def test_validate_canvas_url_allows_only_berkeley(self) -> None:
        """Allow only trusted Berkeley Canvas hosts."""
        self.assertTrue(config.validate_canvas_url("https://bcourses.berkeley.edu"))
        self.assertTrue(config.validate_canvas_url("https://bcourses.berkeley.edu/"))
        self.assertFalse(config.validate_canvas_url("https://evil.example.com"))
        self.assertFalse(config.validate_canvas_url("https://bcourses.berkeley.edu.evil.example.com"))
        self.assertFalse(config.validate_canvas_url("https://localhost"))

    def test_load_config_returns_empty_for_invalid_json(self) -> None:
        """Ignore malformed config files instead of crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".openmind"
            config_file = config_dir / "config.json"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_file.write_text("{not-json", encoding="utf-8")

            with (
                patch.object(config, "CONFIG_DIR", config_dir),
                patch.object(config, "CONFIG_FILE", config_file),
                patch.object(config.logger, "warning"),
            ):
                self.assertEqual(config.load_config(), {})

    def test_save_config_round_trips_and_restricts_permissions(self) -> None:
        """Write config atomically and lock it down to the current user."""
        payload = {
            "canvas_token": "canvas-token",
            "canvas_url": "https://bcourses.berkeley.edu",
            "openrouter_api_key": "openrouter-key",
            "model": "google/gemini-2.5-pro",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".openmind"
            config_file = config_dir / "config.json"

            with patch.object(config, "CONFIG_DIR", config_dir), patch.object(config, "CONFIG_FILE", config_file):
                config.save_config(payload)

                stored = json.loads(config_file.read_text(encoding="utf-8"))
                self.assertEqual(stored, payload)

                if os.name != "nt":
                    self.assertEqual(stat.S_IMODE(config_dir.stat().st_mode), 0o700)
                    self.assertEqual(stat.S_IMODE(config_file.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
