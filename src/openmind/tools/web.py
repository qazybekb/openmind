"""Fetch and search web content with SSRF protections."""

from __future__ import annotations

import ipaddress
import json
import logging
import socket
from typing import Any, Final, TypeAlias
from urllib.parse import urlparse

import httpx

from openmind.config import ConfigDict

logger = logging.getLogger(__name__)

ToolArgs: TypeAlias = dict[str, Any]
ToolDefinition: TypeAlias = dict[str, Any]

BLOCKED_HOSTS: Final[set[str]] = {"0.0.0.0", "127.0.0.1", "::1", "localhost"}
FETCH_TIMEOUT_S: Final[float] = 30.0
MAX_FETCH_CHARS: Final[int] = 50_000
MAX_SEARCH_CHARS: Final[int] = 30_000
SEARCH_TIMEOUT_S: Final[float] = 15.0
USER_AGENT: Final[str] = "Mozilla/5.0 (compatible; openmind/0.1)"


def _json_result(payload: Any) -> str:
    """Serialize a web tool payload as JSON."""
    return json.dumps(payload, default=str)


def _error_result(message: str) -> str:
    """Serialize a web tool error as JSON."""
    return _json_result({"error": message})


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return whether an IP address should be blocked for SSRF safety."""
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _is_safe_url(url: str) -> str | None:
    """Validate a URL for SSRF safety and return an error message when unsafe."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        return f"Blocked scheme: {parsed.scheme}. Only http/https allowed."

    if not parsed.hostname:
        return "Blocked: URL must include a hostname."

    host = parsed.hostname.rstrip(".").lower()
    if host in BLOCKED_HOSTS:
        return "Blocked: localhost and loopback URLs are not allowed."

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        try:
            resolved = socket.getaddrinfo(host, parsed.port or (443 if scheme == "https" else 80), type=socket.SOCK_STREAM)
        except socket.gaierror:
            return "Blocked: could not resolve hostname."

        if not resolved:
            return "Blocked: hostname did not resolve to any address."

        for result in resolved:
            resolved_host = result[4][0]
            resolved_ip = ipaddress.ip_address(resolved_host)
            if _is_blocked_ip(resolved_ip):
                return "Blocked: hostname resolves to a private or local IP address."
        return None

    if _is_blocked_ip(ip):
        return "Blocked: private or local IP addresses are not allowed."
    return None


MAX_REDIRECTS: Final[int] = 5


def _safe_get(url: str, timeout: float = FETCH_TIMEOUT_S) -> httpx.Response:
    """GET with redirect validation — re-checks SSRF safety on each hop."""
    current_url = url
    for _ in range(MAX_REDIRECTS):
        resp = httpx.get(
            current_url,
            timeout=timeout,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT},
        )
        if resp.status_code not in (301, 302, 303, 307, 308):
            return resp
        location = resp.headers.get("location", "")
        if not location:
            return resp
        # Resolve relative redirects
        if not location.startswith("http"):
            from urllib.parse import urljoin
            location = urljoin(current_url, location)
        # Validate the redirect target
        err = _is_safe_url(location)
        if err:
            raise httpx.HTTPStatusError(
                f"Redirect blocked: {err}",
                request=resp.request,
                response=resp,
            )
        current_url = location
    raise httpx.TooManyRedirects(f"Too many redirects from {url}")


WEB_TOOLS: list[ToolDefinition] = [
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch the content of a web page URL and return its text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web using DuckDuckGo and return results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
        },
    },
]


def execute_web_tool(name: str, args: ToolArgs, cfg: ConfigDict) -> str:
    """Execute a web tool and return a JSON string."""
    del cfg

    if name == "web_fetch":
        url = str(args.get("url", "")).strip()
        if not url:
            return _error_result("Missing required argument: url.")

        safety_error = _is_safe_url(url)
        if safety_error:
            return _error_result(safety_error)

        try:
            response = _safe_get(url, timeout=FETCH_TIMEOUT_S)
            response.raise_for_status()
            if "pdf" in response.headers.get("content-type", "").lower():
                return _error_result("This is a PDF. Use the read_pdf tool instead.")

            text = response.text
            if len(text) > MAX_FETCH_CHARS:
                text = text[:MAX_FETCH_CHARS] + "\n\n[Content truncated]"
            return _json_result({"content": text})
        except httpx.HTTPError:
            logger.warning("Web fetch failed for %s", urlparse(url).hostname or "unknown", exc_info=True)
            return _error_result("Failed to fetch the URL.")

    if name == "web_search":
        query = str(args.get("query", "")).strip()
        if not query:
            return _error_result("Missing required argument: query.")

        try:
            response = httpx.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": USER_AGENT},
                timeout=SEARCH_TIMEOUT_S,
                follow_redirects=True,
            )
            response.raise_for_status()
            text = response.text
            if len(text) > MAX_SEARCH_CHARS:
                text = text[:MAX_SEARCH_CHARS]
            return _json_result({"content": text})
        except httpx.HTTPError:
            logger.warning("Web search failed for query %r", query, exc_info=True)
            return _error_result("Search failed.")

    return _error_result(f"Unknown web tool: {name}")
