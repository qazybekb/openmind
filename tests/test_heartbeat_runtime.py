"""Runtime-focused tests for heartbeat shutdown behavior."""

from __future__ import annotations

import threading
import unittest
from unittest.mock import patch

from openmind.heartbeat import start_heartbeat


class HeartbeatRuntimeTests(unittest.TestCase):
    """Verify the heartbeat can stop cleanly under service management."""

    def test_start_heartbeat_exits_immediately_when_stop_is_requested(self) -> None:
        """Honor a pre-set stop event so shutdown doesn't block on long sleeps."""
        stop_event = threading.Event()
        stop_event.set()

        with (
            patch("openmind.heartbeat._ensure_private_state_dir"),
            patch("openmind.heartbeat._acquire_heartbeat_lock", return_value=True),
            patch("openmind.heartbeat._release_heartbeat_lock") as release_lock,
            patch("openmind.heartbeat._check_morning_briefing") as check_briefing,
        ):
            start_heartbeat({}, "token", "123", stop_event=stop_event)

        check_briefing.assert_not_called()
        release_lock.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
