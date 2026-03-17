# Heartbeat Tasks

## Active Tasks

- [ ] ASSIGNMENT & ANNOUNCEMENT CHECK:

  Step 1: Fetch upcoming assignments from Canvas API:
  https://bcourses.berkeley.edu/api/v1/users/self/upcoming_events?access_token=YOUR_CANVAS_API_TOKEN

  For each assignment, check days until due:
  - ⚠️ Due within 24hrs + NOT submitted: URGENT alert
  - 📋 Due in 2-3 days + NOT submitted: Reminder
  - 📚 Due in 5 days + NOT submitted: Heads up
  - 🚨 Past due within 5 days + NOT submitted: Warning
  - Already submitted: skip silently

  Step 2: Fetch announcements in ONE call (not per-course):
  https://bcourses.berkeley.edu/api/v1/announcements?context_codes[]=course_1552198&context_codes[]=course_1550426&context_codes[]=course_1551850&context_codes[]=course_1550565&context_codes[]=course_1552042&context_codes[]=course_1550670&per_page=10&access_token=YOUR_CANVAS_API_TOKEN

  Only notify about announcements from the last 3 hours that change deadlines, announce new assignments, or cancel classes.

  Step 3: BEFORE sending a message, check workspace file last_notification.md. If the SAME deadline alert was already sent in the last 6 hours, DO NOT send it again. Only send if:
  - A new assignment appeared that wasn't mentioned before
  - A deadline is now within 24 hours (escalate from 📋 to ⚠️)
  - A new announcement was posted

  Step 4: If sending a message, update last_notification.md with what you sent and the current time.

  Step 5: Send ONE combined message if anything NEW to report.

  If nothing new: stay completely silent.
