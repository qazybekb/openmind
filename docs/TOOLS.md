# OpenMind — Tools Reference

OpenMind uses LLM function calling (tool use) to interact with external services. The LLM decides which tools to call based on the student's question. This document describes all 40 tools.

## Core Tools (27 — always available)

### Canvas API — 13 tools

| Tool | Parameters | Description |
|------|-----------|-------------|
| `lookup_course_id` | `nickname` (required) | Look up a course ID from a nickname. Exact match first, then substring. |
| `get_upcoming_assignments` | — | Fetch upcoming assignments across all courses. Filters out calendar events. |
| `get_course_assignments` | `course_id` (required) | Fetch assignments for a course with submission status. Paginated. |
| `get_grades` | `course_id` (required) | Get grades/enrollment for a specific course. |
| `get_all_grades` | — | Get grades for all active courses at once. |
| `get_assignment_details` | `course_id`, `assignment_id` (both required) | Full assignment details: description, rubric, due date. |
| `get_assignment_groups` | `course_id` (required) | Assignment group weights for grade calculations. |
| `get_modules` | `course_id` (required) | Course modules with items. Paginated. |
| `get_page_content` | `course_id`, `page_url` (both required) | HTML content of a Canvas page. |
| `get_course_files` | `course_id` (required), `search_term` (optional) | List files with download URLs. Paginated. |
| `get_announcements` | `course_id` (optional) | Recent announcements for one or all courses. Paginated. |
| `get_syllabus` | `course_id` (required) | Syllabus body for a course. |
| `get_discussion_topics` | `course_id` (required) | Discussion topics for a course. Paginated. |

### Berkeley Campus — 3 tools

| Tool | Parameters | Description |
|------|-----------|-------------|
| `berkeley_events` | `category`, `search`, `featured`, `limit` (all optional) | Live events from events.berkeley.edu JSON API. |
| `berkeley_library_hours` | `library` (optional) | Current library hours (scraped from lib.berkeley.edu). |
| `berkeley_study_rooms` | `library` (optional) | LibCal booking links for study rooms. |

### Course Catalog — 3 tools

| Tool | Parameters | Description |
|------|-----------|-------------|
| `berkeley_course_search` | `query`, `subject`, `level`, `limit` (all optional) | Search 11K courses by keyword, subject, or level. |
| `berkeley_course_details` | `subject`, `number` (both required) | Full details for a specific course. |
| `berkeley_list_subjects` | — | List all 240 departments with course counts. |

### Student Profile — 3 tools

| Tool | Parameters | Description |
|------|-----------|-------------|
| `get_profile` | — | Read the student's profile. Returns `missing_fields` when incomplete. |
| `update_profile` | `field`, `value` (both required) | Update a profile field. Used when student shares new info. |
| `import_resume` | `resume_text`, `parsed_skills` (required), `parsed_experience`, `parsed_projects`, `parsed_education` (optional) | Save structured resume data to profile. |

### PDF & Web — 3 tools

| Tool | Parameters | Description |
|------|-----------|-------------|
| `read_pdf` | `url` (required) | Download a PDF and extract text. SSRF protected. |
| `web_fetch` | `url` (required) | Fetch a web page. SSRF protected. Redirects PDF to read_pdf. |
| `web_search` | `query` (required) | Search DuckDuckGo. |

### Reminders — 2 tools

| Tool | Parameters | Description |
|------|-----------|-------------|
| `remind_me` | `message`, `due_at` (required, ISO 8601) | Set a reminder. Delivered via Telegram when due. |
| `list_reminders` | — | List all pending reminders. |

---

## Optional Tools (13 — enabled per integration)

### Obsidian — 3 tools (enable: `openmind setup obsidian`)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `obsidian_read` | `path` (required) | Read a note. Path traversal protected. |
| `obsidian_write` | `path`, `content` (both required) | Write/update a note. Creates directories. |
| `obsidian_search` | `query` (required) | Search notes by filename or content (max 20 results). |

### Todoist — 2 tools (enable: `openmind setup todoist`)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `todoist_add_task` | `content` (required), `due_string` (optional) | Create a task with optional due date. |
| `todoist_list_tasks` | — | List active tasks (max 30). |

### Gmail — 2 tools (enable: `openmind setup gmail`, requires `pip install ".[gmail]"`)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `gmail_search` | `query` (required), `max_results` (optional) | Search emails using Gmail syntax. |
| `gmail_read` | `message_id` (required) | Read full email content by ID. |

### Slack — 3 tools (enable: `openmind setup slack`)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `slack_search` | `query` (required) | Search messages across channels. |
| `slack_read_channel` | `channel` (required), `limit` (optional) | Read recent messages. Resolves channel names to IDs. |
| `slack_list_channels` | — | List accessible channels with topics. |

### Google Calendar — 3 tools (enable: `openmind setup calendar`, requires `pip install ".[calendar]"`)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `calendar_list_events` | `days_ahead` (optional, default 7) | List upcoming calendar events. |
| `calendar_add_event` | `title`, `date` (required), `time`, `duration_minutes` (optional) | Create a timed or all-day event. |
| `calendar_add_deadlines` | `assignments` (required, list) | Bulk-add Canvas deadlines with reminders. |

---

## Error Handling

All tools return errors as JSON: `{"error": "description"}`. The LLM receives the error and explains it to the student.

Canvas-specific error mapping:
- **401** → "Canvas token is invalid or expired. Run: openmind setup"
- **403** → "Access denied. Check token permissions."
- **429** → "Rate limit hit. Wait a minute."

## Security

- **SSRF protection** on `web_fetch` and `read_pdf` — blocks localhost, private IPs, validates redirects
- **Path traversal protection** on Obsidian tools — `is_relative_to()` check before any file I/O
- **Canvas URL validation** — only `bcourses.berkeley.edu` is allowed
- **Prompt injection guardrail** — system prompt declares tool results as untrusted data
- **Sensitive integration gating** — Gmail, Slack, Calendar, Todoist, and Obsidian tools require explicit recent user intent
