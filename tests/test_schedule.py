"""The classes.berkeley.edu parser, against pages saved from the live site.

These fixtures are the contract with someone else's HTML. If the Registrar restyles the
class schedule, these tests fail — which is the point. A silent parser failure would
report that no courses are offered, which is worse than an error.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from openmind import schedule

FIXTURES = Path(__file__).parent / "fixtures" / "schedule"
SEARCH_PAGE = FIXTURES / "search_stat156_fall2026.html"
SUBJECT_PAGE = FIXTURES / "search_stat_fall2026.html"
FACET_PAGE = FIXTURES / "facets.html"


@pytest.fixture(scope="module")
def results_html() -> str:
    return SEARCH_PAGE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def facets_html() -> str:
    return FACET_PAGE.read_text(encoding="utf-8")


# -- result cards --------------------------------------------------------------


def test_result_cards_are_parsed_into_sections(results_html: str):
    sections, _ = schedule.parse_sections(results_html)
    assert len(sections) == schedule.RESULTS_PER_PAGE


def test_every_field_on_a_card_is_captured(results_html: str):
    sections, _ = schedule.parse_sections(results_html)
    stat = next(s for s in sections if s.course_code == "STAT 156")
    assert stat.title == "Causal Inference"
    assert stat.ccn == "21143"
    assert stat.section == "001"
    assert stat.kind == "LEC"
    assert stat.instructors == "Peng Ding"
    assert stat.days == "Tu, Th"
    assert stat.time == "02:00 pm - 03:29 pm"
    assert stat.location == "Joan and Sanford I. Weill 101"
    assert stat.units == "4"
    assert stat.instruction_mode == "In-Person Instruction"
    assert stat.open_seats == "1"
    assert stat.status == "closed"
    assert stat.term == "2026 Fall"
    assert stat.url.endswith("/content/2026-fall-stat-156-001-lec-001")


def test_a_section_renders_without_empty_fields(results_html: str):
    sections, _ = schedule.parse_sections(results_html)
    payload = sections[0].to_dict()
    assert all(value for value in payload.values())
    assert payload["course"] == "STAT 156"


def test_the_next_page_link_is_resolved_against_the_current_url(results_html: str):
    page = "https://classes.berkeley.edu/search/class?f%5B0%5D=term%3A8588&search=STAT%20156"
    _, next_page = schedule.parse_sections(results_html, page_url=page)
    assert next_page is not None
    assert next_page.startswith("https://classes.berkeley.edu/search/class?")
    assert "page=1" in next_page


def test_a_page_with_no_results_yields_nothing_rather_than_failing():
    sections, next_page = schedule.parse_sections("<html><body><p>No results</p></body></html>")
    assert sections == []
    assert next_page is None


def test_a_restyled_page_fails_loudly_instead_of_reporting_no_courses():
    """The failure mode to avoid: silently telling a student nothing is offered."""
    broken = '<article class="listing"><div class="st--section-name">STAT 156</div></article>'
    with pytest.raises(schedule.ScheduleError, match="changed shape"):
        schedule.parse_sections(broken)


def test_keyword_results_include_unrelated_courses_so_they_are_filtered(results_html: str):
    """Solr's keyword search is generous; the caller narrows it back down."""
    sections, _ = schedule.parse_sections(results_html)
    codes = {s.course_code for s in sections}
    assert "STAT 156" in codes
    assert len(codes) > 1
    exact = [s for s in sections if s.course_code == "STAT 156"]
    assert len(exact) == 1


def test_sections_can_be_grouped_by_subject(results_html: str):
    sections, _ = schedule.parse_sections(SUBJECT_PAGE.read_text(encoding="utf-8"))
    stat = [s for s in sections if schedule.subject_of(s.course_code) == "STAT"]
    assert len(stat) >= 15
    assert all(s.ccn for s in stat)


# -- facets --------------------------------------------------------------------


def test_term_facets_are_read_from_the_sidebar(facets_html: str):
    terms = schedule.parse_terms(facets_html)
    assert len(terms) > 50
    fall = next(term for term in terms if term.name == "Fall 2026")
    assert fall.facet_id == "8588"
    assert fall.count > 5000


def test_the_newest_full_semester_is_chosen_by_date_not_by_size(facets_html: str):
    """Fall 2016 has more sections than Fall 2026; recency is what matters."""
    terms = schedule.parse_terms(facets_html)
    newest = schedule.newest_term(terms)
    assert newest is not None
    assert newest.name == "Fall 2026"
    assert max(terms, key=lambda t: t.count).name != "Fall 2026"


def test_terms_sort_spring_summer_fall_within_a_year():
    assert schedule.term_sort_key("Fall 2026") > schedule.term_sort_key("Summer 2026")
    assert schedule.term_sort_key("Summer 2026") > schedule.term_sort_key("Spring 2026")
    assert schedule.term_sort_key("Spring 2027") > schedule.term_sort_key("Fall 2026")
    assert schedule.term_sort_key("12W: Week May 26-Aug 14") == (-1, -1)


def test_sorted_terms_are_newest_first(facets_html: str):
    ordered = schedule.sorted_terms(schedule.parse_terms(facets_html))
    assert [term.name for term in ordered[:3]] == ["Fall 2026", "Spring 2026", "Fall 2025"]


def test_subject_facets_are_read_with_their_labels(facets_html: str):
    subjects = schedule.parse_subjects(facets_html)
    assert len(subjects) > 200
    assert any(subject.name == "American Studies" for subject in subjects)
    assert all(subject.facet_id.isdigit() for subject in subjects)


# -- URLs and fetching ---------------------------------------------------------


def test_search_urls_carry_the_term_facet_and_the_keyword():
    url = schedule.search_url("STAT 156", "8588", page=2)
    assert "f%5B0%5D=term%3A8588" in url
    assert "search=STAT+156" in url
    assert "page=2" in url


def test_finding_sections_makes_exactly_one_request(results_html: str):
    calls: list[str] = []

    def responder(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text=results_html, request=request)

    client = httpx.Client(transport=httpx.MockTransport(responder))
    sections = schedule.find_sections("stat 156", "8588", client=client)
    client.close()

    assert len(calls) == 1
    assert [s.course_code for s in sections] == ["STAT 156"]


def test_a_cross_listed_course_is_found_without_its_c(results_html: str):
    """The course a student calls "INTEGBI 156" is scheduled as "INTEGBI C156"."""
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, text=results_html, request=request)
    ))
    without_c = schedule.find_sections("INTEGBI 156", "8588", client=client)
    with_c = schedule.find_sections("INTEGBI C156", "8588", client=client)
    exact_wins = schedule.find_sections("STAT 156", "8588", client=client)
    client.close()

    assert with_c and {s.course_code for s in with_c} == {"INTEGBI C156"}
    assert [s.ccn for s in without_c] == [s.ccn for s in with_c]
    assert {s.course_code for s in exact_wins} == {"STAT 156"}, "an exact match never widens to a C variant"
    assert schedule.same_course("STAT 131A", "STAT C131A")
    assert not schedule.same_course("STAT 131A", "STAT 131B")
    assert not schedule.same_course("STAT C8", "STAT 8B")


def test_a_polite_user_agent_identifies_the_project(results_html: str):
    seen: list[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=results_html, request=request)

    client = httpx.Client(transport=httpx.MockTransport(responder))
    schedule.fetch(schedule.search_url("x"), client=client)
    client.close()
    agent = seen[0].headers["User-Agent"]
    assert "openmind" in agent and "github.com" in agent


def test_an_http_error_is_reported_not_swallowed():
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(503, request=request))
    )
    with pytest.raises(schedule.ScheduleError, match="503"):
        schedule.fetch("https://classes.berkeley.edu/search/class?search=x", client=client)
    client.close()


def test_a_crawl_stops_once_the_results_drift_off_the_subject(monkeypatch, results_html: str):
    """Solr keeps returning matches long after the subject runs out."""
    monkeypatch.setattr(schedule.time, "sleep", lambda _: None)
    pages: list[str] = []

    def responder(request: httpx.Request) -> httpx.Response:
        pages.append(str(request.url))
        if len(pages) <= 2:
            return httpx.Response(200, text=results_html, request=request)
        return httpx.Response(200, text="<html><body>nothing</body></html>", request=request)

    client = httpx.Client(transport=httpx.MockTransport(responder))
    sections = schedule.crawl_subject("STAT", "8588", client=client, delay=0)
    client.close()

    assert sections
    assert len(pages) <= 4


# -- collapsing to offerings ---------------------------------------------------


def test_sections_collapse_into_one_row_per_course(results_html: str):
    sections, _ = schedule.parse_sections(SUBJECT_PAGE.read_text(encoding="utf-8"))
    offerings = schedule.collapse(
        [s for s in sections if schedule.subject_of(s.course_code) == "STAT"], "Fall 2026"
    )
    assert offerings
    row = offerings[0].to_row()
    assert row["subject"] == "STAT"
    assert row["term"] == "Fall 2026"
    assert int(row["section_count"]) >= 1
    assert row["instruction_modes"]


def test_multiple_sections_of_one_course_are_counted_together():
    sections = [
        schedule.Section(course_code="STAT 156", instructors="Peng Ding", instruction_mode="In-Person Instruction"),
        schedule.Section(course_code="STAT 156", instructors="Someone Else", instruction_mode="Remote Instruction"),
    ]
    row = schedule.collapse(sections, "Fall 2026")[0].to_row()
    assert row["section_count"] == "2"
    assert "Peng Ding" in row["instructors"] and "Someone Else" in row["instructors"]
    assert "In-Person Instruction" in row["instruction_modes"]


def test_unparseable_course_codes_are_dropped_rather_than_guessed():
    assert schedule.collapse([schedule.Section(course_code="not a code")], "Fall 2026") == []


@pytest.mark.parametrize(
    ("code", "subject"), [("STAT 156", "STAT"), ("INTEGBI C156", "INTEGBI"), ("stat   156", "STAT"), ("156", "")]
)
def test_subjects_are_extracted_from_course_codes(code: str, subject: str):
    assert schedule.subject_of(code) == subject
