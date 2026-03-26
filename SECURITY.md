# Security Policy

## Supported Versions

OpenMind is currently maintained as a single rolling release. Please report security issues against the latest `main` branch and the most recent tagged release once tags are published.

## Reporting a Vulnerability

Please do not open a public GitHub issue for suspected security vulnerabilities.

Use one of these private paths:

- A private GitHub security advisory, if enabled for the repo
- The maintainer email listed on the public GitHub profile

Include:

- A short description of the issue
- Steps to reproduce it
- Impact and any affected configuration
- A suggested fix if you have one

## Response Expectations

- Acknowledgement: within 7 days
- Triage: as quickly as practical based on severity
- Fix timeline: best effort, with priority given to token leakage, prompt-injection bypasses, SSRF, path traversal, and privacy misrepresentation

## Scope

Examples of in-scope issues:

- Token leakage in logs, prompts, or error messages
- SSRF bypasses in web or PDF fetching
- Path traversal or vault escape in Obsidian tools
- Canvas URL validation bypasses
- Prompt-injection paths that allow unintended cross-tool access
- Incorrect privacy claims in shipped docs or CLI output

Out of scope:

- Self-inflicted misconfiguration on a local machine
- Missing features or unsupported third-party API behavior
- Issues in unreleased forks or modified deployments
