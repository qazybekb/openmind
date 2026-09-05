"""Document extraction bounds, SSRF handling, chunking, and the FTS index."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import httpx
import pytest

from openmind import index, materials
from openmind.materials import Chunk, MaterialError

# -- building test documents ---------------------------------------------------


def make_pdf(pages: list[str], *, header: str | None = None) -> bytes:
    """Build a small real PDF with pypdf so extraction is exercised, not mocked."""
    from pypdf import PdfWriter

    try:
        from reportlab.pdfgen import canvas as reportlab_canvas  # type: ignore
    except ImportError:
        reportlab_canvas = None

    if reportlab_canvas is None:
        pytest.skip("reportlab is not installed; PDF text fixtures need a writer")

    buffer = io.BytesIO()
    pdf = reportlab_canvas.Canvas(buffer)
    for text in pages:
        if header:
            pdf.drawString(72, 800, header)
        pdf.drawString(72, 700, text)
        pdf.showPage()
    pdf.save()
    writer = PdfWriter(clone_from=io.BytesIO(buffer.getvalue()))
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def make_pptx(slides: list[list[str]]) -> bytes:
    """Build a minimal .pptx with the parts the extractor reads."""
    buffer = io.BytesIO()
    ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        for number, lines in enumerate(slides, start=1):
            body = "".join(f"<a:t>{line}</a:t>" for line in lines)
            archive.writestr(
                f"ppt/slides/slide{number}.xml", f'<a:sld xmlns:a="{ns}">{body}</a:sld>'
            )
    return buffer.getvalue()


def make_docx(paragraphs: list[str]) -> bytes:
    """Build a minimal .docx with the parts the extractor reads."""
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", f'<w:document xmlns:w="{ns}"><w:body>{body}</w:body></w:document>')
    return buffer.getvalue()


# -- SSRF ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/secrets",
        "http://127.0.0.1:8080/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://10.0.0.5/internal",
        "file:///etc/passwd",
        "gopher://example.test/",
        "https:///no-host",
    ],
)
def test_unsafe_destinations_are_blocked(url: str):
    assert materials.is_safe_url(url) is not None


def test_a_public_https_url_is_allowed():
    assert materials.is_safe_url("https://bcourses.berkeley.edu/files/1/download") is None


def test_a_redirect_to_a_private_address_is_blocked_mid_download():
    def redirector(request: httpx.Request) -> httpx.Response:
        if "start" in str(request.url):
            return httpx.Response(302, headers={"location": "http://127.0.0.1/steal"}, request=request)
        return httpx.Response(200, content=b"nope", request=request)

    client = httpx.Client(transport=httpx.MockTransport(redirector), follow_redirects=False)
    with pytest.raises(MaterialError, match="after a redirect"):
        materials.download("https://bcourses.berkeley.edu/start", client=client)
    client.close()


def test_the_bearer_token_is_dropped_once_the_download_leaves_bcourses(public_dns):
    """Canvas file URLs redirect to signed S3 links; the token must not follow."""
    seen: list[tuple[str, str | None]] = []

    def redirector(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.headers.get("Authorization")))
        if request.url.host == "bcourses.berkeley.edu":
            return httpx.Response(
                302, headers={"location": "https://s3.amazonaws.test/file.pdf?sig=x"}, request=request
            )
        return httpx.Response(200, content=b"%PDF-1.4 body", headers={"content-type": "application/pdf"},
                              request=request)

    client = httpx.Client(transport=httpx.MockTransport(redirector), follow_redirects=False)
    body, content_type, final = materials.download(
        "https://bcourses.berkeley.edu/files/1/download", token="secret", client=client
    )
    client.close()

    assert seen[0][1] == "Bearer secret"
    assert seen[1][1] is None, "the token must not be sent to the storage host"
    assert body.startswith(b"%PDF")
    assert final.startswith("https://s3.amazonaws.test/")


def test_an_oversized_declared_length_is_refused_before_the_body_is_read():
    def big(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 10, headers={"content-length": str(60 * 1024 * 1024)},
                              request=request)

    client = httpx.Client(transport=httpx.MockTransport(big), follow_redirects=False)
    with pytest.raises(MaterialError, match="60 MB, larger than the 25 MB"):
        materials.download("https://bcourses.berkeley.edu/files/1", client=client)
    client.close()


def test_a_body_that_grows_past_the_cap_is_cut_off():
    def big(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 4096, request=request)

    client = httpx.Client(transport=httpx.MockTransport(big), follow_redirects=False)
    with pytest.raises(MaterialError, match="larger than the 1 KB limit"):
        materials.download("https://bcourses.berkeley.edu/files/1", max_bytes=1024, client=client)
    client.close()


# -- extraction ----------------------------------------------------------------


def test_pdf_text_is_extracted_page_by_page():
    body = make_pdf(["Confounding is a backdoor path.", "Randomisation breaks it."])
    result = materials.extract(body, "week3.pdf")
    assert result.status == "indexed"
    assert result.page_count == 2
    assert "Confounding" in result.pages[0]
    assert "Randomisation" in result.pages[1]


def test_a_running_header_is_dropped_from_every_page():
    body = make_pdf([f"Slide {n} content here" for n in range(1, 9)], header="STAT 156 Fall 2026")
    result = materials.extract(body, "deck.pdf")
    assert result.status == "indexed"
    assert "STAT 156 Fall 2026" not in result.text
    assert "Slide 1 content here" in result.text


def test_a_scanned_pdf_says_so_instead_of_returning_nothing():
    body = make_pdf(["", "", "", "", ""])
    result = materials.extract(body, "scan.pdf")
    assert result.status == "skipped"
    assert "scanned" in (result.note or "")


def test_a_corrupt_pdf_fails_cleanly():
    result = materials.extract(b"%PDF-1.4 truncated garbage", "broken.pdf")
    assert result.status in {"failed", "skipped"}
    assert result.note


def test_slides_become_one_page_per_slide():
    body = make_pptx([["Title slide", "STAT 156"], ["Confounding", "A backdoor path"]])
    result = materials.extract(body, "lecture.pptx")
    assert result.page_count == 2
    assert "Confounding" in result.pages[1]


def test_word_documents_are_read():
    body = make_docx(["Assignment 1", "Estimate the treatment effect."])
    result = materials.extract(body, "hw.docx")
    assert result.status == "indexed"
    assert "treatment effect" in result.text


@pytest.mark.parametrize(
    ("name", "fragment"),
    [("video.mp4", "video"), ("data.xlsx", "spreadsheet"), ("notes.ipynb", "notebook"),
     ("old.doc", "old Word"), ("diagram.png", "image")],
)
def test_file_types_we_cannot_read_are_named_not_ignored(name: str, fragment: str):
    result = materials.extract(b"whatever", name)
    assert result.status == "skipped"
    assert fragment in (result.note or "")


def test_plain_text_and_html_are_read_directly():
    assert "hello" in materials.extract(b"hello world", "notes.txt").text
    result = materials.extract(b"<h2>Grading</h2><p>40% homework</p>", "page.html")
    assert "40% homework" in result.text


def test_html_flattening_drops_scripts_and_keeps_headings():
    text = materials.html_to_text(
        "<h2>Policy</h2><p>Late work loses 10%.</p><script>alert(1)</script><style>p{}</style>"
    )
    assert "## Policy" in text
    assert "Late work loses 10%." in text
    assert "alert" not in text


def test_html_entities_survive_flattening():
    assert "R&D" in materials.html_to_text("<p>R&amp;D</p>")


# -- chunking ------------------------------------------------------------------


def test_chunks_never_straddle_a_page_boundary():
    pages = ["Page one text. " * 30, "Page two text. " * 30]
    chunks = materials.chunk_pages(pages)
    assert chunks
    for chunk in chunks:
        assert chunk.page_start == chunk.page_end


def test_slide_chunks_accumulate_until_they_are_worth_retrieving():
    pages = [f"Slide {n}." for n in range(1, 41)]
    chunks = materials.chunk_pages(pages, slides=True)
    assert len(chunks) < len(pages)
    assert chunks[0].page_end > chunks[0].page_start


def test_headings_are_carried_onto_the_chunks_beneath_them():
    chunks = materials.chunk_pages(["## Grading\n\nHomework is 30%.\n\n## Exams\n\nTwo midterms."])
    headings = [chunk.heading for chunk in chunks]
    assert "Grading" in headings and "Exams" in headings


def test_an_oversized_paragraph_is_split_rather_than_dropped():
    chunks = materials.chunk_pages(["x" * 5000])
    assert len(chunks) >= 3
    assert all(len(chunk.text) <= materials.CHUNK_MAX for chunk in chunks)


def test_citations_name_the_page_or_the_range():
    assert materials.cite("Week 3", 4, 4) == "(Week 3, p. 4)"
    assert materials.cite("Deck", 2, 5) == "(Deck, pp. 2-5)"
    assert materials.cite("Syllabus", 1, 1, "Grading", paged=False) == "(Syllabus, Grading)"


# -- index ---------------------------------------------------------------------


def test_fts5_is_available_in_this_python():
    assert index.fts5_available()


def test_search_finds_text_inside_a_document_and_cites_the_page(home: Path):
    with index.connect() as conn:
        material_id = index.upsert_material(
            conn, course_id="1001", kind="file", canvas_id="501", title="Week 3 Slides", module_name="Week 3"
        )
        index.store_chunks(conn, material_id, "Week 3 Slides", [
            Chunk(ord=0, text="A confounder causes both the treatment and the outcome.", page_start=4, page_end=4),
            Chunk(ord=1, text="Randomisation removes confounding in expectation.", page_start=9, page_end=9),
        ], page_count=20)

        hits = index.search(conn, "1001", "confounder")
        # The porter stemmer matches "confounding" as well, which is the point of it.
        assert {hit.to_dict()["cite"] for hit in hits} == {
            "(Week 3 Slides, p. 4)", "(Week 3 Slides, p. 9)"
        }
        assert all(hit.to_dict()["module"] == "Week 3" for hit in hits)
        assert any("[confounder]" in hit.snippet for hit in hits)


def test_a_query_that_matches_no_single_document_still_widens_to_or(home: Path):
    with index.connect() as conn:
        material_id = index.upsert_material(conn, course_id="1", kind="page", canvas_id="p", title="Notes")
        index.store_chunks(conn, material_id, "Notes", [
            Chunk(ord=0, text="Randomisation is the gold standard.", page_start=1, page_end=1)
        ])
        assert index.search(conn, "1", "randomisation quantum") != []


@pytest.mark.parametrize("query", ['NEAR("a" "b")', "confounder*", 'x" OR "y', "a OR b", "-- drop", "(((", '"'])
def test_fts_operators_in_a_query_are_treated_as_literal_words(query: str, home: Path):
    """A document title or a model must not be able to inject query syntax."""
    with index.connect() as conn:
        material_id = index.upsert_material(conn, course_id="1", kind="page", canvas_id="p", title="Notes")
        index.store_chunks(conn, material_id, "Notes", [
            Chunk(ord=0, text="ordinary text", page_start=1, page_end=1)
        ])
        index.search(conn, "1", query)  # must not raise
        expression = index.build_match(query)
        assert "*" not in expression
        assert "(" not in expression and ")" not in expression
        # Every token is a quoted literal, so quotes come only in balanced pairs.
        assert expression.count('"') % 2 == 0


def test_at_most_two_chunks_come_from_one_document(home: Path):
    with index.connect() as conn:
        material_id = index.upsert_material(conn, course_id="1", kind="file", canvas_id="f", title="Long Deck")
        index.store_chunks(conn, material_id, "Long Deck", [
            Chunk(ord=n, text=f"confounding appears again on page {n}", page_start=n + 1, page_end=n + 1)
            for n in range(10)
        ])
        assert len(index.search(conn, "1", "confounding", limit=10)) == 2


def test_a_skipped_material_records_why(home: Path):
    with index.connect() as conn:
        material_id = index.upsert_material(conn, course_id="1", kind="file", canvas_id="v", title="lecture.mp4")
        index.mark(conn, material_id, "skipped", "video — no transcript available")
        rows = index.list_materials(conn, "1")
    assert rows[0]["status"] == "skipped"
    assert "transcript" in rows[0]["note"]


def test_a_changed_source_marks_a_material_pending_again(home: Path):
    with index.connect() as conn:
        first = index.upsert_material(conn, course_id="1", kind="file", canvas_id="f", title="Deck",
                                      source_updated_at="2026-09-01T00:00:00Z")
        index.store_chunks(conn, first, "Deck", [Chunk(ord=0, text="old", page_start=1, page_end=1)])
        assert index.course_stats(conn, "1")["indexed"] == 1

        index.upsert_material(conn, course_id="1", kind="file", canvas_id="f", title="Deck",
                              source_updated_at="2026-09-20T00:00:00Z")
        conn.commit()
        assert index.course_stats(conn, "1")["pending"] == 1


def test_clearing_a_course_removes_its_chunks_too(home: Path):
    with index.connect() as conn:
        material_id = index.upsert_material(conn, course_id="1", kind="page", canvas_id="p", title="Notes")
        index.store_chunks(conn, material_id, "Notes", [Chunk(ord=0, text="text", page_start=1, page_end=1)])
        index.clear_course(conn, "1")
        assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0
        assert index.search(conn, "1", "text") == []


def test_clearing_everything_deletes_the_file(home: Path):
    with index.connect() as conn:
        index.upsert_material(conn, course_id="1", kind="page", canvas_id="p", title="Notes")
        conn.commit()
    assert index.clear_all() is True
    assert index.clear_all() is False


def test_reading_a_missing_index_names_the_command_to_run(home: Path):
    with pytest.raises(index.IndexError_, match="openmind index"), index.connect(create=False):
        pass
