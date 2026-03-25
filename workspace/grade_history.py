#!/usr/bin/env python3
"""Track grade snapshots over time. Run daily via heartbeat."""
import json, os, sys, urllib.request
from datetime import datetime, timezone

TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
if not TOKEN:
    print("ERROR: CANVAS_API_TOKEN environment variable not set", file=sys.stderr)
    sys.exit(1)

WORKSPACE = os.environ.get("WORKSPACE_DIR", "/root/.nanobot/workspace")
COURSES_FILE = os.path.join(WORKSPACE, "courses.json")
HISTORY_FILE = os.path.join(WORKSPACE, "grade_history.json")

with open(COURSES_FILE) as f:
    config = json.load(f)

BASE = config["canvas_base_url"]
courses = config["courses"]

history = {}
if os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE) as f:
        history = json.load(f)

today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
today_grades = {}

for cid, name in courses.items():
    try:
        resp = urllib.request.urlopen(
            f"{BASE}/courses/{cid}/enrollments?user_id=self&access_token={TOKEN}"
        )
        enrollments = json.loads(resp.read())
        for e in enrollments:
            g = e.get('grades', {})
            score = g.get('current_score')
            grade = g.get('current_grade')
            if score is not None:
                today_grades[name] = {"score": score, "grade": grade}
    except urllib.error.URLError as e:
        print(f"WARNING: Failed to fetch grades for {name}: {e}", file=sys.stderr)

history[today] = today_grades

with open(HISTORY_FILE, 'w') as f:
    json.dump(history, f, indent=2)

dates = sorted(history.keys())
if len(dates) >= 2:
    prev_date = dates[-2]
    prev = history[prev_date]
    print("Grade trends:")
    for course, current in today_grades.items():
        prev_score = prev.get(course, {}).get('score')
        curr_score = current['score']
        if prev_score is not None:
            diff = curr_score - prev_score
            arrow = "\U0001f4c8" if diff > 0 else "\U0001f4c9" if diff < 0 else "\u27a1\ufe0f"
            print(f"  {arrow} {course}: {current['grade']} ({curr_score}%) "
                  f"\u2014 {'+' if diff >= 0 else ''}{diff:.1f}% since {prev_date}")
        else:
            print(f"  {course}: {current['grade']} ({curr_score}%)")
else:
    print("First snapshot saved. Run again tomorrow to see trends.")
    for course, data in today_grades.items():
        print(f"  {course}: {data['grade']} ({data['score']}%)")
