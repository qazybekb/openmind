# Tools and prompts

OpenMind gives your AI app twelve tools and five prompts. Every tool reads; only
`index_course` writes anything, and only to a file on your own machine.

Every payload carries `as_of`, `tz`, `partial`, and `warnings[]`. When something could
not be read, the result says so instead of coming back short — an empty list from
OpenMind means "nothing is due", never "the request failed".

## Tools

| Tool | Parameters | Returns |
|---|---|---|
| `list_courses` | `refresh` | Your enabled courses: `id`, `name`, `nickname`, `code`, `term`, `ends_human`, `current_score`, `current_grade`, `indexed`. **Call this first** to turn a course name into a `course_id`. |
| `get_deadlines` | `range` (`today`/`this_week`/`next_7_days`/`2weeks`/`month`), `course_id`, `status` (`open`/`all`/`submitted`/`graded`/`missing`/`undated`), `limit`, `offset`, `refresh` | `overdue[]`, `items[]`, `counts`, `notes[]`, `source`, `next_offset`. Each item has `due_human`, `days`, `priority`, `reason`, `weight_pct`, `est_hours`, `start_by`. |
| `get_assignment` | `course_id`, `assignment_id`, `max_chars`, `cursor`, `refresh` | Instructions, rubric, due and lock times, points, weight, hour estimate, start-by date, and your submission status. Dates are yours, so extensions are reflected. |
| `get_course_overview` | `course_id`, `announcements_days`, `max_chars`, `cursor`, `refresh` | Syllabus text, module structure, and recent announcements. |
| `get_grades` | `course_id`, `refresh` | Your own scores. With a `course_id`: assignment-group breakdown, the last 20 graded items, and how many are still ungraded. |
| `find_materials` | `course_id`, `query`, `kind`, `limit`, `cursor`, `refresh` | Cited excerpts from an indexed course, or title and module matches from one that is not indexed — which it tells you. |
| `read_material` | `material_id`, `page`, `cursor` | An indexed document as Markdown with `--- p. N ---` markers. `cursor` is a **character offset**, returned by the previous call — not a section index. Scanned or unsupported files return one line saying so. |
| `index_course` | `course_id`, `enable` | Builds (or deletes) a local searchable index of one course's materials. Runs in 20-second passes; call again while `pending` is above zero. |
| `prepare_study_session` | `course_id`, `topic`, `mode` (`tutor`/`practice`/`explain_assignment`/`weekly_plan`), `assignment_id` | Tutoring rules, a hint ladder, up to four cited excerpts, your course's AI policy, and an opening move. |
| `search_catalog` | `query`, `subject`, `level`, `units`, `offered_term`, `limit` | Berkeley catalog matches with units, department, a description gist, and the terms each course is known to be offered. Courses titled after the query rank first. Use `get_catalog_course` for the full text and cross-listings. A `data_note` says when the call refreshed the snapshot from GitHub; that is news, not a warning. |
| `get_catalog_course` | `subject`, `number` | One course in full: description, units range, repeat rules, cross-listings, known offerings. |
| `check_offering` | `course_code`, `term` | Live sections from classes.berkeley.edu: times, instructors, seats, instruction mode. One request, cached for a day. |

### What the deadline fields mean

- `priority` — **HIGH**: due within 2 days, or worth 20% or more of the grade. **MED**:
  due within 5 days. **LOW**: everything else in the window. Anything past due and
  unsubmitted is listed separately in `overdue[]` and is always HIGH.
- `weight_pct` — the share of your final grade, computed from the course's assignment
  group weights. Reported as unknown rather than guessed when Canvas will not say.
- `est_hours` — a rough estimate from the assignment type, title, and points, with a
  floor for heavily weighted work. Used to compute `start_by`, not to predict your evening.
- `start_by` — the last day you can start and still finish at about 2 hours a day.
  `start_note: "start now"` means that day has already passed.
- `due_human` — the deadline in your Canvas time zone, formatted for reading. Show it
  as written; do not recompute it.

## Prompts

| Prompt | Arguments | What it does |
|---|---|---|
| `tutor` | `course`, `topic`, `level` | Socratic tutoring on a topic, with excerpts from your own materials. Asks before it tells; climbs a hint ladder rather than handing over answers. `/answer` overrides that. |
| `practice` | `course`, `topic`, `count` | Retrieval practice: one question at a time, a confidence rating before the reveal, feedback with citations, and a recap of what you missed. |
| `weekly_plan` | `days`, `course` | A study plan built from your real deadlines, respecting start-by dates and a capacity assumption. |
| `explain_assignment` | `course`, `assignment` | What the assignment asks, what the rubric rewards, an outline, and a time plan — with no text written for you to submit. |
| `course_planner` | `interests`, `constraints`, `term` | Course suggestions from the Berkeley catalog, filtered to what is actually offered, with the advisor caveat attached. |

## What OpenMind will not do

There is no tool to submit work, post a discussion reply, send a message, upload a file,
change a grade, edit a calendar, or fetch an arbitrary URL. The Canvas routes are fixed
in code, course access is limited to the courses you chose at setup, and grades are
requested for `self` only.
