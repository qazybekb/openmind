#!/usr/bin/env python3
"""Track grade snapshots over time. Run daily via heartbeat."""
import json, os, urllib.request
from datetime import datetime, timezone

TOKEN = "YOUR_CANVAS_API_TOKEN"
BASE = "https://bcourses.berkeley.edu/api/v1"
HISTORY_FILE = "/root/.nanobot/workspace/grade_history.json"

courses = {
    "1552198": "Big Data",
    "1550426": "Ethical AI",
    "1551850": "Info Law",
    "1550565": "Finance",
    "1552042": "NLP",
    "1550670": "Social Issues"
}

# Load history
history = {}
if os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE) as f:
        history = json.load(f)

today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
today_grades = {}

for cid, name in courses.items():
    try:
        resp = urllib.request.urlopen(f"{BASE}/courses/{cid}/enrollments?user_id=self&access_token={TOKEN}")
        enrollments = json.loads(resp.read())
        for e in enrollments:
            g = e.get('grades', {})
            score = g.get('current_score')
            grade = g.get('current_grade')
            if score is not None:
                today_grades[name] = {"score": score, "grade": grade}
    except:
        pass

# Save today's snapshot
history[today] = today_grades

with open(HISTORY_FILE, 'w') as f:
    json.dump(history, f, indent=2)

# Show trends
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
            arrow = "📈" if diff > 0 else "📉" if diff < 0 else "➡️"
            print(f"  {arrow} {course}: {current['grade']} ({curr_score}%) — {'+' if diff >= 0 else ''}{diff:.1f}% since {prev_date}")
        else:
            print(f"  {course}: {current['grade']} ({curr_score}%)")
else:
    print("First snapshot saved. Run again tomorrow to see trends.")
    for course, data in today_grades.items():
        print(f"  {course}: {data['grade']} ({data['score']}%)")
