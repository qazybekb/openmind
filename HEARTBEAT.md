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

  Step 2: Fetch announcements:
  https://bcourses.berkeley.edu/api/v1/announcements?context_codes[]=course_1552198&context_codes[]=course_1550426&context_codes[]=course_1551850&context_codes[]=course_1550565&context_codes[]=course_1552042&context_codes[]=course_1550670&per_page=10&access_token=YOUR_CANVAS_API_TOKEN

  Only notify about announcements from the last 3 hours that change deadlines, announce new assignments, or cancel classes.

  Step 3: Send ONE combined message if anything to report.

  If nothing to report: stay completely silent.
