"""Turn course files and pages into plain text, within strict bounds.

Everything here treats a document as hostile input: it is downloaded to memory (never
to disk), capped on size, pages, characters, and wall-clock time, and the extracted
text is only ever handed back as *evidence*, never as instructions. The Bearer token is
dropped the moment a download redirects off bCourses, because Canvas file URLs redirect
to a signed S3 URL that neither wants nor should receive it.
"""

from __future__ import annotations

import io
import ipaddress
import logging
import re
import socket
import time
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Final
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import httpx

from openmind.config import ALLOWED_CANVAS_HOSTS

logger = logging.getLogger(__name__)

MAX_DOWNLOAD_BYTES: Final[int] = 25 * 1024 * 1024
MAX_PAGES: Final[int] = 400
MAX_CHARS: Final[int] = 400_000
MAX_SECONDS: Final[float] = 20.0
MAX_REDIRECTS: Final[int] = 5
DOWNLOAD_TIMEOUT_S: Final[float] = 60.0

CHUNK_TARGET: Final[int] = 1_200
CHUNK_MAX: Final[int] = 1_800
SLIDE_MIN: Final[int] = 600

BLOCKED_HOSTS: Final[frozenset[str]] = frozenset({"0.0.0.0", "127.0.0.1", "::1", "localhost"})
USER_AGENT: Final[str] = "openmind-berkeley (+https://github.com/qazybekb/openmind)"

SUPPORTED_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {".pdf", ".pptx", ".docx", ".txt", ".md", ".markdown", ".html", ".htm", ".csv", ".rtf"}
)
UNSUPPORTED_NOTE: Final[dict[str, str]] = {
    ".doc": "old Word format (.doc) — no text extractor; open it in bCourses",
    ".ppt": "old PowerPoint format (.ppt) — no text extractor; open it in bCourses",
    ".xls": "spreadsheet — not indexed",
    ".xlsx": "spreadsheet — not indexed",
    ".ipynb": "notebook — not indexed",
    ".zip": "archive — not indexed",
    ".mp4": "video — no transcript available through the Canvas API",
    ".mov": "video — no transcript available through the Canvas API",
    ".mp3": "audio — no transcript available through the Canvas API",
    ".png": "image — no text layer",
    ".jpg": "image — no text layer",
    ".jpeg": "image — no text layer",
    ".gif": "image — no text layer",
}


class MaterialError(Exception):
    """A material could not be fetched or read."""


@dataclass
class Extraction:
    """The text of one document, page by page."""

    pages: list[str] = field(default_factory=list)
    page_count: int = 0
    char_count: int = 0
    truncated: bool = False
    status: str = "indexed"
    note: str | None = None

    @property
    def text(self) -> str:
        """Return the whole document as one string."""
        return "\n\n".join(self.pages)


# -- SSRF guards --------------------------------------------------------------


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return whether an IP address must not be contacted."""
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_multicast or ip.is_reserved or ip.is_unspecified
    )


def is_safe_url(url: str) -> str | None:
    """Validate a URL for SSRF safety, returning an error message when unsafe."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        return f"Blocked scheme: {parsed.scheme or 'none'}. Only http and https are allowed."
    if not parsed.hostname:
        return "Blocked: the URL has no hostname."

    host = parsed.hostname.rstrip(".").lower()
    if host in BLOCKED_HOSTS:
        return "Blocked: localhost and loopback URLs are not allowed."

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        try:
            resolved = socket.getaddrinfo(
                host, parsed.port or (443 if scheme == "https" else 80), type=socket.SOCK_STREAM
            )
        except socket.gaierror:
            return "Blocked: the hostname could not be resolved."
        if not resolved:
            return "Blocked: the hostname did not resolve to any address."
        for entry in resolved:
            if _is_blocked_ip(ipaddress.ip_address(entry[4][0])):
                return "Blocked: the hostname resolves to a private or local address."
        return None

    return "Blocked: private and local IP addresses are not allowed." if _is_blocked_ip(ip) else None


def human_size(byte_count: int) -> str:
    """Render a byte count the way a student would read it."""
    if byte_count >= 1024 * 1024:
        return f"{byte_count / (1024 * 1024):.0f} MB"
    if byte_count >= 1024:
        return f"{byte_count / 1024:.0f} KB"
    return f"{byte_count} bytes"


def _on_canvas(url: str) -> bool:
    """Return whether a URL points at the allowed bCourses host."""
    return (urlparse(url).hostname or "").lower().rstrip(".") in ALLOWED_CANVAS_HOSTS


def download(url: str, *, token: str | None = None, max_bytes: int = MAX_DOWNLOAD_BYTES,
             client: httpx.Client | None = None) -> tuple[bytes, str, str]:
    """Download a document into memory and return ``(body, content_type, final_url)``.

    Redirects are followed by hand so each hop can be re-checked for SSRF safety, and so
    the Authorization header can be dropped as soon as the chain leaves bCourses.
    """
    error = is_safe_url(url)
    if error:
        raise MaterialError(error)

    owned = client is None
    http = client or httpx.Client(timeout=DOWNLOAD_TIMEOUT_S, follow_redirects=False)
    current = url
    try:
        for _ in range(MAX_REDIRECTS + 1):
            headers = {"User-Agent": USER_AGENT}
            if token and _on_canvas(current):
                headers["Authorization"] = f"Bearer {token}"
            with http.stream("GET", current, headers=headers, follow_redirects=False) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location", "")
                    if not location:
                        raise MaterialError("The download redirected without a destination.")
                    target = location if location.startswith("http") else urljoin(current, location)
                    redirect_error = is_safe_url(target)
                    if redirect_error:
                        raise MaterialError(f"Download blocked after a redirect: {redirect_error}")
                    current = target
                    continue
                if response.status_code >= 400:
                    raise MaterialError(f"The file could not be downloaded (HTTP {response.status_code}).")

                declared = response.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > max_bytes:
                    raise MaterialError(
                        f"That file is {human_size(int(declared))}, larger than the {human_size(max_bytes)} "
                        "limit. Open it in bCourses instead."
                    )

                buffer = bytearray()
                for chunk in response.iter_bytes():
                    buffer.extend(chunk)
                    if len(buffer) > max_bytes:
                        raise MaterialError(
                            f"That file is larger than the {human_size(max_bytes)} limit. "
                            "Open it in bCourses instead."
                        )
                return bytes(buffer), response.headers.get("content-type", "").lower(), str(response.url)
        raise MaterialError("The download followed too many redirects.")
    except httpx.HTTPError as exc:
        logger.warning("Download failed for a course material: %s", type(exc).__name__)
        raise MaterialError("The file could not be downloaded.") from exc
    finally:
        if owned:
            http.close()


# -- extractors ---------------------------------------------------------------


def extension_of(name: str) -> str:
    """Return the lowercase extension of a filename, including the dot."""
    match = re.search(r"(\.[A-Za-z0-9]{1,10})$", (name or "").strip())
    return match.group(1).lower() if match else ""


def unsupported_reason(name: str, content_type: str = "") -> str | None:
    """Return why a file cannot be read, or ``None`` when it can be."""
    ext = extension_of(name)
    if ext in SUPPORTED_EXTENSIONS:
        return None
    if ext in UNSUPPORTED_NOTE:
        return UNSUPPORTED_NOTE[ext]
    if "pdf" in content_type:
        return None
    if content_type.startswith(("text/", "application/xhtml")):
        return None
    return f"unsupported file type ({ext or content_type or 'unknown'})"


def extract(body: bytes, name: str, content_type: str = "") -> Extraction:
    """Extract text from a document, choosing the reader by extension then content type."""
    ext = extension_of(name)
    if ext == ".pdf" or (not ext and "pdf" in content_type):
        return extract_pdf(body)
    if ext == ".pptx":
        return extract_pptx(body)
    if ext == ".docx":
        return extract_docx(body)
    if ext in {".html", ".htm"} or "html" in content_type:
        return _paginate(html_to_text(body.decode("utf-8", "replace")))
    if ext in {".txt", ".md", ".markdown", ".csv", ".rtf"} or content_type.startswith("text/"):
        return _paginate(body.decode("utf-8", "replace"))
    reason = unsupported_reason(name, content_type) or "unsupported file type"
    return Extraction(status="skipped", note=reason)


def extract_pdf(body: bytes) -> Extraction:
    """Extract text from a PDF page by page, dropping headers and footers.

    Lines that repeat on at least half the pages are almost always running headers or
    slide footers; keeping them buries the real content and wastes the byte budget.
    A deck where four fifths of pages have no text is a scan, and we say so rather than
    returning a convincing-looking empty document.
    """
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError:  # pragma: no cover - pypdf is a hard dependency
        return Extraction(status="failed", note="pypdf is not installed")

    started = time.monotonic()
    try:
        reader = PdfReader(io.BytesIO(body))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                return Extraction(status="skipped", note="the PDF is password protected")
        raw_pages: list[str] = []
        empty = 0
        for number, page in enumerate(reader.pages):
            if number >= MAX_PAGES or time.monotonic() - started > MAX_SECONDS:
                return _finish_pdf(raw_pages, empty, truncated=True)
            try:
                text = (page.extract_text() or "").strip()
            except Exception:
                text = ""
            if not text:
                empty += 1
            raw_pages.append(text)
    except PdfReadError as exc:
        logger.debug("PDF could not be parsed: %s", exc)
        return Extraction(status="failed", note="the PDF could not be read")
    except Exception:
        logger.debug("PDF extraction failed", exc_info=True)
        return Extraction(status="failed", note="the PDF could not be read")

    return _finish_pdf(raw_pages, empty, truncated=False)


def _finish_pdf(raw_pages: list[str], empty: int, *, truncated: bool) -> Extraction:
    """Strip repeated boilerplate, cap the total size, and label scanned documents."""
    total = len(raw_pages)
    if total and empty >= 0.8 * total:
        return Extraction(
            page_count=total,
            status="skipped",
            note="scanned document, no text layer — open it in bCourses",
        )

    repeated = _repeated_lines(raw_pages)
    cleaned: list[str] = []
    chars = 0
    for text in raw_pages:
        kept = "\n".join(line for line in text.splitlines() if line.strip() and line.strip() not in repeated)
        if chars + len(kept) > MAX_CHARS:
            cleaned.append(kept[: max(0, MAX_CHARS - chars)])
            truncated = True
            break
        chars += len(kept)
        cleaned.append(kept)

    return Extraction(
        pages=cleaned,
        page_count=total,
        char_count=sum(len(page) for page in cleaned),
        truncated=truncated,
        status="indexed" if any(cleaned) else "skipped",
        note=None if any(cleaned) else "no extractable text",
    )


def _repeated_lines(pages: list[str], threshold: float = 0.5) -> set[str]:
    """Return short lines that appear on at least *threshold* of the pages."""
    if len(pages) < 4:
        return set()
    seen: dict[str, int] = {}
    for text in pages:
        for line in {line.strip() for line in text.splitlines() if 0 < len(line.strip()) <= 120}:
            seen[line] = seen.get(line, 0) + 1
    cutoff = max(2, int(threshold * len(pages)))
    return {line for line, count in seen.items() if count >= cutoff}


_PPTX_NS: Final[str] = "{http://schemas.openxmlformats.org/drawingml/2006/main}t"
_DOCX_NS: Final[str] = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def extract_pptx(body: bytes) -> Extraction:
    """Extract slide text from a .pptx, one page per slide."""
    names: list[str] = []
    pages: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            names = sorted(
                (n for n in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[-1]).group(1)),
            )
            for name in names[:MAX_PAGES]:
                try:
                    root = ElementTree.fromstring(archive.read(name))
                except ElementTree.ParseError:
                    continue
                lines = [(node.text or "").strip() for node in root.iter(_PPTX_NS)]
                pages.append("\n".join(line for line in lines if line))
    except (zipfile.BadZipFile, KeyError, OSError):
        return Extraction(status="failed", note="the slide deck could not be read")

    if not any(pages):
        return Extraction(page_count=len(pages), status="skipped", note="the slides contain no text")
    return Extraction(
        pages=pages,
        page_count=len(pages),
        char_count=sum(len(page) for page in pages),
        truncated=len(names) > MAX_PAGES,
    )


def extract_docx(body: bytes) -> Extraction:
    """Extract paragraph text from a .docx."""
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, OSError, ElementTree.ParseError):
        return Extraction(status="failed", note="the document could not be read")

    paragraphs: list[str] = []
    for para in root.iter(f"{_DOCX_NS}p"):
        text = "".join(node.text or "" for node in para.iter(f"{_DOCX_NS}t")).strip()
        if text:
            paragraphs.append(text)
    if not paragraphs:
        return Extraction(status="skipped", note="the document contains no text")
    return _paginate("\n\n".join(paragraphs))


class _TextExtractor(HTMLParser):
    """Collect visible text from HTML, remembering the heading each block sits under."""

    _SKIP: Final[frozenset[str]] = frozenset({"script", "style", "noscript", "head"})
    _BLOCK: Final[frozenset[str]] = frozenset(
        {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "blockquote", "pre"}
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.headings: list[tuple[int, str]] = []
        self._skip_depth = 0
        self._heading_level: int | None = None
        self._heading_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._heading_level = int(tag[1])
            self._heading_buffer = []
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and self._heading_level is not None:
            heading = " ".join("".join(self._heading_buffer).split())
            if heading:
                self.headings.append((self._heading_level, heading))
                self.parts.append(f"\n\n## {heading}\n")
            self._heading_level = None
            self._heading_buffer = []
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._heading_level is not None:
            self._heading_buffer.append(data)
            return
        self.parts.append(data)


def html_to_text(html: str) -> str:
    """Flatten HTML to text, keeping headings as Markdown so citations can name them."""
    parser = _TextExtractor()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        logger.debug("HTML parsing failed; falling back to tag stripping", exc_info=True)
        return re.sub(r"<[^>]+>", " ", html or "")
    text = "".join(parser.parts)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def _paginate(text: str) -> Extraction:
    """Wrap a flat string as a single-page extraction, honouring the character cap."""
    truncated = len(text) > MAX_CHARS
    body = text[:MAX_CHARS]
    if not body.strip():
        return Extraction(status="skipped", note="no text content")
    return Extraction(pages=[body], page_count=1, char_count=len(body), truncated=truncated)


# -- chunking -----------------------------------------------------------------


@dataclass
class Chunk:
    """A citable slice of a document."""

    ord: int
    text: str
    page_start: int
    page_end: int
    heading: str | None = None


def chunk_pages(pages: list[str], *, slides: bool = False) -> list[Chunk]:
    """Split extracted pages into citable chunks that never straddle a page.

    A chunk that spans pages cannot be cited honestly, so page boundaries are hard.
    Slide decks are the exception in the other direction: single slides are too small to
    retrieve on, so consecutive slides accumulate until the chunk is worth returning.
    """
    chunks: list[Chunk] = []
    order = 0

    if slides:
        buffer: list[str] = []
        start_page = 1
        for number, text in enumerate(pages, start=1):
            cleaned = text.strip()
            if not cleaned:
                continue
            if not buffer:
                start_page = number
            buffer.append(cleaned)
            if sum(len(part) for part in buffer) >= SLIDE_MIN:
                chunks.append(Chunk(ord=order, text="\n\n".join(buffer), page_start=start_page, page_end=number))
                order += 1
                buffer = []
        if buffer:
            chunks.append(
                Chunk(ord=order, text="\n\n".join(buffer), page_start=start_page, page_end=len(pages))
            )
        return chunks

    for number, text in enumerate(pages, start=1):
        for piece, heading in _split_page(text):
            chunks.append(Chunk(ord=order, text=piece, page_start=number, page_end=number, heading=heading))
            order += 1
    return chunks


def _split_page(text: str) -> list[tuple[str, str | None]]:
    """Split one page into chunks at paragraph and heading boundaries."""
    cleaned = text.strip()
    if not cleaned:
        return []

    blocks = [block.strip() for block in re.split(r"\n\s*\n", cleaned) if block.strip()]
    pieces: list[tuple[str, str | None]] = []
    buffer: list[str] = []
    heading: str | None = None
    current_heading: str | None = None

    def flush() -> None:
        if buffer:
            pieces.append(("\n\n".join(buffer), current_heading))
            buffer.clear()

    for block in blocks:
        match = re.match(r"^#{1,2}\s+(.*)$", block)
        if match:
            flush()
            heading = match.group(1).strip()
            current_heading = heading
            continue
        if len(block) > CHUNK_MAX:
            flush()
            for start in range(0, len(block), CHUNK_TARGET):
                pieces.append((block[start : start + CHUNK_TARGET], current_heading))
            continue
        if sum(len(part) + 2 for part in buffer) + len(block) > CHUNK_TARGET and buffer:
            flush()
        buffer.append(block)

    flush()
    return pieces


def cite(title: str, page_start: int, page_end: int, heading: str | None = None, *, paged: bool = True) -> str:
    """Format the citation the host is told to quote."""
    parts = [title]
    if heading:
        parts.append(heading)
    if paged and page_start:
        parts.append(f"p. {page_start}" if page_start == page_end else f"pp. {page_start}-{page_end}")
    return "(" + ", ".join(parts) + ")"


def truncate(text: str, limit: int, *, offset: int = 0) -> tuple[str, int | None]:
    """Return a slice of text and the cursor for the next slice, if any."""
    if offset >= len(text):
        return "", None
    window = text[offset : offset + limit]
    next_offset = offset + len(window)
    return window, (next_offset if next_offset < len(text) else None)


def summarise_html(html: str, limit: int, offset: int = 0) -> tuple[str, int | None, int]:
    """Flatten HTML and return a windowed slice plus the total length."""
    text = html_to_text(html or "")
    window, cursor = truncate(text, limit, offset=offset)
    return window, cursor, len(text)


def looks_like_pdf(body: bytes) -> bool:
    """Return whether a byte string starts with the PDF magic number."""
    return body[:5] == b"%PDF-"


def file_summary(record: dict[str, Any]) -> dict[str, Any]:
    """Reduce a Canvas file record to the fields the index and tools need."""
    return {
        "canvas_id": str(record.get("id") or ""),
        "title": str(record.get("display_name") or record.get("filename") or "Untitled"),
        "content_type": str(record.get("content-type") or record.get("content_type") or ""),
        "size_bytes": int(record.get("size") or 0),
        "url": str(record.get("url") or ""),
        "html_url": str(record.get("html_url") or ""),
        "source_updated_at": str(record.get("updated_at") or ""),
    }
