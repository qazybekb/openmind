"""Run background Canvas + Gmail checks and send Telegram notifications."""

from __future__ import annotations

import json
import logging
import os
import stat
import tempfile
import time
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final, TypeAlias

import httpx

from openmind.config import CONFIG_DIR, ConfigDict

logger = logging.getLogger(__name__)

JsonObject: TypeAlias = dict[str, Any]

ANNOUNCEMENT_LOOKBACK_HOURS: Final[int] = 3
EMAIL_LOOKBACK_HOURS: Final[int] = 3
EMAIL_MAX_RESULTS: Final[int] = 10
EMAIL_QUERY: Final[str] = "is:unread from:berkeley.edu newer_than:3h"
CANVAS_TIMEOUT_S: Final[float] = 30.0
DEADLINE_LOOKAHEAD_DAYS: Final[int] = 7
HEARTBEAT_INTERVAL: Final[int] = 3 * 60 * 60
INITIAL_STARTUP_DELAY_S: Final[int] = 30
RECENT_SUBMISSION_WINDOW_HOURS: Final[int] = 24
STATE_DIR: Final[Path] = CONFIG_DIR / "state"
TELEGRAM_API_BASE: Final[str] = "https://api.telegram.org"
TELEGRAM_CHUNK_SIZE: Final[int] = 4_000
TELEGRAM_TIMEOUT_S: Final[float] = 15.0

_URGENCY_ORDER: Final[dict[str, int]] = {"headsup": 0, "reminder": 1, "urgent": 2}


def _ensure_private_state_dir() -> None:
    """Create the heartbeat state directory with owner-only permissions."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(STATE_DIR, stat.S_IRWXU)


def start_heartbeat(cfg: ConfigDict, bot_token: str, chat_id: str) -> None:
    """Run heartbeat checks in a loop."""
    try:
        _ensure_private_state_dir()
    except OSError:
        logger.exception("Failed to prepare heartbeat state directory at %s", STATE_DIR)
        return

    time.sleep(INITIAL_STARTUP_DELAY_S)

    while True:
        try:
            notifications: list[str] = []
            notifications.extend(_check_deadlines(cfg))
            notifications.extend(_check_submissions(cfg))
            notifications.extend(_check_grades(cfg))
            notifications.extend(_check_announcements(cfg))
            notifications.extend(_check_emails(cfg))
            notifications.extend(_check_reminders())

            if notifications:
                summary = "\n\n".join(notifications)
                if _should_notify(summary):
                    _send_telegram(bot_token, chat_id, summary)
        except Exception:
            logger.exception("Heartbeat cycle failed")

        time.sleep(HEARTBEAT_INTERVAL)


def _canvas_get(
    cfg: Mapping[str, Any],
    path: str,
    params: Mapping[str, str] | None = None,
) -> list[JsonObject] | JsonObject:
    """Make an authenticated GET request to the Canvas API."""
    canvas_url = str(cfg.get("canvas_url", "")).rstrip("/")
    canvas_token = str(cfg.get("canvas_token", ""))
    if not canvas_url or not canvas_token:
        raise ValueError("Canvas config is incomplete.")

    response = httpx.get(
        f"{canvas_url}{path}",
        params=params or {},
        headers={"Authorization": f"Bearer {canvas_token}"},
        timeout=CANVAS_TIMEOUT_S,
    )
    response.raise_for_status()

    data = response.json()
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return data
    return {}


def _load_state(name: str) -> JsonObject:
    """Load persisted heartbeat state by name."""
    path = STATE_DIR / f"{name}.json"
    if not path.exists():
        return {}

    try:
        raw_state = path.read_text(encoding="utf-8")
        data = json.loads(raw_state)
    except OSError:
        logger.warning("Failed to read heartbeat state from %s", path, exc_info=True)
        return {}
    except json.JSONDecodeError:
        logger.warning("Failed to parse heartbeat state from %s", path, exc_info=True)
        return {}

    return data if isinstance(data, dict) else {}


def _save_state(name: str, data: Mapping[str, Any]) -> None:
    """Persist heartbeat state by name."""
    path = STATE_DIR / f"{name}.json"
    tmp_path: str | None = None
    try:
        _ensure_private_state_dir()
        payload = json.dumps(dict(data), sort_keys=True)
        fd, tmp_path = tempfile.mkstemp(dir=STATE_DIR, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        tmp_file = Path(tmp_path)
        tmp_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        tmp_file.replace(path)
    except OSError:
        if tmp_path is not None:
            Path(tmp_path).unlink(missing_ok=True)
        logger.warning("Failed to write heartbeat state to %s", path, exc_info=True)


def _parse_canvas_datetime(value: str) -> datetime | None:
    """Parse a Canvas timestamp and return `None` when it is invalid."""
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("Failed to parse Canvas timestamp: %s", value)
        return None


def _normalise_courses(cfg: Mapping[str, Any]) -> dict[str, str]:
    """Return the configured courses as a string-to-string mapping."""
    raw_courses = cfg.get("courses", {})
    if not isinstance(raw_courses, dict):
        return {}

    return {str(course_id): str(course_name) for course_id, course_name in raw_courses.items()}


def _as_float(value: Any) -> float | None:
    """Convert a numeric value to `float` when possible."""
    if isinstance(value, (int, float)):
        return float(value)

    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _check_deadlines(cfg: ConfigDict) -> list[str]:
    """Check for new or escalated deadline notifications."""
    previous_state = _load_state("deadlines")
    events = _canvas_get(cfg, "/users/self/upcoming_events")
    if not isinstance(events, list):
        return []

    now = datetime.now(timezone.utc)
    notifications: list[str] = []
    new_state: dict[str, str] = {}

    for event in events:
        title = str(event.get("title", ""))
        due = str(event.get("end_at") or event.get("start_at") or "")
        assignment = event.get("assignment")
        if not isinstance(assignment, dict):
            continue

        submission = assignment.get("submission", {})
        if not isinstance(submission, dict):
            submission = {}
        if submission.get("workflow_state") in ("submitted", "graded"):
            continue

        due_dt = _parse_canvas_datetime(due)
        if due_dt is None:
            continue

        days = (due_dt - now).total_seconds() / 86400
        if days < 0 or days > DEADLINE_LOOKAHEAD_DAYS:
            continue

        if days <= 1:
            level, emoji = "urgent", "\u26a0\ufe0f"
        elif days <= 3:
            level, emoji = "reminder", "\U0001f4cb"
        else:
            level, emoji = "headsup", "\U0001f4da"

        assignment_id = str(assignment.get("id", ""))
        context_code = str(event.get("context_code", ""))
        key = f"{context_code}:{assignment_id}" if assignment_id else f"{context_code}:{title.strip()}"
        new_state[key] = level

        previous_level = str(previous_state.get(key, ""))
        if not previous_level or _URGENCY_ORDER.get(level, 0) > _URGENCY_ORDER.get(previous_level, -1):
            due_str = due_dt.strftime("%b %d")
            days_str = f"{int(days)}d" if days >= 1 else "TODAY"
            notifications.append(f"{emoji} {title} (due {due_str}, {days_str})")

    _save_state("deadlines", new_state)
    if notifications:
        return ["Deadline update \U0001f43b\n" + "\n".join(notifications)]
    return []


def _check_submissions(cfg: ConfigDict) -> list[str]:
    """Check for assignments due in the last 24 hours — submitted or not."""
    courses = _normalise_courses(cfg)
    seen_raw = _load_state("submissions").get("seen", [])
    seen = {str(item) for item in seen_raw} if isinstance(seen_raw, list) else set()
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=RECENT_SUBMISSION_WINDOW_HOURS)
    alerts: list[str] = []
    new_seen = set(seen)

    for course_id, course_name in courses.items():
        try:
            assignments = _canvas_get(
                cfg,
                f"/courses/{course_id}/assignments",
                {
                    "include[]": "submission",
                    "order_by": "due_at",
                    "per_page": "100",
                },
            )
            if not isinstance(assignments, list):
                continue

            for assignment in assignments:
                due_dt = _parse_canvas_datetime(str(assignment.get("due_at", "")))
                if due_dt is None or not (window_start <= due_dt <= now):
                    continue

                assignment_id = str(assignment.get("id", ""))
                key = f"{course_id}:{assignment_id}"
                if key in seen:
                    continue
                new_seen.add(key)

                submission = assignment.get("submission", {})
                if not isinstance(submission, dict):
                    submission = {}

                submitted = submission.get("workflow_state") in ("submitted", "graded")
                assignment_name = str(assignment.get("name", "?"))
                if submitted:
                    alerts.append(f"\u2705 {course_name} \u2014 {assignment_name}: Submitted!")
                else:
                    alerts.append(f"\U0001f6a8 {course_name} \u2014 {assignment_name}: NOT submitted!")
        except Exception:
            logger.warning("Submission check failed for %s", course_name, exc_info=True)

    _save_state("submissions", {"seen": sorted(new_seen)})
    if alerts:
        return ["Submission check \U0001f43b\n" + "\n".join(alerts)]
    return []


def _check_grades(cfg: ConfigDict) -> list[str]:
    """Check for grade changes since the last heartbeat."""
    courses = _normalise_courses(cfg)
    previous_state = _load_state("grades")
    current: dict[str, JsonObject] = {}

    for course_id, course_name in courses.items():
        try:
            enrollments = _canvas_get(cfg, f"/courses/{course_id}/enrollments", {"user_id": "self"})
            if not isinstance(enrollments, list):
                continue

            for enrollment in enrollments:
                grades = enrollment.get("grades", {})
                if not isinstance(grades, dict):
                    continue

                score = _as_float(grades.get("current_score"))
                if score is not None:
                    current[course_id] = {"score": score, "name": course_name}
        except Exception:
            logger.warning("Grade check failed for %s", course_name, exc_info=True)

    _save_state("grades", current)

    changes: list[str] = []
    for course_id, data in current.items():
        previous_entry = previous_state.get(course_id, {})
        previous_score = previous_entry.get("score") if isinstance(previous_entry, dict) else previous_entry
        previous_value = _as_float(previous_score)
        current_score = _as_float(data.get("score"))
        if previous_value is None or current_score is None or current_score == previous_value:
            continue

        diff = current_score - previous_value
        arrow = "\U0001f4c8" if diff > 0 else "\U0001f4c9"
        sign = "+" if diff >= 0 else ""
        changes.append(f"{arrow} {data['name']}: {current_score}% ({sign}{diff:.1f}%)")

    if changes:
        return ["Grade update \U0001f43b\n" + "\n".join(changes)]
    return []


def _check_announcements(cfg: ConfigDict) -> list[str]:
    """Check for new announcements posted in the last 3 hours."""
    courses = _normalise_courses(cfg)
    seen_raw = _load_state("announcements").get("seen", [])
    seen = {str(item) for item in seen_raw} if isinstance(seen_raw, list) else set()
    context_codes = [f"course_{course_id}" for course_id in courses]
    if not context_codes:
        return []

    canvas_url = str(cfg.get("canvas_url", "")).rstrip("/")
    canvas_token = str(cfg.get("canvas_token", ""))
    if not canvas_url or not canvas_token:
        return []

    params: list[tuple[str, str]] = [("per_page", "20")]
    params.extend(("context_codes[]", context_code) for context_code in context_codes)

    try:
        response = httpx.get(
            f"{canvas_url}/announcements",
            params=params,
            headers={"Authorization": f"Bearer {canvas_token}"},
            timeout=CANVAS_TIMEOUT_S,
        )
        response.raise_for_status()
        announcements = response.json()
        if not isinstance(announcements, list):
            logger.warning("Unexpected announcements response type: %s", type(announcements))
            return []
    except Exception:
        logger.warning("Announcement check failed", exc_info=True)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=ANNOUNCEMENT_LOOKBACK_HOURS)
    new_items: list[str] = []
    all_ids: set[str] = set()

    for announcement in announcements:
        if not isinstance(announcement, dict):
            continue

        announcement_id = str(announcement.get("id", ""))
        all_ids.add(announcement_id)
        if announcement_id in seen:
            continue

        posted_dt = _parse_canvas_datetime(str(announcement.get("posted_at", "")))
        if posted_dt is None or posted_dt < cutoff:
            continue

        title = str(announcement.get("title", ""))
        context_code = str(announcement.get("context_code", ""))
        course_name = courses.get(context_code.replace("course_", ""), "Unknown")
        new_items.append(f"\U0001f4e2 {course_name} \u2014 {title}")

    _save_state("announcements", {"seen": sorted(all_ids)})
    if new_items:
        return ["New announcements \U0001f43b\n" + "\n".join(new_items)]
    return []


def _check_reminders() -> list[str]:
    """Check for due reminders."""
    try:
        from openmind.tools.reminders import get_due_reminders
    except ImportError:
        return []

    due = get_due_reminders()
    if not due:
        return []

    items = [f"\u23f0 {r.get('message', '')}" for r in due]
    return ["Reminders \U0001f43b\n" + "\n".join(items)]


def _should_notify(summary: str) -> bool:
    """Evaluate whether the notification summary is worth sending.

    Filters out low-value notifications to reduce noise. Always notifies for:
    - Urgent deadlines (⚠️)
    - Unsubmitted assignments (🚨)
    - Grade changes (📈/📉)
    Skips if only low-priority items (headsup-level deadlines with no urgency).
    """
    high_priority_markers = ("\u26a0\ufe0f", "\U0001f6a8", "\U0001f4c8", "\U0001f4c9", "\U0001f4e2", "\u2709\ufe0f", "\u23f0")
    for marker in high_priority_markers:
        if marker in summary:
            return True

    # If we only have low-priority headsup items, suppress during quiet hours
    now = datetime.now()
    if 0 <= now.hour < 8:
        logger.info("Suppressing low-priority heartbeat notification during quiet hours")
        return False

    return True


def _check_emails(cfg: ConfigDict) -> list[str]:
    """Check for recent unread emails from berkeley.edu senders."""
    if not cfg.get("gmail", {}).get("enabled"):
        return []

    try:
        from openmind.tools.gmail import _get_gmail_service, _headers_map
    except ImportError:
        return []

    service = _get_gmail_service(cfg)
    if service is None:
        return []

    seen_raw = _load_state("emails").get("seen", [])
    seen = {str(item) for item in seen_raw} if isinstance(seen_raw, list) else set()

    try:
        results = service.users().messages().list(
            userId="me",
            q=EMAIL_QUERY,
            maxResults=EMAIL_MAX_RESULTS,
        ).execute()
        messages = results.get("messages", [])
    except Exception:
        logger.warning("Gmail heartbeat check failed", exc_info=True)
        return []

    new_items: list[str] = []
    all_ids: set[str] = set(seen)

    for msg_ref in messages:
        msg_id = str(msg_ref.get("id", ""))
        if not msg_id or msg_id in seen:
            continue

        all_ids.add(msg_id)

        try:
            msg = service.users().messages().get(
                userId="me",
                id=msg_id,
                format="metadata",
                metadataHeaders=["From", "Subject"],
            ).execute()
        except Exception:
            logger.warning("Failed to fetch email %s", msg_id, exc_info=True)
            continue

        headers = _headers_map(msg.get("payload", {}).get("headers", []))
        sender = headers.get("From", "Unknown")
        subject = headers.get("Subject", "(no subject)")

        # Clean up sender display
        if "<" in sender:
            sender = sender.split("<")[0].strip().strip('"')

        new_items.append(f"\u2709\ufe0f {sender} \u2014 {subject}")

    # Cap seen set to prevent unbounded growth
    if len(all_ids) > 500:
        all_ids = set(sorted(all_ids)[-250:])
    _save_state("emails", {"seen": sorted(all_ids)})

    if new_items:
        return ["New emails from Berkeley \U0001f43b\n" + "\n".join(new_items)]
    return []


def _send_telegram(bot_token: str, chat_id: str, text: str) -> None:
    """Send a message via Telegram Bot API, chunking if needed."""
    for i in range(0, len(text), TELEGRAM_CHUNK_SIZE):
        chunk = text[i : i + TELEGRAM_CHUNK_SIZE]
        try:
            response = httpx.post(
                f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": chunk},
                timeout=TELEGRAM_TIMEOUT_S,
            )
            if response.status_code != 200:
                logger.warning("Telegram send failed with HTTP %d", response.status_code)
        except httpx.HTTPError as exc:
            logger.warning("Failed to send Telegram notification: %s", type(exc).__name__)
