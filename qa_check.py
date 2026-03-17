#!/usr/bin/env python3
"""
QA Check for bCourses Bot
Run after chatting with the bot to analyze response quality.
Usage: python3 qa_check.py
"""

import json
import sys
from datetime import datetime

SESSION_FILE = "~/.nanobot-canvas/workspace/sessions/telegram_*.jsonl"

BANNED_PHRASES = [
    "of course", "one moment", "one sec", "let me check",
    "certainly", "absolutely", "i'd be happy to", "i would be happy",
    "here's what i found", "based on my analysis", "let me help you",
    "i can assist", "would you like me to"
]

REQUIRED_IN_LINKS = "access_token="

def load_messages():
    messages = []
    with open(SESSION_FILE) as f:
        for line in f:
            try:
                messages.append(json.loads(line))
            except:
                pass
    return messages

def check_banned_phrases(messages):
    issues = []
    for i, m in enumerate(messages):
        if m.get("role") != "assistant":
            continue
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content)
        content_lower = content.lower()
        for phrase in BANNED_PHRASES:
            if phrase in content_lower:
                issues.append(f"  ❌ Message {i}: Used '{phrase}' — \"{content[:100]}...\"")
    return issues

def check_download_links(messages):
    issues = []
    for i, m in enumerate(messages):
        if m.get("role") != "assistant":
            continue
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content)
        if "bcourses.berkeley.edu/files/" in content and "/download" in content:
            if REQUIRED_IN_LINKS not in content:
                issues.append(f"  ❌ Message {i}: Download link missing access_token — \"{content[:150]}...\"")
    return issues

def check_verbosity(messages):
    issues = []
    assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
    for i, m in enumerate(assistant_msgs):
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content)
        # Check for filler-only messages (announcing what they're about to do)
        filler_starters = [
            "let me ", "i'll ", "checking ", "pulling up", "fetching",
            "got it.", "alright,", "okay,", "sure,", "great question"
        ]
        content_lower = content.lower().strip()
        if len(content) < 100 and any(content_lower.startswith(f) for f in filler_starters):
            issues.append(f"  ⚠️ Message {i}: Filler response — \"{content[:100]}\"")
    return issues

def check_response_stats(messages):
    user_msgs = [m for m in messages if m.get("role") == "user"]
    assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
    tool_calls = [m for m in messages if m.get("role") == "tool"]

    return {
        "user_messages": len(user_msgs),
        "bot_responses": len(assistant_msgs),
        "tool_calls": len(tool_calls),
        "avg_response_length": sum(
            len(m.get("content", "") if isinstance(m.get("content"), str) else str(m.get("content", "")))
            for m in assistant_msgs
        ) // max(len(assistant_msgs), 1)
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
        issues.append(f"  ⚠️ Made {api_calls} API calls but never read cache — should use cache for quick queries")

    return issues, cache_reads, api_calls

def main():
    print("🐻 bCourses Bot QA Report")
    print("=" * 50)

    messages = load_messages()
    stats = check_response_stats(messages)

    print(f"\n📊 Stats:")
    print(f"  User messages: {stats['user_messages']}")
    print(f"  Bot responses: {stats['bot_responses']}")
    print(f"  Tool calls: {stats['tool_calls']}")
    print(f"  Avg response length: {stats['avg_response_length']} chars")

    print(f"\n🔍 Banned Phrases Check:")
    issues = check_banned_phrases(messages)
    if issues:
        for i in issues:
            print(i)
    else:
        print("  ✅ No banned phrases found")

    print(f"\n🔗 Download Links Check:")
    issues = check_download_links(messages)
    if issues:
        for i in issues:
            print(i)
    else:
        print("  ✅ All download links have access_token")

    print(f"\n💬 Verbosity Check:")
    issues = check_verbosity(messages)
    if issues:
        for i in issues:
            print(i)
    else:
        print("  ✅ No unnecessary filler responses")

    print(f"\n📦 Cache Usage:")
    issues, cache_reads, api_calls = check_cache_usage(messages)
    print(f"  Cache reads: {cache_reads}")
    print(f"  API calls: {api_calls}")
    if issues:
        for i in issues:
            print(i)
    else:
        print("  ✅ Cache usage looks good")

    print(f"\n{'=' * 50}")
    total_issues = (len(check_banned_phrases(messages)) +
                   len(check_download_links(messages)) +
                   len(check_verbosity(messages)) +
                   len(check_cache_usage(messages)[0]))
    if total_issues == 0:
        print("🎉 All checks passed! Go Bears!")
    else:
        print(f"⚠️ {total_issues} issues found — review above")

if __name__ == "__main__":
    main()
