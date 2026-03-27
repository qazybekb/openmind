"""Read Gmail data through optional read-only tools."""

from __future__ import annotations

import base64
import json
import logging
import os
import stat
import sys
from typing import Any, Final, TypeAlias

from openmind.config import ConfigDict, GMAIL_CREDS_DIR

logger = logging.getLogger(__name__)

ToolArgs: TypeAlias = dict[str, Any]
ToolDefinition: TypeAlias = dict[str, Any]

DEFAULT_MAX_RESULTS: Final[int] = 10
MAX_RESULTS_LIMIT: Final[int] = 25
SCOPES: Final[list[str]] = ["https://www.googleapis.com/auth/gmail.readonly"]

GMAIL_TOOLS: list[ToolDefinition] = [
    {
        "type": "function",
        "function": {
            "name": "gmail_search",
            "description": "Search Gmail for emails matching a query (e.g. 'from:professor@berkeley.edu', 'subject:midterm', 'is:unread').",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Gmail search query"},
                    "max_results": {"type": "integer", "description": "Max emails to return (default 10)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_read",
            "description": "Read the full content of a specific email by its message ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {"type": "string", "description": "Gmail message ID"},
                },
                "required": ["message_id"],
            },
        },
    },
]

NOT_READY_MESSAGE: Final[str] = (
    "Gmail is not connected yet. To set it up: "
    "(1) run: openmind setup gmail and provide your Google OAuth credentials "
    "(from Google Cloud Console > Gmail API > OAuth 2.0 Client ID, Desktop app), "
    "(2) on first use a browser window will open for Google sign-in. "
    "Detailed guide: openmindbot.io/guides/gmail"
)


def _ensure_private_google_dir() -> None:
    """Create the shared Google credentials directory with owner-only permissions."""
    GMAIL_CREDS_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(GMAIL_CREDS_DIR, stat.S_IRWXU)


def _restrict_file(path: Any) -> None:
    """Restrict a credential or token file to owner read/write."""
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def _json_result(payload: Any) -> str:
    """Serialize a Gmail tool payload as JSON."""
    return json.dumps(payload, default=str)


def _error_result(message: str) -> str:
    """Serialize a Gmail tool error as JSON."""
    return _json_result({"error": message})


def _coerce_max_results(value: Any) -> int:
    """Return a bounded Gmail search result count."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_RESULTS
    return max(1, min(parsed, MAX_RESULTS_LIMIT))


def _headers_map(headers: Any) -> dict[str, str]:
    """Return a mapping of Gmail headers by name."""
    if not isinstance(headers, list):
        return {}

    result: dict[str, str] = {}
    for header in headers:
        if not isinstance(header, dict):
            continue
        name = str(header.get("name", ""))
        value = str(header.get("value", ""))
        if name:
            result[name] = value
    return result


def _decode_body(data: str) -> str:
    """Decode a Gmail body fragment."""
    if not data:
        return ""

    try:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    except (ValueError, TypeError):
        return ""


def _extract_body(payload: dict[str, Any]) -> str:
    """Extract message text from a Gmail payload."""
    mime_type = str(payload.get("mimeType", ""))
    if mime_type in {"text/plain", "text/html"}:
        body = payload.get("body", {})
        if isinstance(body, dict):
            text = _decode_body(str(body.get("data", "")))
            if text:
                return text

    parts = payload.get("parts", [])
    if not isinstance(parts, list):
        return ""

    for part in parts:
        if not isinstance(part, dict):
            continue
        text = _extract_body(part)
        if text:
            return text
    return ""


def _get_gmail_service(cfg: ConfigDict) -> Any | None:
    """Build a Gmail API service when Gmail is configured and available."""
    if not cfg.get("gmail", {}).get("enabled"):
        return None

    credentials_file = GMAIL_CREDS_DIR / "credentials.json"
    token_file = GMAIL_CREDS_DIR / "token.json"
    if not credentials_file.exists():
        return None

    try:
        # Import lazily because Gmail support is an optional dependency group.
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        return None

    try:
        credentials: Any | None = None
        if token_file.exists():
            credentials = Credentials.from_authorized_user_file(str(token_file), SCOPES)

        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            elif token_file.exists():
                return None
            else:
                if not sys.stdin.isatty():
                    return None
                flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), SCOPES)
                credentials = flow.run_local_server(port=0)

            _ensure_private_google_dir()
            token_file.write_text(credentials.to_json(), encoding="utf-8")
            _restrict_file(token_file)

        return build("gmail", "v1", credentials=credentials)
    except Exception:
        logger.warning("Failed to initialize Gmail service", exc_info=True)
        return None


def execute_gmail_tool(name: str, args: ToolArgs, cfg: ConfigDict) -> str:
    """Execute a Gmail tool and return a JSON string."""
    service = _get_gmail_service(cfg)
    if service is None:
        return _error_result(NOT_READY_MESSAGE)

    try:
        return _execute_gmail_tool(name, args, service)
    except Exception:
        logger.exception("Gmail tool '%s' failed unexpectedly", name)
        return _error_result("Gmail tool failed unexpectedly.")


def _execute_gmail_tool(name: str, args: ToolArgs, service: Any) -> str:
    """Dispatch a Gmail tool after validating its arguments."""
    if name == "gmail_search":
        query = str(args.get("query", "")).strip()
        if not query:
            return _error_result("Missing required argument: query.")

        max_results = _coerce_max_results(args.get("max_results", DEFAULT_MAX_RESULTS))
        results = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
        messages = results.get("messages", []) if isinstance(results, dict) else []

        summaries: list[dict[str, str]] = []
        for message in messages:
            if not isinstance(message, dict):
                continue

            message_id = str(message.get("id", "")).strip()
            if not message_id:
                continue

            detail = service.users().messages().get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            payload = detail.get("payload", {}) if isinstance(detail, dict) else {}
            headers = _headers_map(payload.get("headers", []) if isinstance(payload, dict) else [])
            summaries.append(
                {
                    "id": message_id,
                    "from": headers.get("From", ""),
                    "subject": headers.get("Subject", ""),
                    "date": headers.get("Date", ""),
                    "snippet": str(detail.get("snippet", "")) if isinstance(detail, dict) else "",
                }
            )

        return _json_result({"messages": summaries, "count": len(summaries)})

    if name == "gmail_read":
        message_id = str(args.get("message_id", "")).strip()
        if not message_id:
            return _error_result("Missing required argument: message_id.")

        message = service.users().messages().get(userId="me", id=message_id, format="full").execute()
        payload = message.get("payload", {}) if isinstance(message, dict) else {}
        payload_dict = payload if isinstance(payload, dict) else {}
        headers = _headers_map(payload_dict.get("headers", []))
        return _json_result(
            {
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
                "body": _extract_body(payload_dict),
            }
        )

    return _error_result(f"Unknown gmail tool: {name}")
