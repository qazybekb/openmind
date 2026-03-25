#!/usr/bin/env python3
"""Check if assignments due in the last 24 hours were submitted."""
import json, os, urllib.request
from datetime import datetime, timezone, timedelta

TOKEN = "YOUR_CANVAS_API_TOKEN"
BASE = "https://bcourses.berkeley.edu/api/v1"

courses = {
    "1552198": "Big Data",
    "1550426": "Ethical AI",
    "1551850": "Info Law",
    "1550565": "Finance",
    "1552042": "NLP",
    "1550670": "Social Issues"
}

now = datetime.now(timezone.utc)
yesterday = now - timedelta(hours=24)
alerts = []

for cid, name in courses.items():
    try:
        resp = urllib.request.urlopen(f"{BASE}/courses/{cid}/assignments?include[]=submission&order_by=due_at&per_page=100&access_token={TOKEN}")
        assignments = json.loads(resp.read())

        if not isinstance(assignments, list):
            continue

        for a in assignments:
            due = a.get('due_at')
            if not due:
                continue

            due_dt = datetime.fromisoformat(due.replace('Z', '+00:00'))

            # Assignment was due in the last 24 hours
            if yesterday <= due_dt <= now:
                sub = a.get('submission', {}) or {}
                submitted = sub.get('workflow_state') in ['submitted', 'graded']
                aname = a.get('name', '?')

                if submitted:
                    alerts.append(f"✅ {name} — {aname}: Submitted!")
                else:
                    alerts.append(f"🚨 {name} — {aname}: NOT submitted! Was due {due_dt.strftime('%b %d %I%p')}")
    except:
        pass

if alerts:
    print("Submission check 🐻\n")
    for a in alerts:
        print(a)
else:
    print("SKIP")
