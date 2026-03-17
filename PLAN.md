# bCourses Bot — Public Release Plan

## Goal
Make the bCourses bot available for all UC Berkeley students. They download it, add their APIs, and use it privately.

---

## Phase 1: Clean Up (Before Release)

### Remove hardcoded data
- [ ] Replace hardcoded course IDs with dynamic fetching from Canvas API
- [ ] Move Canvas token, Todoist token, Gemini key to environment variables
- [ ] USER.md becomes a template — bot auto-fills courses on first run
- [ ] Remove personal Telegram user ID from repo — use env var

### Auto-onboarding flow
- [ ] Student runs `docker compose up`
- [ ] Bot sends first Telegram message: "Hey Bear! 🐻 Send me your Canvas API token to get started"
- [ ] Bot validates token, fetches courses, builds cache
- [ ] Bot asks: "Want to connect Todoist?" → optional setup
- [ ] Zero manual config file editing

### Simplify setup to 3 things
1. Telegram bot token (from @BotFather)
2. Canvas API token (from bCourses settings)
3. Gemini API key (from aistudio.google.com)

Everything else auto-configures.

---

## Phase 2: Make It Robust

### Error handling
- [ ] Canvas token expired → bot tells user how to refresh
- [ ] Gemini rate limit → graceful error message, retry later
- [ ] Todoist not connected → bot works without it, just skips task features
- [ ] Network errors → retry with backoff

### Multi-student testing
- [ ] Test with 3-5 Berkeley friends
- [ ] Collect feedback on setup experience
- [ ] Fix any course-specific issues (some courses use modules, some don't)
- [ ] Test with different course loads (2 courses vs 6 courses)

### Documentation
- [ ] Step-by-step setup guide with screenshots
- [ ] Video walkthrough (2 min)
- [ ] FAQ: common issues and fixes
- [ ] List of supported features

---

## Phase 3: Distribution

### Option A: Public GitHub Repo (Recommended to start)
- Effort: Low
- Reach: Anyone can fork and self-host
- Cost to you: $0
- Students need: Mac/Linux with Docker, or a cloud server

```
git clone https://github.com/qazybekb/bcourses_bot
cd bcourses_bot
cp .env.example .env
# Edit .env with your tokens
docker compose up -d
```

### Option B: One-Click Cloud Deploy
- Effort: Medium
- Reach: Students who don't want to run Docker locally
- Platforms: Railway, Render, Fly.io
- Cost: ~$5/month per student (they pay their own)
- Add: `railway.toml` or `render.yaml` for one-click deploy button in README

### Option C: Hosted Service (Future)
- Effort: High
- You run infrastructure for all students
- Need: multi-tenant support, billing, user management
- Cost: significant (API costs × number of students)
- Only worth it if you want to build a startup

---

## Phase 4: Growth

### Berkeley-specific
- [ ] Post on r/berkeley subreddit
- [ ] Share in MIMS/iSchool Slack
- [ ] Present at a CODEBASE or data science club meeting
- [ ] Ask professors to mention it (they'd love students using AI for studying)

### Expansion
- [ ] Support other Canvas LMS schools (just change base URL)
- [ ] Add more LLM providers (OpenAI, Claude, local models)
- [ ] Community-contributed course-specific prompts
- [ ] Plugin system for additional features

---

## Technical Changes Needed

### Environment Variables (.env file)
```
TELEGRAM_BOT_TOKEN=
TELEGRAM_USER_ID=
CANVAS_API_TOKEN=
CANVAS_BASE_URL=https://bcourses.berkeley.edu
GEMINI_API_KEY=
TODOIST_API_TOKEN=  # optional
```

### Config auto-generation
On first run, bot should:
1. Read env vars
2. Fetch active courses from Canvas
3. Generate config.json with correct course IDs
4. Generate USER.md with course list
5. Build initial course cache
6. Send welcome message on Telegram

### Docker Compose (simplified for students)
```yaml
services:
  bcourses-bot:
    image: ghcr.io/qazybekb/bcourses_bot:latest
    env_file: .env
    restart: unless-stopped
```

Pre-built Docker image on GitHub Container Registry — students don't even need the source code.

---

## Resume / Portfolio Value

"Built an open-source AI study assistant for UC Berkeley students"
- Canvas LMS API integration
- LLM orchestration (Gemini 2.5 Pro)
- MCP tool architecture
- Docker containerization
- Real users, real feedback

Relevant for: AI/ML roles, product engineering, EdTech, developer tools

---

## Timeline

| Week | What |
|------|------|
| 1 | Test thoroughly, fix remaining bugs |
| 2 | Remove hardcoded data, add env vars, auto-onboarding |
| 3 | Test with 3-5 friends, iterate on feedback |
| 4 | Clean up repo, write docs, record setup video |
| 5 | Public release on GitHub + post on r/berkeley |

---

## Risks

| Risk | Mitigation |
|------|-----------|
| Canvas API token security | Tokens stay local, never sent to external services. Add warning in README. |
| Gemini costs | Free tier covers most students. Add budget warning in docs. |
| Canvas API rate limiting | Cache aggressively, 700 req/10min is generous |
| Bot gives wrong info | Always fetch from Canvas, never guess. QA script catches issues. |
| UC Berkeley policy | Check with iSchool if sharing Canvas API tools is allowed |

---

*Go Bears! 🐻💙💛*
