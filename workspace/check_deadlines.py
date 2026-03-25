#!/usr/bin/env python3
"""Check Canvas deadlines and output only NEW notifications."""
import json, os, sys
from datetime import datetime, timezone, timedelta
import urllib.request

TOKEN = "YOUR_CANVAS_API_TOKEN"
STATE_FILE = "/root/.nanobot/workspace/notification_state.json"

# Load previous state
prev = {}
if os.path.exists(STATE_FILE):
    with open(STATE_FILE) as f:
        prev = json.load(f)

# Fetch upcoming events
resp = urllib.request.urlopen(f"https://bcourses.berkeley.edu/api/v1/users/self/upcoming_events?access_token={TOKEN}")
events = json.loads(resp.read())

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

    # Determine urgency
    if days <= 1:
        level = "urgent"
        emoji = "⚠️"
    elif days <= 3:
        level = "reminder"
        emoji = "📋"
    else:
        level = "headsup"
        emoji = "📚"

    key = title.strip()
    prev_level = prev.get(key, "")
    new_state[key] = level

    # Only notify if new or escalated
    urgency_order = {"headsup": 0, "reminder": 1, "urgent": 2}
    if prev_level == "" or urgency_order.get(level, 0) > urgency_order.get(prev_level, -1):
        due_str = due_dt.strftime('%b %d')
        days_str = f"{int(days)}d" if days >= 1 else "TODAY"
        notifications.append(f"{emoji} {title} (due {due_str}, {days_str})")

# Save new state
with open(STATE_FILE, 'w') as f:
    json.dump(new_state, f)

# Output
if notifications:
    print("Hey Bear 🐻 deadline update:\n")
    for n in notifications:
        print(n)
else:
    print("SKIP")
