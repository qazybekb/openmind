#!/usr/bin/env python3
"""Check if assignments due in the last 24 hours were submitted."""
import json, os, sys, urllib.request
from datetime import datetime, timezone, timedelta

TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
if not TOKEN:
    print("ERROR: CANVAS_API_TOKEN environment variable not set", file=sys.stderr)
    sys.exit(1)

WORKSPACE = os.environ.get("WORKSPACE_DIR", "/root/.nanobot/workspace")
COURSES_FILE = os.path.join(WORKSPACE, "courses.json")

with open(COURSES_FILE) as f:
    config = json.load(f)

BASE = config["canvas_base_url"]
courses = config["courses"]

now = datetime.now(timezone.utc)
yesterday = now - timedelta(hours=24)
alerts = []

for cid, name in courses.items():
    try:
        resp = urllib.request.urlopen(
            f"{BASE}/courses/{cid}/assignments?include[]=submission"
            f"&order_by=due_at&per_page=100&access_token={TOKEN}"
        )
        assignments = json.loads(resp.read())

        if not isinstance(assignments, list):
            continue

        for a in assignments:
            due = a.get('due_at')
            if not due:
                continue

            due_dt = datetime.fromisoformat(due.replace('Z', '+00:00'))

            if yesterday <= due_dt <= now:
                sub = a.get('submission', {}) or {}
                submitted = sub.get('workflow_state') in ['submitted', 'graded']
                aname = a.get('name', '?')

                if submitted:
                    alerts.append(f"\u2705 {name} \u2014 {aname}: Submitted!")
                else:
                    alerts.append(
                        f"\U0001f6a8 {name} \u2014 {aname}: NOT submitted! "
                        f"Was due {due_dt.strftime('%b %d %I%p')}"
                    )
    except urllib.error.URLError as e:
        print(f"WARNING: Failed to fetch {name}: {e}", file=sys.stderr)

if alerts:
    print("Submission check \U0001f43b\n")
    for a in alerts:
        print(a)
else:
    print("SKIP")
