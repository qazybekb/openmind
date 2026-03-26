"""Download PDFs safely and extract their text for tool calls."""

from __future__ import annotations

import json
import logging
import tempfile
from typing import Any, Final, TypeAlias

import fitz
import httpx

from openmind.config import ConfigDict
from openmind.tools.web import _is_safe_url, _safe_get

logger = logging.getLogger(__name__)

ToolArgs: TypeAlias = dict[str, Any]
ToolDefinition: TypeAlias = dict[str, Any]

PDF_DOWNLOAD_TIMEOUT_S: Final[float] = 60.0

PDF_TOOLS: list[ToolDefinition] = [
    {
        "type": "function",
        "function": {
            "name": "read_pdf",
            "description": "Download a PDF from a URL and extract all text from every page. Use for Canvas lecture slides, readings, and papers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Direct URL to the PDF file"},
                },
                "required": ["url"],
            },
        },
    },
]


def _json_result(payload: Any) -> str:
    """Serialize a PDF tool payload as JSON."""
    return json.dumps(payload, default=str)


def _error_result(message: str) -> str:
    """Serialize a PDF tool error as JSON."""
    return _json_result({"error": message})


def execute_pdf_tool(name: str, args: ToolArgs, cfg: ConfigDict) -> str:
    """Execute a PDF tool and return a JSON string."""
    del cfg

    if name != "read_pdf":
        return _error_result(f"Unknown pdf tool: {name}")

    url = str(args.get("url", "")).strip()
    if not url:
        return _error_result("Missing required argument: url.")

    safety_error = _is_safe_url(url)
    if safety_error:
        return _error_result(safety_error)

    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp_file:
            # Validate redirects for SSRF safety, then stream
            resolved_resp = _safe_get(url, timeout=PDF_DOWNLOAD_TIMEOUT_S)
            resolved_url = str(resolved_resp.url) if resolved_resp.is_redirect else url
            with httpx.stream("GET", resolved_url, timeout=PDF_DOWNLOAD_TIMEOUT_S, follow_redirects=False) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if "pdf" not in content_type and not url.lower().endswith(".pdf"):
                    return _error_result("URL did not return a PDF document.")

                for chunk in response.iter_bytes():
                    tmp_file.write(chunk)
                tmp_file.flush()

            document = fitz.open(tmp_file.name)
            try:
                pages: list[str] = []
                for index, page in enumerate(document):
                    text = page.get_text().strip()
                    if text:
                        pages.append(f"--- Page {index + 1} ---\n{text}")
            finally:
                document.close()

        if not pages:
            return _json_result({"content": "PDF contained no extractable text."})
        return _json_result({"content": "\n\n".join(pages)})
    except httpx.HTTPError as exc:
        logger.warning("Failed to download PDF: %s", type(exc).__name__)
        return _error_result("Failed to download the PDF.")
    except Exception:
        logger.exception("Failed to read PDF")
        return _error_result("Failed to read the PDF.")
