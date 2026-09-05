# Security Policy

## Supported Versions

OpenMind is maintained as a single rolling release. Report security issues against the latest `main` branch and the most recent tagged release.

OpenMind runs on a student's own machine with their own bCourses token, so the threat model is: what could make it read more than the student allowed, write anything at all, or leak the token.

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
- SSRF bypasses in course-material downloads, including on redirect
- Path traversal in course-material extraction or in the catalog data asset
- Canvas URL validation bypasses
- Prompt-injection paths where course-document text changes tool behaviour or permissions
- Any path that lets a tool write to bCourses, or read a course the student did not enable
- Bearer token leakage to a redirect target off bCourses
- Incorrect privacy claims in shipped docs or CLI output

Out of scope:

- Self-inflicted misconfiguration on a local machine
- Missing features or unsupported third-party API behavior
- Issues in unreleased forks or modified deployments
