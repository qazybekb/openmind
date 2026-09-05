"""Shared fixtures: a synthetic bCourses instance, a frozen clock, and an isolated home.

Every test runs against `httpx.MockTransport` over the fixture data below, so the suite
never touches the network, a real Canvas account, or the developer's keyring.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from openmind.canvas import CanvasClient
from openmind.config import Config

FIXTURES = Path(__file__).parent / "fixtures"

# Friday 2026-09-04 15:00 in Berkeley = 22:00 UTC. Chosen so "11:59 PM tonight"
# lands on a different UTC date, which is the bug this whole design exists to avoid.
NOW_UTC = datetime(2026, 9, 4, 22, 0, tzinfo=UTC)
TZ = "America/Los_Angeles"


def canvas_dt(days: float = 0.0, *, hour: int = 23, minute: int = 59) -> str:
    """Return a Canvas UTC timestamp for a local Berkeley time N days from the clock."""
    from zoneinfo import ZoneInfo

    local = NOW_UTC.astimezone(ZoneInfo(TZ))
    target = (local + timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return target.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


COURSES: list[dict[str, Any]] = [
    {
        "id": 1001,
        "name": "STAT 156 - Causal Inference",
        "course_code": "STAT 156",
        "apply_assignment_group_weights": True,
        "hide_final_grades": False,
        "term": {"name": "Fall 2026", "end_at": "2026-12-19T08:00:00Z"},
        "enrollments": [
            {"type": "student", "computed_current_score": 88.5, "computed_current_grade": "B+",
             "computed_final_score": 62.0},
        ],
    },
    {
        "id": 1002,
        "name": "INFO 259 - Natural Language Processing",
        "course_code": "INFO 259",
        "apply_assignment_group_weights": False,
        "term": {"name": "Fall 2026", "end_at": "2026-12-19T08:00:00Z"},
        "enrollments": [
            {"type": "student", "computed_current_score": None, "computed_current_grade": None},
        ],
    },
    {"id": 9999, "name": "Not Enabled - Ignore Me", "course_code": "XX 1", "term": {"name": "Fall 2026"}},
]

GROUPS_1001: list[dict[str, Any]] = [
    {
        "id": 10, "name": "Problem Sets", "group_weight": 40.0, "rules": {"drop_lowest": 1},
        "assignments": [
            {"id": 201, "name": "Problem Set 3", "points_possible": 20, "published": True},
            {"id": 202, "name": "Problem Set 4", "points_possible": 20, "published": True},
            {"id": 209, "name": "Ungraded practice", "points_possible": 0, "published": True},
        ],
    },
    {
        "id": 11, "name": "Exams", "group_weight": 60.0, "rules": {},
        "assignments": [
            {"id": 203, "name": "Midterm 1", "points_possible": 100, "published": True, "quiz_id": 5001},
            {"id": 204, "name": "Final Exam", "points_possible": 100, "published": True},
            {"id": 205, "name": "Extra credit", "points_possible": 10, "published": True,
             "omit_from_final_grade": True},
        ],
    },
]

GROUPS_1002: list[dict[str, Any]] = [
    {
        "id": 20, "name": "Assignments", "group_weight": 0.0, "rules": {},
        "assignments": [
            {"id": 301, "name": "Reading response 2", "points_possible": 10, "published": True},
            {"id": 302, "name": "Final Project", "points_possible": 90, "published": True},
        ],
    },
]

PLANNER: list[dict[str, Any]] = [
    {
        "course_id": 1001, "plannable_id": 201, "plannable_type": "assignment",
        "plannable_date": canvas_dt(0), "html_url": "/courses/1001/assignments/201",
        "plannable": {"id": 201, "title": "Problem Set 3", "due_at": canvas_dt(0), "points_possible": 20,
                      "submission_types": ["online_upload"]},
        "submissions": {"submitted": False, "graded": False, "late": False, "missing": False, "excused": False},
    },
    {
        "course_id": 1001, "plannable_id": 5001, "plannable_type": "quiz",
        "plannable_date": canvas_dt(6), "html_url": "/courses/1001/quizzes/5001",
        "plannable": {"id": 5001, "title": "Midterm 1", "due_at": canvas_dt(6), "points_possible": 100},
        "submissions": {"submitted": False, "graded": False, "late": False, "missing": False, "excused": False},
    },
    {
        "course_id": 1001, "plannable_id": 202, "plannable_type": "assignment",
        "plannable_date": canvas_dt(-3), "html_url": "/courses/1001/assignments/202",
        "plannable": {"id": 202, "title": "Problem Set 4", "due_at": canvas_dt(-3), "points_possible": 20,
                      "submission_types": ["online_upload"]},
        "submissions": {"submitted": False, "graded": False, "late": False, "missing": True, "excused": False},
    },
    {
        "course_id": 1002, "plannable_id": 301, "plannable_type": "assignment",
        "plannable_date": canvas_dt(2), "html_url": "/courses/1002/assignments/301",
        "plannable": {"id": 301, "title": "Reading response 2", "due_at": canvas_dt(2), "points_possible": 10,
                      "submission_types": ["online_text_entry"]},
        "submissions": {"submitted": True, "graded": False, "late": False, "missing": False, "excused": False},
    },
    {
        "course_id": 1002, "plannable_id": 302, "plannable_type": "assignment",
        "plannable_date": canvas_dt(9), "html_url": "/courses/1002/assignments/302",
        "plannable": {"id": 302, "title": "Final Project", "due_at": canvas_dt(9), "points_possible": 90,
                      "submission_types": ["online_upload"]},
        "submissions": {"submitted": False, "graded": False, "late": False, "missing": False, "excused": False},
    },
    {
        "course_id": 1001, "plannable_id": 77, "plannable_type": "calendar_event",
        "plannable_date": canvas_dt(1), "plannable": {"id": 77, "title": "Office hours"},
    },
]

SYLLABUS = (
    "<h2>Grading</h2><p>Problem sets 40%, exams 60%.</p>"
    "<h2>Collaboration and AI</h2><p>You may use generative AI tools such as ChatGPT to explain concepts, "
    "but submitting AI-written solutions is an academic integrity violation. Cite any AI assistance.</p>"
)


def _paged(items: list[dict[str, Any]], request: httpx.Request) -> httpx.Response:
    """Return a JSON list, with a Link header on the first page when paging is exercised."""
    return httpx.Response(200, json=items, request=request)


def handler(request: httpx.Request) -> httpx.Response:
    """Serve the synthetic bCourses instance."""
    path = request.url.path.replace("/api/v1", "", 1)
    params = request.url.params

    if path == "/users/self/profile":
        return httpx.Response(200, json={"id": 7, "name": "Test Student", "time_zone": TZ})
    if path == "/courses":
        return _paged(COURSES, request)
    if path == "/planner/items":
        codes = params.get_list("context_codes[]")
        items = PLANNER
        if codes:
            allowed = {code.replace("course_", "") for code in codes}
            items = [item for item in PLANNER if str(item["course_id"]) in allowed]
        return _paged(items, request)
    if path == "/courses/1001/assignment_groups":
        return _paged(GROUPS_1001, request)
    if path == "/courses/1002/assignment_groups":
        return _paged(GROUPS_1002, request)
    if path == "/courses/1001":
        return httpx.Response(200, json={"id": 1001, "name": COURSES[0]["name"], "course_code": "STAT 156",
                                         "syllabus_body": SYLLABUS, "updated_at": "2026-08-20T00:00:00Z"},
                              request=request)
    if path == "/courses/1002":
        return httpx.Response(200, json={"id": 1002, "name": COURSES[1]["name"], "course_code": "INFO 259",
                                         "syllabus_body": ""}, request=request)
    if path == "/courses/1001/assignments/201":
        return httpx.Response(200, json={
            "id": 201, "name": "Problem Set 3", "due_at": canvas_dt(0), "lock_at": canvas_dt(1),
            "points_possible": 20, "submission_types": ["online_upload"],
            "html_url": "https://bcourses.berkeley.edu/courses/1001/assignments/201",
            "description": "<p>Estimate the average treatment effect.</p><p>Show your assumptions.</p>",
            "rubric": [{"description": "Correctness", "points": 12,
                        "long_description": "<p>Identification assumptions stated.</p>"},
                       {"description": "Clarity", "points": 8}],
            "submission": {"workflow_state": "unsubmitted", "score": None, "attempt": None},
        }, request=request)
    if path == "/courses/1001/modules":
        return _paged([
            {"id": 30, "name": "Week 3 — Confounding", "items": [
                {"id": 41, "title": "Week 3 Slides", "type": "File", "content_id": 501,
                 "html_url": "https://bcourses.berkeley.edu/courses/1001/modules/items/41"},
                {"id": 42, "title": "Reading: Chapter 4", "type": "Page", "content_id": 502},
            ]},
        ], request)
    if path == "/courses/1002/modules":
        return _paged([], request)
    if path == "/announcements":
        return _paged([
            {"id": 60, "title": "Midterm room change", "posted_at": canvas_dt(-1, hour=9),
             "message": "<p>The midterm is in Wheeler 150.</p>",
             "html_url": "https://bcourses.berkeley.edu/courses/1001/announcements/60"},
        ], request)
    if path == "/courses/1001/pages":
        return _paged([{"url": "week-3-notes", "title": "Week 3 Notes", "updated_at": "2026-09-01T00:00:00Z",
                        "html_url": "https://bcourses.berkeley.edu/courses/1001/pages/week-3-notes"}], request)
    if path == "/courses/1001/pages/week-3-notes":
        return httpx.Response(200, json={
            "url": "week-3-notes", "title": "Week 3 Notes",
            "body": "<h2>Confounding</h2><p>A confounder causes both the treatment and the outcome. "
                    "Adjusting for it removes the backdoor path.</p>",
        }, request=request)
    if path == "/courses/1001/files":
        return _paged([{"id": 501, "display_name": "week3.pdf", "content-type": "application/pdf",
                        "size": 1024, "url": "https://bcourses.berkeley.edu/files/501/download?verifier=abc",
                        "html_url": "https://bcourses.berkeley.edu/courses/1001/files/501",
                        "updated_at": "2026-09-01T00:00:00Z"}], request)
    if path == "/courses/1002/files":
        return httpx.Response(403, json={"status": "unauthorized"}, request=request)
    if path == "/courses/1002/pages":
        return _paged([], request)
    if path == "/courses/1001/students/submissions":
        return _paged([
            {"assignment_id": 202, "score": 18.0, "workflow_state": "graded", "graded_at": canvas_dt(-2),
             "assignment": {"name": "Problem Set 2", "points_possible": 20}},
            {"assignment_id": 208, "score": None, "workflow_state": "submitted", "submitted_at": canvas_dt(-1)},
        ], request)
    if path.startswith("/courses/1001/assignments"):
        return _paged([
            {"id": 201, "name": "Problem Set 3", "due_at": canvas_dt(0), "points_possible": 20,
             "submission_types": ["online_upload"], "submission": {"workflow_state": "unsubmitted"}},
            {"id": 210, "name": "Course survey", "due_at": None, "points_possible": 1,
             "submission_types": ["online_quiz"], "submission": {"workflow_state": "unsubmitted"}},
        ], request)
    if path.startswith("/courses/1002/assignments"):
        return _paged([], request)

    return httpx.Response(404, json={"errors": [{"message": "not found"}]}, request=request)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point OPENMIND_HOME at a temporary directory for the whole test."""
    target = tmp_path / "openmind"
    target.mkdir()
    monkeypatch.setenv("OPENMIND_HOME", str(target))
    monkeypatch.delenv("OPENMIND_CANVAS_TOKEN", raising=False)
    return target


@pytest.fixture(autouse=True)
def isolated_host_configs(tmp_path_factory, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep every test away from the developer's real Claude and Cursor configs.

    Autouse and unconditional: `openmind doctor` reads these paths, so without this a
    test outcome would depend on whether the machine running it happens to use Claude.
    """
    target = tmp_path_factory.mktemp("hostconfig")
    monkeypatch.setenv("OPENMIND_HOST_CONFIG_DIR", str(target))
    return target


@pytest.fixture
def config(home: Path) -> Config:
    """A config sharing the two synthetic courses."""
    cfg = Config(
        {
            "canvas_url": "https://bcourses.berkeley.edu",
            "time_zone": TZ,
            "user_name": "Test Student",
            "courses": {"1001": "Causal Inference", "1002": "NLP"},
            "index_enabled": [],
            "capacity_hours_per_day": 2.0,
            "data_updates": False,
        },
        home / "config.json",
    )
    cfg.save()
    return cfg


@pytest.fixture
def client() -> CanvasClient:
    """A Canvas client wired to the synthetic instance."""
    canvas = CanvasClient(
        "https://bcourses.berkeley.edu", "fake-token-value-0123456789",
        transport=httpx.MockTransport(handler),
    )
    yield canvas
    canvas.close()


@pytest.fixture
def session(config: Config, client: CanvasClient):
    """A service session with a frozen clock."""
    from openmind.service import Session

    return Session(config, client, clock=NOW_UTC)


@pytest.fixture
def sample_catalog(home: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A tiny catalog database built from CSV rows, without the packaged 11k-row files."""
    import csv

    from openmind import catalog as catalog_module

    source = home / "data"
    source.mkdir()
    rows = [
        {"Subject": "STAT", "Course Number": "156", "Department(s)": "Statistics",
         "Course Title": "Causal Inference", "Credits - Units - Minimum Units": "4",
         "Credits - Units - Maximum Units": "4", "Terms Offered": "-",
         "Course Description": "Potential outcomes, randomized experiments, observational studies.",
         "Cross-Listed Course(s)": "-", "Repeat Rules": "Course is not repeatable for credit.",
         "Offering Information": "-", "Additional Offering Information": "-", "In Printed Catalog": "0"},
        {"Subject": "COMPSCI", "Course Number": "189", "Department(s)": "Computer Science",
         "Course Title": "Introduction to Machine Learning", "Credits - Units - Minimum Units": "4",
         "Credits - Units - Maximum Units": "4", "Terms Offered": "-",
         "Course Description": "Regression, classification, neural networks.",
         "Cross-Listed Course(s)": "-", "Repeat Rules": "-", "Offering Information": "-",
         "Additional Offering Information": "-", "In Printed Catalog": "1"},
    ]
    grad = [
        {**rows[0], "Subject": "INFO", "Course Number": "259", "Department(s)": "Information",
         "Course Title": "Natural Language Processing",
         "Course Description": "Language models, parsing, semantics.", "In Printed Catalog": "1"},
    ]
    for name, data in (("undergraduate_courses.csv", rows), ("graduate_courses.csv", grad)):
        with (source / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(data[0].keys()))
            writer.writeheader()
            writer.writerows(data)

    with (source / "term_offerings.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["subject", "number", "term", "section_count", "instruction_modes", "instructors"]
        )
        writer.writeheader()
        writer.writerow({"subject": "STAT", "number": "156", "term": "Fall 2026", "section_count": "1",
                         "instruction_modes": "In-Person Instruction", "instructors": "Peng Ding"})

    (source / "catalog_meta.json").write_text(json.dumps({
        "catalog_as_of": "2026-09-05", "offerings_as_of": "2026-09-05",
        "terms_known": ["Fall 2026"], "data_sha256": "0" * 64,
    }), encoding="utf-8")

    catalog_module.build(source_dir=source)
    return source


@pytest.fixture
def public_dns(monkeypatch: pytest.MonkeyPatch):
    """Make fake hostnames resolve to a public address so no test needs real DNS."""
    import socket

    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 443))]

    monkeypatch.setattr("openmind.materials.socket.getaddrinfo", fake_getaddrinfo)
