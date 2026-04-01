"""Run background Canvas + Gmail checks and send Telegram notifications."""

from __future__ import annotations

import json
import logging
import os
import stat
import tempfile
import threading
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final, TypeAlias

import httpx

from openmind.config import CONFIG_DIR, ConfigDict

logger = logging.getLogger(__name__)

JsonObject: TypeAlias = dict[str, Any]

ANNOUNCEMENT_LOOKBACK_HOURS: Final[int] = 3
BRIEFING_HOUR: Final[int] = 8  # 8am PT
EMAIL_LOOKBACK_HOURS: Final[int] = 3
EMAIL_MAX_RESULTS: Final[int] = 10
EMAIL_QUERY: Final[str] = "is:unread from:berkeley.edu newer_than:3h"
CANVAS_TIMEOUT_S: Final[float] = 30.0
DEADLINE_LOOKAHEAD_DAYS: Final[int] = 7
HEARTBEAT_INTERVAL: Final[int] = 3 * 60 * 60
TICK_INTERVAL: Final[int] = 60 * 60  # Check reminders/briefing every hour
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


def _acquire_heartbeat_lock() -> bool:
    """Try to acquire a heartbeat PID lock. Returns False if another instance is running."""
    lock_file = STATE_DIR / "heartbeat.pid"
    try:
        if lock_file.exists():
            try:
                old_pid = int(lock_file.read_text(encoding="utf-8").strip())
                # Check if the process is still alive
                os.kill(old_pid, 0)
                return False  # Another instance is running
            except (ValueError, ProcessLookupError, PermissionError):
                pass  # Old process is dead, safe to take over

        lock_file.write_text(str(os.getpid()), encoding="utf-8")
        return True
    except OSError:
        logger.warning("Could not manage heartbeat lock", exc_info=True)
        return True  # Fail open — better to double-notify than never notify


def _release_heartbeat_lock() -> None:
    """Release the heartbeat PID lock when it belongs to this process."""
    lock_file = STATE_DIR / "heartbeat.pid"
    try:
        if not lock_file.exists():
            return
        if lock_file.read_text(encoding="utf-8").strip() == str(os.getpid()):
            lock_file.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not release heartbeat lock", exc_info=True)


def start_heartbeat(
    cfg: ConfigDict,
    bot_token: str,
    chat_id: str,
    stop_event: threading.Event | None = None,
) -> None:
    """Run heartbeat checks in a loop."""
    stop_signal = stop_event or threading.Event()
    try:
        _ensure_private_state_dir()
    except OSError:
        logger.exception("Failed to prepare heartbeat state directory at %s", STATE_DIR)
        return

    if not _acquire_heartbeat_lock():
        logger.info("Another heartbeat is already running, skipping.")
        return

    try:
        if stop_signal.wait(INITIAL_STARTUP_DELAY_S):
            return

        tick_count = 0
        while not stop_signal.is_set():
            try:
                # Lightweight checks every hour (reminders, briefing)
                briefing = _check_morning_briefing(cfg)
                if briefing:
                    _send_telegram(bot_token, chat_id, briefing)

                reminder_notifications = _check_reminders()
                if reminder_notifications:
                    _send_telegram(bot_token, chat_id, "\n\n".join(reminder_notifications))

                # Full Canvas checks every 3 hours (every 3rd tick)
                if tick_count % 3 == 0:
                    notifications: list[str] = []
                    notifications.extend(_check_deadlines(cfg))
                    notifications.extend(_check_submissions(cfg))
                    notifications.extend(_check_grades(cfg))
                    notifications.extend(_check_announcements(cfg))
                    notifications.extend(_check_emails(cfg))

                    # Auto-sync Canvas deadlines to Todoist + Calendar
                    _sync_deadlines_to_todoist(cfg)
                    _sync_deadlines_to_calendar(cfg)

                    if notifications:
                        summary = "\n\n".join(notifications)
                        if _should_notify(summary):
                            _send_telegram(bot_token, chat_id, summary)
            except Exception:
                logger.exception("Heartbeat cycle failed")

            tick_count += 1
            if stop_signal.wait(TICK_INTERVAL):
                break
    finally:
        _release_heartbeat_lock()


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
    if not value or value == "None":
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        logger.debug("Skipping unparseable Canvas timestamp: %s", value)
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
    courses = _normalise_courses(cfg)
    previous_state = _load_state("deadlines")
    events = _canvas_get(cfg, "/users/self/upcoming_events")
    if not isinstance(events, list):
        return []

    now = datetime.now(timezone.utc)
    notifications: list[str] = []
    deadline_changes: list[str] = []
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
        course_id = context_code.replace("course_", "")
        course_name = courses.get(course_id, "")
        key = f"{context_code}:{assignment_id}" if assignment_id else f"{context_code}:{title.strip()}"
        due_iso = due_dt.isoformat()
        new_state[key] = f"{level}|{due_iso}"

        # Parse previous state (format: "level|due_iso" or just "level" for backwards compat)
        prev_raw = str(previous_state.get(key, ""))
        if "|" in prev_raw:
            previous_level, prev_due_iso = prev_raw.split("|", 1)
        else:
            previous_level = prev_raw
            prev_due_iso = ""

        # Check for deadline date changes
        if prev_due_iso and prev_due_iso != due_iso:
            prev_due_dt = _parse_canvas_datetime(prev_due_iso)
            if prev_due_dt:
                old_str = prev_due_dt.strftime("%b %d")
                new_str = due_dt.strftime("%b %d")
                diff_days = (due_dt - prev_due_dt).total_seconds() / 86400
                prefix = f"{course_name} \u2014 {title}" if course_name else title
                if diff_days > 0:
                    deadline_changes.append(f"\U0001f4c5 {prefix}: {old_str} \u2192 {new_str} (extended {int(diff_days)}d)")
                else:
                    deadline_changes.append(f"\U0001f4c5 {prefix}: {old_str} \u2192 {new_str} (moved earlier by {int(abs(diff_days))}d)")

        # Check for urgency escalation
        if not previous_level or _URGENCY_ORDER.get(level, 0) > _URGENCY_ORDER.get(previous_level, -1):
            due_str = due_dt.strftime("%b %d")
            days_str = f"{int(days)}d" if days >= 1 else "TODAY"
            if course_name:
                notifications.append(f"{emoji} {course_name} \u2014 {title} (due {due_str}, {days_str})")
            else:
                notifications.append(f"{emoji} {title} (due {due_str}, {days_str})")

    _save_state("deadlines", new_state)
    results: list[str] = []
    if deadline_changes:
        results.append("Deadline changed \U0001f43b\n" + "\n".join(deadline_changes))
    if notifications:
        results.append("Deadline update \U0001f43b\n" + "\n".join(notifications))
    return results


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
        # Show letter grade alongside percentage
        if current_score >= 93:
            letter = "A"
        elif current_score >= 90:
            letter = "A-"
        elif current_score >= 87:
            letter = "B+"
        elif current_score >= 83:
            letter = "B"
        elif current_score >= 80:
            letter = "B-"
        elif current_score >= 77:
            letter = "C+"
        elif current_score >= 70:
            letter = "C"
        else:
            letter = "D"
        changes.append(f"{arrow} {data['name']}: {letter} ({current_score}%, {sign}{diff:.1f}%)")

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


def _check_morning_briefing(cfg: ConfigDict) -> str:
    """Build and return a morning briefing if it's ~8am and hasn't been sent today."""
    try:
        from zoneinfo import ZoneInfo
        now_pt = datetime.now(ZoneInfo("America/Los_Angeles"))
    except ImportError:
        now_pt = datetime.now()

    # Only send between 8:00-8:59am (heartbeat runs every 3h, so we'll hit this window once)
    if now_pt.hour != BRIEFING_HOUR:
        return ""

    # Check if already sent today
    state = _load_state("briefing")
    last_date = state.get("last_date", "")
    today = now_pt.strftime("%Y-%m-%d")
    if last_date == today:
        return ""

    # Build the briefing
    user_name = cfg.get("user_name", "Bear")
    day_name = now_pt.strftime("%A")
    lines = [f"\u2600\ufe0f Good morning {user_name}! Here's your {day_name}:\n"]

    # Deadlines
    now_utc = datetime.now(timezone.utc)
    try:
        events = _canvas_get(cfg, "/users/self/upcoming_events")
        if isinstance(events, list):
            today_items: list[str] = []
            week_items: list[str] = []
            for event in events:
                assignment = event.get("assignment")
                if not isinstance(assignment, dict):
                    continue
                submission = assignment.get("submission", {})
                if isinstance(submission, dict) and submission.get("workflow_state") in ("submitted", "graded"):
                    continue
                title = str(event.get("title", ""))
                due = str(event.get("end_at") or event.get("start_at") or "")
                due_dt = _parse_canvas_datetime(due)
                if due_dt is None:
                    continue
                days = (due_dt - now_utc).total_seconds() / 86400
                due_str = due_dt.strftime("%a, %b %d")
                if 0 <= days <= 1:
                    today_items.append(f"  \U0001f6a8 {title} (due TODAY)")
                elif 1 < days <= 7:
                    week_items.append(f"  \U0001f4cb {title} (due {due_str})")

            if today_items:
                lines.append("\U0001f4cc Due today:")
                lines.extend(today_items)
            else:
                lines.append("\U0001f4cc Nothing due today \u2014 you're clear!")

            if week_items:
                lines.append("\n\U0001f4da Coming this week:")
                lines.extend(week_items)
    except Exception:
        logger.warning("Briefing: failed to fetch deadlines", exc_info=True)

    # Grades summary — just count courses and flag any below 80%
    try:
        courses = _normalise_courses(cfg)
        low_grades: list[str] = []
        for course_id, course_name in courses.items():
            enrollments = _canvas_get(cfg, f"/courses/{course_id}/enrollments", {"user_id": "self"})
            if not isinstance(enrollments, list):
                continue
            for enrollment in enrollments:
                if not isinstance(enrollment, dict):
                    continue
                score = _as_float(enrollment.get("grades", {}).get("current_score"))
                if score is not None and score < 80:
                    low_grades.append(f"  \u26a0\ufe0f {course_name}: {score:.0f}%")
        if low_grades:
            lines.append("\n\U0001f4ca Grades needing attention:")
            lines.extend(low_grades)
    except Exception:
        logger.warning("Briefing: failed to fetch grades", exc_info=True)

    # Unread emails count
    if cfg.get("gmail", {}).get("enabled"):
        try:
            from openmind.tools.gmail import _get_gmail_service
            service = _get_gmail_service(cfg)
            if service:
                result = service.users().messages().list(
                    userId="me", q="is:unread from:berkeley.edu", maxResults=1
                ).execute()
                count = result.get("resultSizeEstimate", 0)
                if count:
                    lines.append(f"\n\u2709\ufe0f {count} unread Berkeley email{'s' if count != 1 else ''}")
        except Exception:
            pass

    from openmind.universities import spirit
    lines.append(f"\n{spirit()} \U0001f43b")

    _save_state("briefing", {"last_date": today})
    return "\n".join(lines)


def _sync_deadlines_to_todoist(cfg: ConfigDict) -> None:
    """Auto-add upcoming Canvas deadlines to Todoist if enabled."""
    todoist = cfg.get("todoist", {})
    if not todoist.get("enabled") or not todoist.get("token"):
        return

    token = str(todoist["token"])
    courses = _normalise_courses(cfg)

    # Load what we've already synced
    state = _load_state("todoist_sync")
    synced = set(state.get("synced", []))

    try:
        events = _canvas_get(cfg, "/users/self/upcoming_events")
        if not isinstance(events, list):
            return
    except Exception:
        return

    new_synced: set[str] = set(synced)

    for event in events:
        if not isinstance(event, dict):
            continue
        assignment = event.get("assignment")
        if not isinstance(assignment, dict):
            continue

        # Skip already submitted
        sub = assignment.get("submission", {})
        if isinstance(sub, dict) and sub.get("workflow_state") in ("submitted", "graded"):
            continue

        title = str(event.get("title", ""))
        due = str(event.get("end_at") or event.get("start_at") or "")
        context_code = str(event.get("context_code", ""))
        course_name = courses.get(context_code.replace("course_", ""), "")
        assignment_id = str(assignment.get("id", ""))

        key = f"{context_code}:{assignment_id}"
        if key in synced:
            continue

        # Create Todoist task
        task_title = f"{course_name} \u2014 {title}" if course_name else title
        due_date = due[:10] if due else ""

        try:
            body: dict[str, str] = {"content": task_title}
            if due_date:
                body["due_string"] = due_date

            resp = httpx.post(
                "https://api.todoist.com/api/v1/tasks",
                json=body,
                headers={"Authorization": f"Bearer {token}"},
                timeout=15.0,
            )
            if resp.status_code == 200:
                new_synced.add(key)
                logger.info("Synced to Todoist: %s", task_title)
        except Exception:
            logger.warning("Failed to sync task to Todoist: %s", task_title, exc_info=True)

    if new_synced != synced:
        _save_state("todoist_sync", {"synced": sorted(new_synced)})


def _sync_deadlines_to_calendar(cfg: ConfigDict) -> None:
    """Auto-create Google Calendar events for upcoming Canvas deadlines."""
    if not cfg.get("calendar", {}).get("enabled"):
        return

    try:
        from openmind.tools.calendar import _get_calendar_service
    except ImportError:
        return

    service = _get_calendar_service(cfg)
    if service is None:
        return

    courses = _normalise_courses(cfg)

    # Load what we've already synced
    state = _load_state("calendar_sync")
    synced = set(state.get("synced", []))

    try:
        events = _canvas_get(cfg, "/users/self/upcoming_events")
        if not isinstance(events, list):
            return
    except Exception:
        return

    new_synced: set[str] = set(synced)

    for event in events:
        if not isinstance(event, dict):
            continue
        assignment = event.get("assignment")
        if not isinstance(assignment, dict):
            continue

        # Skip already submitted
        sub = assignment.get("submission", {})
        if isinstance(sub, dict) and sub.get("workflow_state") in ("submitted", "graded"):
            continue

        title = str(event.get("title", ""))
        due = str(event.get("end_at") or event.get("start_at") or "")
        context_code = str(event.get("context_code", ""))
        course_name = courses.get(context_code.replace("course_", ""), "")
        assignment_id = str(assignment.get("id", ""))
        points = assignment.get("points_possible", 0) or 0

        key = f"cal:{context_code}:{assignment_id}"
        if key in synced:
            continue

        # Only auto-add significant assignments (5+ points)
        try:
            if float(points) < 5:
                continue
        except (TypeError, ValueError):
            continue

        # Create all-day calendar event on the due date
        event_title = f"\U0001f4da {course_name} \u2014 {title}" if course_name else f"\U0001f4da {title}"
        due_date = due[:10] if due else ""
        if not due_date:
            continue

        # Exclusive end date for all-day events
        try:
            next_day = (datetime.strptime(due_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        except ValueError:
            continue

        try:
            event_body = {
                "summary": event_title,
                "start": {"date": due_date},
                "end": {"date": next_day},
                "reminders": {
                    "useDefault": False,
                    "overrides": [
                        {"method": "popup", "minutes": 24 * 60},
                        {"method": "popup", "minutes": 60},
                    ],
                },
            }
            service.events().insert(calendarId="primary", body=event_body).execute()
            new_synced.add(key)
            logger.info("Synced to Calendar: %s on %s", event_title, due_date)
        except Exception:
            logger.warning("Failed to sync to Calendar: %s", event_title, exc_info=True)

    if new_synced != synced:
        _save_state("calendar_sync", {"synced": sorted(new_synced)})


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
        from openmind.tools.gmail import _get_gmail_service, _headers_map, _extract_body
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
                format="full",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
        except Exception:
            logger.warning("Failed to fetch email %s", msg_id, exc_info=True)
            continue

        payload = msg.get("payload", {})
        headers = _headers_map(payload.get("headers", []))
        sender = headers.get("From", "Unknown")
        subject = headers.get("Subject", "(no subject)")

        # Clean up sender display
        if "<" in sender:
            sender = sender.split("<")[0].strip().strip('"')

        # Extract body preview
        try:
            body = _extract_body(payload) if isinstance(payload, dict) else ""
            # Strip HTML tags for preview
            import re
            preview = re.sub(r'<[^>]+>', '', body).strip()
            preview = " ".join(preview.split())[:150]
        except Exception:
            preview = ""

        # Smart summary: one-line description of what the email is about
        summary = subject
        if preview:
            # Use first sentence of preview as summary if shorter
            first_sentence = preview.split(".")[0].strip()
            if len(first_sentence) > 10 and len(first_sentence) < len(subject):
                summary = first_sentence

        # Format notification (nanobot-style)
        line = f"\u2709\ufe0f {summary}"
        line += f"\nFrom: {sender}"
        line += f"\nSubject: {subject}"

        # Auto-add actionable emails to Todoist if smart_emails enabled
        if cfg.get("smart_emails") and cfg.get("todoist", {}).get("enabled"):
            _auto_todoist_from_email(cfg, subject, preview)

        new_items.append(line)

    # Cap seen set to prevent unbounded growth
    if len(all_ids) > 500:
        all_ids = set(sorted(all_ids)[-250:])
    _save_state("emails", {"seen": sorted(all_ids)})

    if new_items:
        return ["New Berkeley emails \U0001f43b\n\n" + "\n\n".join(new_items)]
    return []


# Actionable email keywords that suggest a Todoist task
_ACTION_KEYWORDS = (
    "submit", "deadline", "due", "reminder", "rsvp", "register",
    "sign up", "apply", "form", "request", "survey", "complete",
    "attend", "conference", "workshop", "meeting",
)


def _auto_todoist_from_email(cfg: ConfigDict, subject: str, preview: str) -> None:
    """Auto-add actionable emails to Todoist if they match action keywords."""
    todoist = cfg.get("todoist", {})
    token = str(todoist.get("token", ""))
    if not token:
        return

    combined = (subject + " " + preview).lower()
    if not any(kw in combined for kw in _ACTION_KEYWORDS):
        return

    # Extract a due date hint from the text
    import re
    date_match = re.search(
        r'(?:by|before|due|on)\s+'
        r'(\w+\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{0,4})',
        combined,
    )
    due_string = date_match.group(1).strip() if date_match else ""

    task_content = f"[email] {subject[:100]}"

    try:
        body: dict[str, str] = {"content": task_content}
        if due_string:
            body["due_string"] = due_string

        resp = httpx.post(
            "https://api.todoist.com/api/v1/tasks",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15.0,
        )
        if resp.status_code == 200:
            logger.info("Auto-added email to Todoist: %s", task_content)
    except Exception:
        logger.warning("Failed to auto-add email to Todoist", exc_info=True)


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
