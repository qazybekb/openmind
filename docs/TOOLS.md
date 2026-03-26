# OpenMind — Tools Reference

OpenMind uses LLM function calling (tool use) to interact with external services. The LLM decides which tools to call based on the student's question. This document describes every available tool.

## Core Tools (always available)

### Canvas API — 13 tools

#### `lookup_course_id`
Look up a Canvas course ID from a nickname.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `nickname` | string | yes | Course name or partial match (e.g., "NLP", "Finance") |

Returns the matching course ID. Uses exact match first, then substring. Returns disambiguation list if multiple matches.

#### `get_upcoming_assignments`
Fetch all upcoming assignments across all courses. Filters out calendar events (lectures, office hours) — only returns items with an assignment payload. No parameters.

#### `get_course_assignments`
Fetch assignments for a specific course with submission status.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `course_id` | string | yes | Canvas course ID |

Paginated — follows Canvas Link headers up to 2000 items.

#### `get_grades`
Get grades/enrollment for a specific course.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `course_id` | string | yes | Canvas course ID |

#### `get_all_grades`
Get grades for all active courses at once. No parameters. Returns a map of course name to score/grade.

#### `get_assignment_details`
Get full details of a specific assignment including description HTML, rubric, due date.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `course_id` | string | yes | Canvas course ID |
| `assignment_id` | string | yes | Canvas assignment ID |

#### `get_assignment_groups`
Get assignment group weights for grade calculations (e.g., "Homework 30%, Midterm 40%").

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `course_id` | string | yes | Canvas course ID |

#### `get_modules`
Get course modules with items (weeks, topics, readings). Paginated.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `course_id` | string | yes | Canvas course ID |

#### `get_page_content`
Get the HTML content of a specific Canvas page.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `course_id` | string | yes | Canvas course ID |
| `page_url` | string | yes | Canvas page URL slug |

#### `get_course_files`
List files in a course with download URLs. Paginated.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `course_id` | string | yes | Canvas course ID |
| `search_term` | string | no | Filter by filename |

#### `get_announcements`
Get recent announcements for one or all courses. Paginated.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `course_id` | string | no | Specific course, or omit for all |

#### `get_syllabus`
Get the syllabus body for a course.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `course_id` | string | yes | Canvas course ID |

#### `get_discussion_topics`
Get discussion topics for a course. Paginated.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `course_id` | string | yes | Canvas course ID |

---

### PDF — 1 tool

#### `read_pdf`
Download a PDF from a URL and extract text from every page using pymupdf.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | yes | Direct URL to the PDF |

SSRF protection: blocks localhost, private IPs, non-http(s) schemes.

---

### Web — 2 tools

#### `web_fetch`
Fetch a web page and return its text content. Truncates at 50,000 characters. Redirects PDFs to `read_pdf`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | yes | URL to fetch |

SSRF protection: blocks localhost, private IPs, non-http(s) schemes.

#### `web_search`
Search DuckDuckGo and return results as HTML.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | yes | Search query |

---

## Optional Tools

These tools are only loaded when their integration is enabled in config.

### Gmail — 2 tools (requires `pip install ".[gmail]"`)

#### `gmail_search`
Search Gmail using Gmail search syntax.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | yes | Gmail search query (e.g., `from:professor@berkeley.edu`, `subject:midterm`, `is:unread`) |
| `max_results` | integer | no | Max emails to return (default 10) |

Returns: list of emails with id, from, subject, date, snippet.

#### `gmail_read`
Read the full content of a specific email.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `message_id` | string | yes | Gmail message ID (from `gmail_search` results) |

Returns: from, subject, date, full body text.

### Todoist — 2 tools

#### `todoist_add_task`
Create a new task in Todoist.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `content` | string | yes | Task title (e.g., "NLP — Midterm report") |
| `due_string` | string | no | Due date (e.g., "2026-03-21" or "Friday") |

#### `todoist_list_tasks`
List active Todoist tasks (up to 30). No parameters.

### Obsidian — 3 tools

#### `obsidian_read`
Read a note from the Obsidian vault.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | yes | Relative path (e.g., "Readings/Author Title.md") |

Path traversal protection: blocks `../` escapes outside the vault.

#### `obsidian_write`
Write or update a note in the vault. Creates parent directories.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | yes | Relative path |
| `content` | string | yes | Markdown content |

#### `obsidian_search`
Search notes by filename or content (up to 20 results).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | yes | Search term |

---

## Error Handling

All tools return errors as JSON: `{"error": "description"}`. The LLM receives the error and can explain it to the student or retry.

Canvas-specific error mapping:
- **401** → "Canvas token is invalid or expired. Run: openmind setup"
- **403** → "Access denied. Your token may not have permission for this resource."
- **429** → "Canvas rate limit hit. Wait a minute and try again."
