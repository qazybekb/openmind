"""Set up and inspect OpenMind from a terminal.

Everything interactive lives here rather than in the server: `openmind-mcp` speaks the
protocol on stdout and must never print a prompt or a banner, so setup, diagnosis, and
deletion are separate commands the student runs themselves.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import shutil
import sys
from getpass import getpass
from pathlib import Path
from typing import Any, Final

from openmind import __version__, catalog, hosts, index, secrets
from openmind.canvas import CanvasClient, CanvasError
from openmind.config import CANVAS_URL, Config, ConfigError, config_path, home_dir, load_config

logger = logging.getLogger(__name__)

MIN_PYTHON: Final[tuple[int, int]] = (3, 11)
MAX_NICKNAME_LENGTH: Final[int] = 40
TOKEN_HELP: Final[str] = (
    "Create one in bCourses: Account -> Settings -> Approved Integrations -> + New Access Token."
)


def _use_utf8() -> None:
    """Make the console tolerate the characters this CLI actually prints.

    A legacy Windows console defaults to cp1252 and raises on an em dash, which would
    turn a helpful setup message into a traceback. Reconfiguring to UTF-8 with a
    replacing error handler means the worst case is a substituted character, never a
    crash mid-setup.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            # A detached or already-closed stream is not worth failing setup over.
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8", errors="replace")


def out(message: str = "") -> None:
    """Print a line to stdout for a human reading a terminal."""
    print(message)


def err(message: str) -> None:
    """Print a line to stderr."""
    print(message, file=sys.stderr)


# -- setup ---------------------------------------------------------------------


def cmd_setup(args: argparse.Namespace) -> int:
    """Store a bCourses token, choose courses, and build the catalog."""
    out("OpenMind — bCourses for UC Berkeley")
    out(f"Config will be written to {config_path()}")
    out("")

    token = os.environ.get(secrets.ENV_VAR, "").strip()
    if token:
        out(f"Using the token from ${secrets.ENV_VAR}.")
    else:
        out(f"Paste your bCourses access token. {TOKEN_HELP}")
        out("It is stored in your operating system's credential store, not in a file.")
        token = getpass("bCourses token: ").strip()
    if not token:
        err("No token entered. Nothing was changed.")
        return 1

    out(f"Token: {secrets.mask(token)}")
    out("Connecting to bCourses...")
    try:
        client = CanvasClient(CANVAS_URL, token)
        profile = client.profile()
    except CanvasError as exc:
        err(f"Failed: {exc}")
        return 1

    name = str(profile.get("name") or "student")
    time_zone = str(profile.get("time_zone") or "America/Los_Angeles")
    out(f"Connected as {name} ({time_zone}).")
    out("")

    try:
        courses = client.courses()
    except CanvasError as exc:
        err(f"Could not list your courses: {exc}")
        client.close()
        return 1

    active = [
        (str(course.get("id")), _nickname(str(course.get("name") or ""), str(course.get("course_code") or "")))
        for course in courses
        if course.get("id")
    ]
    if not active:
        err("bCourses reports no active courses for this token.")
        client.close()
        return 1

    out("Your active courses:")
    for position, (course_id, nickname) in enumerate(active, start=1):
        out(f"  {position:2d}. {nickname}  (id {course_id})")
    out("")
    out("OpenMind shares only the courses you choose here with your AI app.")
    chosen = _select(active, args.all_courses)
    if not chosen:
        err("No courses selected. Nothing was changed.")
        client.close()
        return 1

    cfg = Config(
        {
            "canvas_url": CANVAS_URL,
            "time_zone": time_zone,
            "user_name": name,
            "courses": dict(chosen),
            "index_enabled": [],
            "capacity_hours_per_day": 2.0,
            "data_updates": True,
            "allow_file_secrets": bool(args.allow_file_secrets),
        }
    )

    try:
        backend = secrets.set_token(token, allow_file=args.allow_file_secrets)
    except secrets.SecretError as exc:
        err(str(exc))
        client.close()
        return 1
    if backend == "file":
        err(f"WARNING: the token was written to {home_dir() / 'token'} (mode 0600), not a credential store.")
    cfg.save()
    out(f"Saved {len(chosen)} course(s) to {config_path()}.")
    out("")

    out("Building the Berkeley course catalog index (public data, no login)...")
    try:
        counts = catalog.build()
        out(f"  {counts['courses']} courses across {counts['subjects']} subjects.")
    except Exception as exc:
        err(f"  Could not build the catalog: {exc}. Run `openmind update-data` later.")
    out("")

    if args.index:
        _index_courses(cfg, client, [cid for cid, _ in chosen])
    else:
        out("Course materials are NOT stored locally unless you ask for it.")
        out("To search inside slides and readings for a course, run:")
        out("  openmind index --course <id>")
    out("")

    client.close()
    _print_host_config()
    return 0


def _nickname(name: str, code: str) -> str:
    """Shorten a Canvas course name into something a student would say out loud."""
    nickname = name.split(" - ")[-1].strip() if " - " in name else name.strip()
    nickname = nickname or code or "Course"
    if len(nickname) > MAX_NICKNAME_LENGTH:
        nickname = nickname[:MAX_NICKNAME_LENGTH].rsplit(" ", 1)[0]
    return nickname


def _select(active: list[tuple[str, str]], take_all: bool) -> list[tuple[str, str]]:
    """Ask which courses to share, defaulting to all of them."""
    if take_all or not sys.stdin.isatty():
        return active
    answer = input("Numbers to share, comma separated, or Enter for all: ").strip()
    if not answer:
        return active
    chosen: list[tuple[str, str]] = []
    for part in answer.replace(" ", "").split(","):
        if part.isdigit() and 1 <= int(part) <= len(active):
            chosen.append(active[int(part) - 1])
    return chosen


def _index_courses(cfg: Config, client: CanvasClient, course_ids: list[str]) -> None:
    """Build a materials index for some courses, reporting progress."""
    from openmind.service import Session

    out("Indexing course materials. Text is extracted into a private file on this machine:")
    out(f"  {home_dir() / 'index.db'}")
    session = Session(cfg, client)
    for course_id in course_ids:
        out(f"  {cfg.nickname(course_id)}...")
        for _ in range(20):
            try:
                result = session.index_course(course_id)
            except Exception as exc:
                err(f"    failed: {exc}")
                break
            out(f"    {result['indexed']} indexed, {result['pending']} pending, {result['skipped']} skipped")
            if not result["pending"]:
                break


# -- host config ---------------------------------------------------------------


def _server_path() -> str:
    """Return the command that launches the MCP server, as a shell would spell it."""
    return hosts.command_line()


def _print_host_config() -> None:
    """Print copy-paste config for each supported AI host. No secrets appear here."""
    snippet = json.dumps({"mcpServers": {hosts.ENTRY_NAME: hosts.entry()}}, indent=2)
    command = hosts.command_line()

    out("Connect OpenMind to your AI app")
    out("=" * 32)
    out("")
    out("Claude Desktop — add this to claude_desktop_config.json, then restart Claude:")
    out(f"  {hosts.claude_desktop_path()}")
    out("")
    out(snippet)
    out("")
    out("Claude Code — run:")
    out(f"  claude mcp add --scope user {hosts.ENTRY_NAME} -- {command}")
    out("")
    out(f"Cursor — add the same JSON block to {hosts.cursor_path()}")
    out("")
    out("ChatGPT desktop — add a local (STDIO) MCP server with this command:")
    out(f"  {command}")
    out("")
    out("Or let OpenMind write it for you:")
    out("  openmind mcp --write claude-desktop")
    out("  openmind mcp --write cursor")
    out("  openmind mcp --write claude-code")
    out("")
    out('Then restart the app and ask: "what\'s due this week?"')


def _confirm(question: str, *, assume_yes: bool) -> bool:
    """Ask a yes/no question, unless the student already said yes on the command line."""
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        err("Refusing to create a file without confirmation. Re-run with --yes.")
        return False
    return input(f"{question} [y/N]: ").strip().lower() in {"y", "yes"}


def _write_host_config(key: str, *, assume_yes: bool) -> int:
    """Merge OpenMind's entry into one host's config file."""
    try:
        host = hosts.find(key)
    except hosts.HostError as exc:
        err(str(exc))
        return 1

    if key == "claude-code":
        return _write_claude_code(assume_yes=assume_yes)
    if not host.writable:
        out(f"{host.label} has no config file to write. Add it in the app:")
        out(f"  {host.note}")
        out(f"  Command: {hosts.command_line()}")
        return 0

    assert host.path is not None
    try:
        before = hosts.read_config(host.path)
    except hosts.HostError as exc:
        err(str(exc))
        return 1

    if not host.path.exists() and not _confirm(f"Create {host.path}?", assume_yes=assume_yes):
        out("Nothing was written.")
        return 1

    try:
        after, change = hosts.merge(host, before)
    except hosts.HostError as exc:
        err(str(exc))
        return 1

    if change == "unchanged":
        out(f"{host.label} already points at this install. Nothing to do.")
        return 0

    if host.path.exists():
        backup = hosts.back_up(host.path)
        out(f"Backed up {host.path.name} to {backup.name}")

    hosts.write_config(host.path, after)
    out(f"{change.capitalize()} the openmind entry in {host.path}")
    for line in hosts.diff(before, after):
        out(f"  {line}")
    out("")
    out(f"Restart {host.label} completely, then ask: what's due this week?")
    return 0


def _write_claude_code(*, assume_yes: bool) -> int:
    """Register the server with Claude Code, which owns its own config."""
    command = ["claude", "mcp", "add", "--scope", "user", hosts.ENTRY_NAME, "--", *hosts.command_line().split(" ")]
    printable = " ".join(command)

    if shutil.which("claude") is None:
        out("The `claude` command is not on your PATH. Once Claude Code is installed, run:")
        out(f"  {printable}")
        return 0
    if not _confirm(f"Run: {printable}?", assume_yes=assume_yes):
        out("Nothing was run. The command above registers OpenMind with Claude Code.")
        return 1

    import subprocess

    result = subprocess.run(command, capture_output=True, text=True)
    for line in (result.stdout or "").splitlines():
        out(line)
    for line in (result.stderr or "").splitlines():
        err(line)
    if result.returncode != 0:
        err(f"`claude mcp add` exited {result.returncode}.")
        return result.returncode
    out("Registered with Claude Code.")
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    """Print host configuration snippets, or write one for the student."""
    if args.write:
        return _write_host_config(args.write, assume_yes=args.yes)
    _print_host_config()
    return 0


# -- doctor --------------------------------------------------------------------


def cmd_doctor(args: argparse.Namespace) -> int:
    """Check every part of the setup and say exactly what is wrong."""
    del args
    problems = 0

    out(f"OpenMind {__version__}")
    out(f"Python {sys.version.split()[0]}  ({sys.executable})")
    if sys.version_info[:2] < MIN_PYTHON:
        err(f"  Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer is required.")
        problems += 1

    out(f"Home: {home_dir()}")
    out(f"Credential store: {secrets.backend_name()}")
    out(f"Server command: {_server_path()}")

    # Reported before the bCourses checks: this half is about the AI app, and it is
    # worth seeing even when setup has not been run yet.
    out("AI app configuration:")
    for host in hosts.hosts():
        report = hosts.status(host)
        if report is None:
            out(f"  {host.label}: configured inside the app, not in a file")
            continue
        out(f"  {report.describe()}")
        if not report.healthy:
            problems += 1

    try:
        cfg = load_config(required=True)
    except ConfigError as exc:
        err(f"Config: {exc}")
        return 1
    out(f"Config: {config_path()} — {len(cfg.courses)} course(s), time zone {cfg.time_zone}")

    token = secrets.get_token()
    if not token:
        err("Token: not stored. Run `openmind setup`.")
        problems += 1
    else:
        out(f"Token: stored ({secrets.mask(token)})")
        try:
            client = CanvasClient(cfg.canvas_url, token)
            profile = client.profile()
            out(f"bCourses: connected as {profile.get('name')} ({profile.get('time_zone')})")
            if str(profile.get("time_zone") or "") != cfg.time_zone:
                out(f"  note: bCourses now reports {profile.get('time_zone')}; run `openmind setup` to update.")
            reachable = 0
            for course_id, nickname in cfg.courses.items():
                try:
                    client.course(course_id, syllabus=False)
                    reachable += 1
                except CanvasError as exc:
                    err(f"  {nickname} ({course_id}): {exc}")
                    problems += 1
            out(f"  {reachable}/{len(cfg.courses)} enabled course(s) reachable")
            client.close()
        except CanvasError as exc:
            err(f"bCourses: {exc}")
            problems += 1

    out(f"FTS5 available: {'yes' if index.fts5_available() else 'no — search will not work'}")
    if not index.fts5_available():
        problems += 1

    db = home_dir() / "index.db"
    if db.exists():
        size_mb = db.stat().st_size / (1024 * 1024)
        try:
            with index.connect(create=False) as conn:
                courses = index.indexed_courses(conn)
                total = sum(index.course_stats(conn, cid).get("indexed", 0) for cid in courses)
            out(f"Materials index: {size_mb:.1f} MB, {len(courses)} course(s), {total} item(s)")
        except Exception as exc:
            err(f"Materials index: unreadable ({exc})")
            problems += 1
    else:
        out("Materials index: none (no course content is stored on this machine)")

    try:
        with catalog.connect() as conn:
            info = catalog.meta(conn)
            count = conn.execute("SELECT COUNT(*) FROM catalog_courses").fetchone()[0]
            offerings = conn.execute("SELECT COUNT(*) FROM term_offerings").fetchone()[0]
        out(f"Catalog: {count} courses, snapshot {info.get('catalog_as_of', 'unknown')}")
        out(f"Offerings: {offerings} course-terms, snapshot {info.get('offerings_as_of', 'none')}")
        terms = json.loads(info.get("terms_known") or "[]")
        out(f"  terms known: {', '.join(terms) or 'none'}")
    except Exception as exc:
        err(f"Catalog: not built ({exc}). Run `openmind update-data`.")
        problems += 1

    out(f"Public data updates: {'on' if cfg.data_updates else 'off'}")


    out("")
    if problems:
        err(f"{problems} problem(s) found.")
        return 1
    out("Everything checks out. Restart your AI app if you changed anything.")
    return 0


# -- index / data / clear / config ---------------------------------------------


def cmd_index(args: argparse.Namespace) -> int:
    """Build or delete a course's local materials index."""
    from openmind.service import Session

    try:
        cfg = load_config(required=True)
    except ConfigError as exc:
        err(str(exc))
        return 1

    token = secrets.get_token()
    if not token:
        err("No bCourses token is stored. Run `openmind setup`.")
        return 1

    course_ids = [args.course] if args.course else list(cfg.courses)
    client = CanvasClient(cfg.canvas_url, token)
    session = Session(cfg, client)
    status = 0
    try:
        for course_id in course_ids:
            try:
                cfg.require_enabled(course_id)
            except ConfigError as exc:
                err(str(exc))
                status = 1
                continue
            if args.delete:
                result = session.index_course(course_id, enable=False)
                out(result["message"])
                continue
            out(f"{cfg.nickname(course_id)}:")
            for _ in range(50):
                result = session.index_course(course_id)
                out(f"  {result['indexed']} indexed, {result['pending']} pending, {result['skipped']} skipped")
                if not result["pending"]:
                    break
    finally:
        client.close()
    return status


def cmd_update_data(args: argparse.Namespace) -> int:
    """Refresh the public catalog snapshot, or rebuild it from the packaged data."""
    cfg = load_config()
    if args.rebuild:
        counts = catalog.build()
        out(f"Rebuilt the catalog from packaged data: {counts['courses']} courses, {counts['offerings']} offerings.")
        return 0

    built = catalog.ensure_built()
    if built is not None:
        out(f"Built the catalog from packaged data: {built['courses']} courses, {built['offerings']} offerings.")

    message = catalog.maybe_update(enabled=cfg.data_updates or args.force, force=True)
    if message:
        out(message)
        return 0
    if not cfg.data_updates and not args.force:
        out("Public data updates are turned off in your config. Use --force to check once anyway.")
        return 0
    if built is None:
        out("The Berkeley catalog is already up to date.")
    return 0


def cmd_clear(args: argparse.Namespace) -> int:
    """Delete everything OpenMind stores on this machine."""
    targets = ["the course materials index"]
    if args.all:
        targets.extend(["the catalog index", "your config", "your stored bCourses token"])
    out("This will delete: " + ", ".join(targets) + ".")
    if not args.yes and sys.stdin.isatty() and input("Type 'yes' to continue: ").strip().lower() != "yes":
        out("Nothing was deleted.")
        return 0

    removed = index.clear_all()
    out("Deleted the course materials index." if removed else "No materials index was present.")

    if args.all:
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(home_dir() / "catalog.db") + suffix)
            if path.exists():
                path.unlink()
        out("Deleted the catalog index.")
        (home_dir() / "data_check").unlink(missing_ok=True)
        config_path().unlink(missing_ok=True)
        out("Deleted your config.")
        secrets.delete_token()
        out("Deleted your stored bCourses token.")
        out("Your bCourses account is untouched. Revoke the token in bCourses if you want it gone there too.")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    """Print or change non-secret settings."""
    try:
        cfg = load_config(required=False)
    except ConfigError as exc:
        err(str(exc))
        return 1

    if args.set:
        key, _, raw = args.set.partition("=")
        key = key.strip()
        if key not in {"capacity_hours_per_day", "data_updates"}:
            err("Only capacity_hours_per_day and data_updates can be set here.")
            return 1
        value: Any = raw.strip()
        if key == "data_updates":
            value = value.lower() in {"1", "true", "yes", "on"}
        else:
            try:
                value = float(value)
            except ValueError:
                err("capacity_hours_per_day must be a number.")
                return 1
        cfg.set(key, value)
        cfg.save()
        out(f"{key} = {value}")
        return 0

    token = secrets.get_token()
    out(f"config file            {config_path()}")
    out(f"canvas_url             {cfg.get('canvas_url', CANVAS_URL)}")
    out(f"time_zone              {cfg.time_zone}")
    out(f"user_name              {cfg.user_name or '(unset)'}")
    out(f"token                  {secrets.mask(token) if token else '(not stored)'} via {secrets.backend_name()}")
    out(f"capacity_hours_per_day {cfg.capacity_hours_per_day}")
    out(f"data_updates           {cfg.data_updates}")
    out(f"courses                {len(cfg.courses)}")
    for course_id, nickname in cfg.courses.items():
        marker = "indexed" if course_id in cfg.indexed_course_ids else "not indexed"
        out(f"  {course_id:<10} {nickname}  [{marker}]")
    return 0


# -- entry point ---------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="openmind",
        description="A local, read-only bCourses MCP server for UC Berkeley students.",
        epilog="Run `openmind setup` first, then `openmind mcp` for your AI app's config.",
    )
    parser.add_argument("--version", action="version", version=f"openmind {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup = subparsers.add_parser("setup", help="store your bCourses token and choose courses")
    setup.add_argument("--all-courses", action="store_true", help="share every active course without asking")
    setup.add_argument("--index", action="store_true", help="index course materials for the chosen courses now")
    setup.add_argument("--allow-file-secrets", action="store_true",
                       help="fall back to a 0600 file if no OS credential store is available")
    setup.set_defaults(func=cmd_setup)

    server = subparsers.add_parser("mcp", help="print config snippets for Claude, Cursor, and ChatGPT")
    server.add_argument("--write", choices=[host.key for host in hosts.hosts()],
                        help="write the entry into that app's config instead of printing it")
    server.add_argument("--yes", action="store_true", help="do not ask before creating a file or running a command")
    server.set_defaults(func=cmd_mcp)

    doctor = subparsers.add_parser("doctor", help="check the setup end to end")
    doctor.set_defaults(func=cmd_doctor)

    idx = subparsers.add_parser("index", help="build a searchable index of a course's materials")
    idx.add_argument("--course", help="course id; omit for every enabled course")
    idx.add_argument("--delete", action="store_true", help="delete the index for that course instead")
    idx.set_defaults(func=cmd_index)

    update = subparsers.add_parser("update-data", help="refresh the public Berkeley catalog snapshot")
    update.add_argument("--force", action="store_true", help="check even when data updates are off")
    update.add_argument("--rebuild", action="store_true", help="rebuild from the data shipped in this package")
    update.set_defaults(func=cmd_update_data)

    clear = subparsers.add_parser("clear", help="delete what OpenMind stores on this machine")
    clear.add_argument("--all", action="store_true", help="also delete the catalog, config, and stored token")
    clear.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    clear.set_defaults(func=cmd_clear)

    config_cmd = subparsers.add_parser("config", help="show or change non-secret settings")
    config_cmd.add_argument("--set", metavar="KEY=VALUE", help="set capacity_hours_per_day or data_updates")
    config_cmd.set_defaults(func=cmd_config)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""
    _use_utf8()
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr, format="%(levelname)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        err("\nCancelled.")
        return 130
    except (ConfigError, CanvasError) as exc:
        err(str(exc))
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
