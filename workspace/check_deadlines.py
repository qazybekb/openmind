#!/usr/bin/env python3
"""Check Canvas deadlines and output only NEW notifications."""
import json, os, sys
from datetime import datetime, timezone
import urllib.request

TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
if not TOKEN:
    print("ERROR: CANVAS_API_TOKEN environment variable not set", file=sys.stderr)
    sys.exit(1)

WORKSPACE = os.environ.get("WORKSPACE_DIR", "/root/.nanobot/workspace")
COURSES_FILE = os.path.join(WORKSPACE, "courses.json")
STATE_FILE = os.path.join(WORKSPACE, "notification_state.json")

with open(COURSES_FILE) as f:
    config = json.load(f)

BASE = config["canvas_base_url"]

prev = {}
if os.path.exists(STATE_FILE):
    with open(STATE_FILE) as f:
        prev = json.load(f)

try:
    resp = urllib.request.urlopen(
        f"{BASE}/users/self/upcoming_events?access_token={TOKEN}"
    )
    events = json.loads(resp.read())
except urllib.error.URLError as e:
    print(f"ERROR: Failed to fetch upcoming events: {e}", file=sys.stderr)
    sys.exit(1)

now = datetime.now(timezone.utc)
notifications = []
new_state = {}

for e in events:
    title = e.get('title', '')
    due = e.get('end_at') or e.get('start_at', '')
    assignment = e.get('assignment', {})
    submitted = False
    if assignment:
        sub = assignment.get('submission', {}) or {}
        submitted = sub.get('workflow_state') in ['submitted', 'graded']

    if not due or submitted:
        continue

    due_dt = datetime.fromisoformat(due.replace('Z', '+00:00'))
    days = (due_dt - now).total_seconds() / 86400

    if days < 0 or days > 7:
        continue

    if days <= 1:
        level = "urgent"
        emoji = "\u26a0\ufe0f"
    elif days <= 3:
        level = "reminder"
        emoji = "\U0001f4cb"
    else:
        level = "headsup"
        emoji = "\U0001f4da"

    key = title.strip()
    prev_level = prev.get(key, "")
    new_state[key] = level

    urgency_order = {"headsup": 0, "reminder": 1, "urgent": 2}
    if prev_level == "" or urgency_order.get(level, 0) > urgency_order.get(prev_level, -1):
        due_str = due_dt.strftime('%b %d')
        days_str = f"{int(days)}d" if days >= 1 else "TODAY"
        notifications.append(f"{emoji} {title} (due {due_str}, {days_str})")

with open(STATE_FILE, 'w') as f:
    json.dump(new_state, f)

if notifications:
    print("Hey Bear \U0001f43b deadline update:\n")
    for n in notifications:
        print(n)
else:
    print("SKIP")
