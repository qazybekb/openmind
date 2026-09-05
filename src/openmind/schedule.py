"""Read live section data from the Berkeley class schedule.

`classes.berkeley.edu` is a Drupal site with a Solr search and no JSON API, so this is
an HTML parser. It is the only part of OpenMind whose contract belongs to someone else's
markup, which is why every selector here is exercised by fixture tests: when the
Registrar restyles the site, CI fails loudly instead of quietly reporting that no
courses are offered.

Two things about the site shape this module. Facet-only URLs (``f[0]=term:8588``) render
an empty results container and fill it in with JavaScript, so they are useless to a
plain HTTP client; adding a ``search=`` keyword makes the same view render server-side.
Everything here therefore goes through keyword search, with the term facet applied, and
filters the generous Solr results back down to the course actually asked for.

The parser is shared by two callers with very different manners: the nightly refresh
job, which crawls politely with a delay between pages, and the `check_offering` tool,
which makes one request and caches the answer for a day.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Final
from urllib.parse import urlencode, urljoin

logger = logging.getLogger(__name__)

BASE_URL: Final[str] = "https://classes.berkeley.edu"
SEARCH_PATH: Final[str] = "/search/class"
USER_AGENT: Final[str] = "openmind-berkeley/2.0 (UC Berkeley student tool; +https://github.com/qazybekb/openmind)"
TIMEOUT_S: Final[float] = 30.0
POLITE_DELAY_S: Final[float] = 1.0
MAX_PAGES: Final[int] = 40
RESULTS_PER_PAGE: Final[int] = 18

# Text-bearing leaf classes on a result card. Container classes (st--wrapper,
# st--content, st--meetings, …) are deliberately absent: collecting them would
# duplicate every child's text into the parent.
CARD_FIELDS: Final[frozenset[str]] = frozenset({
    "st--term-year", "st--section-number", "st--section-name", "st--section-count",
    "st--section-code", "st--title", "st--instructors", "st--meeting-dates",
    "st--meeting-days", "st--meeting-time", "st--location", "st--details-unit",
    "st--extras", "st--seats", "st--description", "st--formerly", "st--open-toggle",
})


class ScheduleError(Exception):
    """The class schedule could not be read."""


@dataclass
class Section:
    """One scheduled section of a course."""

    course_code: str = ""
    title: str = ""
    ccn: str = ""
    section: str = ""
    kind: str = ""
    instructors: str = ""
    days: str = ""
    time: str = ""
    location: str = ""
    open_seats: str = ""
    status: str = ""
    instruction_mode: str = ""
    units: str = ""
    term: str = ""
    url: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Render for a tool payload, dropping fields the site did not provide."""
        return {key: value for key, value in {
            "course": self.course_code,
            "title": self.title,
            "ccn": self.ccn,
            "section": self.section,
            "type": self.kind,
            "instructors": self.instructors,
            "days": self.days,
            "time": self.time,
            "location": self.location,
            "open_seats": self.open_seats,
            "status": self.status,
            "instruction_mode": self.instruction_mode,
            "units": self.units,
            "url": self.url,
        }.items() if value}


@dataclass
class Facet:
    """One entry in the schedule's facet sidebar."""

    facet_id: str
    name: str
    count: int = 0


# -- HTML parsing --------------------------------------------------------------


class _CardParser(HTMLParser):
    """Pull ``article.st`` result cards out of a rendered search results page."""

    # HTML5 void elements never get an end tag, so counting them would leave the
    # nesting depth permanently off and the card would never close.
    _VOID: Final[frozenset[str]] = frozenset({
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "param", "source", "track", "wbr",
    })

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[dict[str, list[str]]] = []
        self.next_page: str | None = None
        self._card: dict[str, list[str]] | None = None
        self._depth = 0
        self._open_fields: list[tuple[str, int]] = []
        self._buffer: list[str] = []
        self._card_url = ""
        self._pager_next_depth: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: (value or "") for key, value in attrs}
        classes = attributes.get("class", "").split()

        if self._card is None and tag == "article" and "st" in classes:
            self._card = {}
            self._card_url = ""
            self._depth = 0
            self._open_fields = []
            self._buffer = []
            return

        if self._card is not None:
            if tag == "a" and not self._card_url and "/content/" in attributes.get("href", ""):
                self._card_url = urljoin(BASE_URL, attributes["href"])
            if tag in self._VOID:
                return
            self._depth += 1
            for name in classes:
                if name in CARD_FIELDS:
                    self._flush()
                    self._open_fields.append((name, self._depth))
                    break
            return

        # Pagination lives outside the cards: <li class="pager__item--next"><a href="?…page=1">
        if tag == "li" and "pager__item--next" in classes:
            self._pager_next_depth = 0
        elif self._pager_next_depth is not None:
            if tag == "a" and attributes.get("href") and self.next_page is None:
                self.next_page = attributes["href"]
                self._pager_next_depth = None
            else:
                self._pager_next_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._card is None:
            if tag == "li" and self._pager_next_depth is not None:
                self._pager_next_depth = None
            return

        while self._open_fields and self._open_fields[-1][1] >= self._depth:
            self._flush()
        if self._depth == 0 and tag == "article":
            self._flush()
            if self._card_url:
                self._card["url"] = [self._card_url]
            self.cards.append(self._card)
            self._card = None
            self._open_fields = []
            return
        self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._card is not None and self._open_fields:
            self._buffer.append(data)

    def _flush(self) -> None:
        """Store the text collected for the innermost open field."""
        if self._card is None or not self._open_fields:
            self._buffer = []
            return
        name, _ = self._open_fields.pop()
        text = " ".join("".join(self._buffer).split())
        self._buffer = []
        if text:
            self._card.setdefault(name, []).append(text)


class _FacetParser(HTMLParser):
    """Read facet ids and labels out of the search sidebar."""

    def __init__(self, facet_name: str) -> None:
        super().__init__(convert_charrefs=True)
        self._pattern = re.compile(rf"f%5B\d+%5D={facet_name}%3A(\d+)|f\[\d+\]={facet_name}:(\d+)")
        self.entries: list[Facet] = []
        self._current: str | None = None
        self._buffer: list[str] = []
        self._seen: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a" or self._current:
            return
        match = self._pattern.search(dict(attrs).get("href") or "")
        if match:
            self._current = match.group(1) or match.group(2)
            self._buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._current:
            return
        text = " ".join("".join(self._buffer).split())
        count_match = re.search(r"\((\d[\d,]*)\)\s*$", text)
        count = int(count_match.group(1).replace(",", "")) if count_match else 0
        name = re.sub(r"\s*\(\d[\d,]*\)\s*$", "", text).strip()
        if name and self._current not in self._seen:
            self._seen.add(self._current)
            self.entries.append(Facet(facet_id=self._current, name=name, count=count))
        self._current = None
        self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._current:
            self._buffer.append(data)


# -- card mapping --------------------------------------------------------------


def _first(card: dict[str, list[str]], name: str, default: str = "") -> str:
    """Return the first captured value for a card field."""
    values = card.get(name)
    return values[0] if values else default


def _strip_label(text: str, *labels: str) -> str:
    """Remove a leading ``Label:`` prefix the site renders inside the value."""
    cleaned = text
    for label in labels:
        cleaned = re.sub(rf"^\s*{re.escape(label)}\s*:?\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def card_to_section(card: dict[str, list[str]]) -> Section:
    """Map one parsed card onto a :class:`Section`."""
    counts = card.get("st--section-count", [])
    numbers = card.get("st--section-number", [])
    ccn = ""
    for value in numbers:
        digits = re.search(r"(\d{4,6})", value)
        if digits:
            ccn = digits.group(1)
            break

    seats = _first(card, "st--seats")
    seat_match = re.search(r"(\d[\d,]*)\s+(?:Unreserved\s+)?Seats?", seats, re.IGNORECASE)

    extras = _first(card, "st--extras")
    mode_match = re.search(r"Instruction Mode\s*:?\s*(.+)", extras, re.IGNORECASE)

    toggle = _first(card, "st--open-toggle")
    status_match = re.search(r"section\s+(open|closed|waitlist\w*)", toggle, re.IGNORECASE)

    return Section(
        course_code=normalise_course_code(_first(card, "st--section-name")),
        title=_first(card, "st--title"),
        ccn=ccn,
        section=counts[0] if counts else "",
        kind=_first(card, "st--section-code"),
        instructors=_first(card, "st--instructors"),
        days=_first(card, "st--meeting-days"),
        time=_first(card, "st--meeting-time"),
        location=_first(card, "st--location"),
        open_seats=seat_match.group(1) if seat_match else "",
        status=status_match.group(1).lower() if status_match else "",
        instruction_mode=mode_match.group(1).strip() if mode_match else "",
        units=_strip_label(_first(card, "st--details-unit"), "Units"),
        term=_first(card, "st--term-year"),
        url=_first(card, "url"),
    )


def normalise_course_code(code: str) -> str:
    """Collapse a course code to ``SUBJECT NUMBER`` with single spaces."""
    return " ".join((code or "").upper().split())


def subject_of(course_code: str) -> str:
    """Return the subject part of a course code, or "" when it is not one."""
    from openmind.catalog import parse_course_code

    parsed = parse_course_code(normalise_course_code(course_code))
    return parsed[0] if parsed else ""


# -- HTTP ----------------------------------------------------------------------


def search_url(keyword: str, term_facet: str | None = None, *, page: int = 0) -> str:
    """Build a schedule search URL.

    A keyword is required: without one the site renders an empty container and fills it
    in with JavaScript, which a plain HTTP client never sees.
    """
    params: list[tuple[str, str]] = []
    if term_facet:
        params.append(("f[0]", f"term:{term_facet}"))
    params.append(("search", keyword))
    if page:
        params.append(("page", str(page)))
    return f"{BASE_URL}{SEARCH_PATH}?{urlencode(params)}"


def fetch(url: str, *, client: Any = None) -> str:
    """GET one page from the schedule site with a polite user agent."""
    import httpx

    owned = client is None
    http = client or httpx.Client(timeout=TIMEOUT_S, follow_redirects=True)
    try:
        response = http.get(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
        if response.status_code >= 400:
            raise ScheduleError(f"The Berkeley class schedule returned HTTP {response.status_code}.")
        return response.text
    except ScheduleError:
        raise
    except Exception as exc:
        logger.warning("Class schedule request failed: %s", type(exc).__name__)
        raise ScheduleError("Could not reach the Berkeley class schedule.") from exc
    finally:
        if owned:
            http.close()


def parse_sections(html: str, *, page_url: str = BASE_URL + SEARCH_PATH) -> tuple[list[Section], str | None]:
    """Parse a results page into sections and the absolute URL of the next page."""
    parser = _CardParser()
    parser.feed(html)
    parser.close()
    if not parser.cards and "<article" in html and "st--section-name" in html:
        raise ScheduleError("The class schedule page changed shape; the parser found no result cards.")
    next_page = urljoin(page_url, parser.next_page) if parser.next_page else None
    return [card_to_section(card) for card in parser.cards], next_page


def parse_terms(html: str) -> list[Facet]:
    """Parse the term facet list, newest first as the site orders it."""
    parser = _FacetParser("term")
    parser.feed(html)
    parser.close()
    return parser.entries


def parse_subjects(html: str) -> list[Facet]:
    """Parse the subject-area facet list."""
    parser = _FacetParser("subject_area")
    parser.feed(html)
    parser.close()
    return parser.entries


def list_terms(*, client: Any = None) -> list[Facet]:
    """Return the terms the schedule currently publishes, newest first."""
    terms = parse_terms(fetch(f"{BASE_URL}{SEARCH_PATH}", client=client))
    if not terms:
        raise ScheduleError("Could not read the term list from the Berkeley class schedule.")
    return terms


_SEASON_ORDER: Final[dict[str, int]] = {"spring": 0, "summer": 1, "fall": 2}


def term_sort_key(name: str) -> tuple[int, int]:
    """Return a sortable (year, season) key for a term label like ``Fall 2026``."""
    match = re.match(r"^(Fall|Spring|Summer)(?:\s+Sessions)?\s+(\d{4})$", name.strip(), re.IGNORECASE)
    if not match:
        return (-1, -1)
    return (int(match.group(2)), _SEASON_ORDER.get(match.group(1).lower(), 0))


def is_full_semester(name: str) -> bool:
    """Return whether a term facet is a full semester rather than a summer sub-session.

    The schedule lists "Summer Sessions 2026" alongside its own sub-sessions ("12W",
    "A: May 26-July 2", …), so counting the umbrella entry would double-count every
    summer section. Course planning means Fall and Spring.
    """
    return term_sort_key(name) != (-1, -1) and "Sessions" not in name


def full_semesters(terms: list[Facet]) -> list[Facet]:
    """Filter a facet list down to full semesters."""
    return [term for term in terms if is_full_semester(term.name)]


def newest_term(terms: list[Facet]) -> Facet | None:
    """Return the latest full semester the schedule publishes.

    The Registrar posts one term ahead at most, so this is the answer to "what can I
    actually sign up for" — and when Spring 2027 appears, it becomes the answer with no
    code change.
    """
    semesters = full_semesters(terms)
    if not semesters:
        return terms[0] if terms else None
    return max(semesters, key=lambda t: term_sort_key(t.name))


def sorted_terms(terms: list[Facet]) -> list[Facet]:
    """Return full semesters newest first."""
    return sorted(full_semesters(terms), key=lambda t: term_sort_key(t.name), reverse=True)


def find_sections(course_code: str, term_facet: str | None = None, *, client: Any = None,
                  limit: int = 25) -> list[Section]:
    """Look up the live sections of one course. One request."""
    wanted = normalise_course_code(course_code)
    sections, _ = parse_sections(
        fetch(search_url(wanted, term_facet), client=client), page_url=search_url(wanted, term_facet)
    )
    exact = [s for s in sections if s.course_code == wanted]
    return exact[:limit]


def crawl_subject(subject: str, term_facet: str, *, client: Any = None, max_pages: int = MAX_PAGES,
                  delay: float = POLITE_DELAY_S) -> list[Section]:
    """Page through a term's sections for one subject code.

    Solr ranks exact matches first and then drifts into courses that merely mention the
    subject, so paging stops after two consecutive pages with nothing from the subject
    we asked about.
    """
    wanted = subject.strip().upper()
    collected: list[Section] = []
    url: str | None = search_url(wanted, term_facet)
    barren = 0
    for page in range(max_pages):
        if url is None:
            break
        current = url
        sections, url = parse_sections(fetch(current, client=client), page_url=current)
        matching = [s for s in sections if subject_of(s.course_code) == wanted]
        collected.extend(matching)
        barren = 0 if matching else barren + 1
        if barren >= 2 or not sections:
            break
        if delay and page + 1 < max_pages:
            time.sleep(delay)
    return collected


@dataclass
class TermOffering:
    """Every section of one course in one term, collapsed into a single row."""

    subject: str
    number: str
    term: str
    section_count: int = 0
    instruction_modes: set[str] = field(default_factory=set)
    instructors: set[str] = field(default_factory=set)

    def to_row(self) -> dict[str, str]:
        """Render as a ``term_offerings.csv`` row."""
        return {
            "subject": self.subject,
            "number": self.number,
            "term": self.term,
            "section_count": str(self.section_count),
            "instruction_modes": "; ".join(sorted(m for m in self.instruction_modes if m)),
            "instructors": "; ".join(sorted(i for i in self.instructors if i)[:6]),
        }


def collapse(sections: list[Section], term: str) -> list[TermOffering]:
    """Group sections into one offering row per course."""
    from openmind.catalog import parse_course_code

    grouped: dict[tuple[str, str], TermOffering] = {}
    for section in sections:
        parsed = parse_course_code(section.course_code)
        if not parsed:
            continue
        subject, number = parsed
        offering = grouped.setdefault((subject, number), TermOffering(subject=subject, number=number, term=term))
        offering.section_count += 1
        if section.instruction_mode:
            offering.instruction_modes.add(section.instruction_mode)
        for name in re.split(r"[;,]", section.instructors):
            cleaned = name.strip()
            if cleaned:
                offering.instructors.add(cleaned)
    return [grouped[key] for key in sorted(grouped)]
