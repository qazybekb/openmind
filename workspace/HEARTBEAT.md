# Heartbeat Tasks

## Active Tasks

- [ ] DEADLINE CHECK: Run shell command: python3 /root/.nanobot/workspace/check_deadlines.py
  - If output says "SKIP" → do nothing
  - If output has notifications → send the EXACT output as a Telegram message

- [ ] SUBMISSION CHECK: Run shell command: python3 /root/.nanobot/workspace/check_submissions.py
  - If output says "SKIP" → do nothing
  - If output has alerts → send the EXACT output as a Telegram message

- [ ] GRADE TRACKING: Run shell command: python3 /root/.nanobot/workspace/grade_history.py
  - If output shows grade changes (📈 or 📉) → send as Telegram message: "Grade update! 🐻\n[output]"
  - If first snapshot or no changes → stay silent
