#!/usr/bin/env python3
"""
QA Check for bCourses Bot
Run after chatting with the bot to analyze response quality.
Usage: python3 qa_check.py [session_file]
"""

import glob
import json
import os
import sys

DEFAULT_SESSION_DIR = os.path.expanduser("~/.nanobot-canvas/workspace/sessions")

BANNED_PHRASES = [
    "of course", "one moment", "one sec", "let me check",
    "certainly", "absolutely", "i'd be happy to", "i would be happy",
    "here's what i found", "based on my analysis", "let me help you",
    "i can assist", "would you like me to"
]


def find_session_file(session_dir):
    pattern = os.path.join(session_dir, "telegram_*.jsonl")
    files = glob.glob(pattern)
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def load_messages(filepath):
    messages = []
    with open(filepath) as f:
        for line in f:
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return messages


def get_text(m):
    content = m.get("content", "")
    if isinstance(content, list):
        return " ".join(c.get("text", "") for c in content)
    return content


def check_banned_phrases(messages):
    issues = []
    for i, m in enumerate(messages):
        if m.get("role") != "assistant":
            continue
        content_lower = get_text(m).lower()
        for phrase in BANNED_PHRASES:
            if phrase in content_lower:
                issues.append(f"  \u274c Message {i}: Used '{phrase}' \u2014 \"{get_text(m)[:100]}...\"")
    return issues


def check_download_links(messages):
    issues = []
    for i, m in enumerate(messages):
        if m.get("role") != "assistant":
            continue
        content = get_text(m)
        if "bcourses.berkeley.edu/files/" in content and "/download" in content:
            if "access_token=" not in content:
                issues.append(f"  \u274c Message {i}: Download link missing access_token \u2014 \"{content[:150]}...\"")
    return issues


def check_verbosity(messages):
    issues = []
    assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
    filler_starters = [
        "let me ", "i'll ", "checking ", "pulling up", "fetching",
        "got it.", "alright,", "okay,", "sure,", "great question"
    ]
    for i, m in enumerate(assistant_msgs):
        content = get_text(m)
        content_lower = content.lower().strip()
        if len(content) < 100 and any(content_lower.startswith(f) for f in filler_starters):
            issues.append(f"  \u26a0\ufe0f Message {i}: Filler response \u2014 \"{content[:100]}\"")
    return issues


def check_response_stats(messages):
    user_msgs = [m for m in messages if m.get("role") == "user"]
    assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
    tool_calls = [m for m in messages if m.get("role") == "tool"]
    total_len = sum(len(get_text(m)) for m in assistant_msgs)
    return {
        "user_messages": len(user_msgs),
        "bot_responses": len(assistant_msgs),
        "tool_calls": len(tool_calls),
        "avg_response_length": total_len // max(len(assistant_msgs), 1)
    }


def check_cache_usage(messages):
    issues = []
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    cache_reads = 0
    api_calls = 0
    for m in tool_msgs:
        content = str(m.get("content", ""))
        if "course_cache" in content:
            cache_reads += 1
        if "bcourses.berkeley.edu/api" in content:
            api_calls += 1
    if api_calls > 0 and cache_reads == 0:
        issues.append(f"  \u26a0\ufe0f Made {api_calls} API calls but never read cache")
    return issues, cache_reads, api_calls


def main():
    if len(sys.argv) > 1:
        session_file = sys.argv[1]
    else:
        session_file = find_session_file(DEFAULT_SESSION_DIR)

    if not session_file or not os.path.exists(session_file):
        print("No session file found.")
        print(f"Usage: python3 qa_check.py [session_file]")
        print(f"Default search: {DEFAULT_SESSION_DIR}/telegram_*.jsonl")
        sys.exit(1)

    print(f"\U0001f43b bCourses Bot QA Report")
    print(f"Session: {session_file}")
    print("=" * 50)

    messages = load_messages(session_file)
    stats = check_response_stats(messages)

    print(f"\n\U0001f4ca Stats:")
    print(f"  User messages: {stats['user_messages']}")
    print(f"  Bot responses: {stats['bot_responses']}")
    print(f"  Tool calls: {stats['tool_calls']}")
    print(f"  Avg response length: {stats['avg_response_length']} chars")

    all_issues = []

    print(f"\n\U0001f50d Banned Phrases Check:")
    issues = check_banned_phrases(messages)
    all_issues.extend(issues)
    for i in issues:
        print(i)
    if not issues:
        print("  \u2705 No banned phrases found")

    print(f"\n\U0001f517 Download Links Check:")
    issues = check_download_links(messages)
    all_issues.extend(issues)
    for i in issues:
        print(i)
    if not issues:
        print("  \u2705 All download links have access_token")

    print(f"\n\U0001f4ac Verbosity Check:")
    issues = check_verbosity(messages)
    all_issues.extend(issues)
    for i in issues:
        print(i)
    if not issues:
        print("  \u2705 No unnecessary filler responses")

    print(f"\n\U0001f4e6 Cache Usage:")
    issues, cache_reads, api_calls = check_cache_usage(messages)
    all_issues.extend(issues)
    print(f"  Cache reads: {cache_reads}")
    print(f"  API calls: {api_calls}")
    for i in issues:
        print(i)
    if not issues:
        print("  \u2705 Cache usage looks good")

    print(f"\n{'=' * 50}")
    if not all_issues:
        print("\U0001f389 All checks passed! Go Bears!")
    else:
        print(f"\u26a0\ufe0f {len(all_issues)} issues found \u2014 review above")


if __name__ == "__main__":
    main()
