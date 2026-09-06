"""Private document parser subprocess. Input and output use memory-only pipes."""

from __future__ import annotations

import json
import sys
from contextlib import suppress
from dataclasses import asdict

from openmind import materials

MEMORY_LIMIT = 768 * 1024 * 1024


def restrict_resources() -> None:
    """Disable core dumps and cap address space where POSIX supports it."""
    try:
        import resource
    except ImportError:  # Windows has no resource module; the parent enforces time.
        return
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if hasattr(resource, "RLIMIT_AS"):
        _, hard = resource.getrlimit(resource.RLIMIT_AS)
        limit = min(MEMORY_LIMIT, hard) if hard != resource.RLIM_INFINITY else MEMORY_LIMIT
        # Some macOS runtimes do not support RLIMIT_AS.
        with suppress(OSError, ValueError):
            resource.setrlimit(resource.RLIMIT_AS, (limit, hard))


def main() -> int:
    parsers = {"pdf": materials._extract_pdf, "pptx": materials._extract_pptx, "docx": materials._extract_docx}
    if len(sys.argv) != 5 or sys.argv[1] not in parsers:
        return 2
    restrict_resources()
    materials.MAX_PAGES, materials.MAX_CHARS, materials.MAX_MEMBER_BYTES = (
        max(1, min(int(value), maximum)) for value, maximum in zip(
            sys.argv[2:], (materials.MAX_PAGES, materials.MAX_CHARS, materials.MAX_MEMBER_BYTES), strict=True
        )
    )
    body = sys.stdin.buffer.read(materials.MAX_DOWNLOAD_BYTES + 1)
    if len(body) > materials.MAX_DOWNLOAD_BYTES:
        return 2
    result = parsers[sys.argv[1]](body)
    sys.stdout.buffer.write(json.dumps(asdict(result), separators=(",", ":")).encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
