# Heartbeat Tasks

## Active Tasks

- [ ] DEADLINE ALERTS (every heartbeat): Read course_cache.json from workspace — DO NOT call Canvas API. Check assignments:
  - ⚠️ Due within 24hrs: URGENT alert
  - 📋 Due in 2-3 days: Reminder
  - 🚨 Past due + not submitted: WARNING
  If nothing urgent: stay silent. This should use ZERO API calls — just read the local file.

- [ ] CACHE REFRESH (only at ~8am and ~8pm Pacific — skip other times): Check current time. Only if it's roughly 8am or 8pm Pacific (within 2 hours), do the full refresh:
  1. Fetch assignments from Canvas API for each course
  2. Compare with course_cache.json — check for:
     - New assignments that weren't there before → notify + add to Todoist
     - Changed due dates → notify: "📢 [Assignment] due date changed from [old] to [new]"
     - New grades posted → notify: "🔥 You got [grade] on [assignment]!"
  3. Fetch files list for each course — compare with cache, notify about new files:
     "📄 New file in NLP: lecture_07_transformers.pdf" (include download link)
  4. Update course_cache.json with fresh data (assignments, grades, files)
  5. Fetch recent announcements — only notify about deadline changes or new assignments
  If it's NOT around 8am/8pm: skip this task entirely.

- [ ] TODOIST SYNC (during cache refresh only): After updating the cache, compare assignments with Todoist:
  1. Get all tasks from Todoist
  2. For each Canvas assignment with a future due date:
     - If NOT in Todoist (no matching task name) → add it with due date → notify: "📌 New assignment added to Todoist: [Course] — [Name] (due [date])"
     - If in Todoist but due date CHANGED from what's in Todoist → update the Todoist task due date → notify: "📅 Due date updated: [Course] — [Name] moved to [new date]"
     - If already in Todoist with correct date → skip silently
  3. Send one combined notification if anything changed

- [ ] SESSION CLEANUP (only on Sundays): If today is Sunday, check the telegram session file size. If it's over 500KB, it's getting too large and will slow responses. Truncate old history by rewriting the session file to keep only the last 50 messages.
