# Pre-Deployment Checklist — JobPilot

Use this checklist before deploying to production. It covers branch state, required files, environment variables, host-specific notes, and post-deploy verification.

---

## 1. Branch and repo state

- [ ] Current branch is **`main`** (or the branch you intend to deploy)
- [ ] All desired changes are merged into that branch
- [ ] `git status` shows **clean working tree**
- [ ] `git remote -v` points to `https://github.com/ssmugdho7/jobpilot.git`
- [ ] Latest commit is pushed: `git push origin main`

**Current staging → main delta:**
```bash
git log --oneline main..staging
# Should show the commits you want to deploy
```

---

## 2. Required production files

These files must exist at the project root:

- [ ] **`Procfile`** — web process command
- [ ] **`render.yaml`** — Render service + disk config (if deploying on Render)
- [ ] **`requirements.txt`** — includes `gunicorn>=21.0`
- [ ] **`.env.example`** — documents required env vars (do NOT commit real `.env`)

Verify:
```bash
cat Procfile
cat render.yaml
grep gunicorn requirements.txt
```

---

## 3. Production-ready code checks

### Port binding
- [ ] `app/web/app.py` — `start_web()` uses `PORT` env var with fallback
```python
def start_web(host="0.0.0.0", port=None):
    port = port or int(os.environ.get("PORT", 5001))
```

### Word COM guard (Linux hosts)
- [ ] `app/cv/render.py` disables Word COM on non-Windows
```python
if os.name != "nt":
    _WORD_AVAILABLE = False
    return False
```
- [ ] PDF generation falls back to reportlab when Word is unavailable

### Data directory
- [ ] `app/paths.py` creates `data/`, `data/uploads/`, `data/cv/` on startup
- [ ] DB path uses relative path from project root: `data/jobs.db`
- [ ] On Render, disk is mounted at `/opt/render/project/src/data`
- [ ] On Railway, volume is mounted at `/app/data`

### Static files
- [ ] Flask serves templates from `app/web/templates/`
- [ ] If using separate static folder, configure `static_url_path` / `static_folder`

---

## 4. Environment variables

Set these in your hosting dashboard (Render → Environment, Railway → Variables, PythonAnywhere → Web → Environment):

| Variable | Required | Example / Notes |
|---|---|---|
| `GEMINI_API_KEY` | Yes | Your Google AI Studio key |
| `GEMINI_API_KEYS` | No | Comma-separated for quota rotation |
| `GEMINI_MODEL` | Yes | `gemini-3-flash-preview` |
| `FACEBOOK_ACCESS_TOKEN` | Optional | Facebook Graph API token |
| `SECRET_KEY` | Yes | Random long string for Flask sessions |
| `PYTHON_VERSION` | Render only | `3.11.9` (already in `render.yaml`) |

**Never commit `.env` to Git.**

---

## 5. Host-specific configuration

### Render (recommended)

- [ ] Web service created from `ssmugdho7/jobpilot` repo
- [ ] `render.yaml` auto-detected (or paste contents manually)
- [ ] Disk attached: name `jobpilot-data`, mount `/opt/render/project/src/data`, size `1 GB`
- [ ] Build command: `pip install -r requirements.txt`
- [ ] Start command: `gunicorn app.web.app:app --bind 0.0.0.0:$PORT --timeout 120 --workers 1`
- [ ] Environment variables set (see section 4)
- [ ] **Cron job added** to trigger `/api/scan` every 3 hours:
  - Schedule: `0 */3 * * *`
  - URL: `/api/scan`
  - Method: `POST`
  - Service: `jobpilot`

### Railway

- [ ] Project deployed from `ssmugdho7/jobpilot` repo
- [ ] Variables set (see section 4)
- [ ] Volume created: mount `/app/data`, size `1 GB`
- [ ] Start command: `gunicorn app.web.app:app --bind 0.0.0.0:$PORT --timeout 120 --workers 1`
- [ ] Scheduler / cron job set up to hit `/api/scan`

### PythonAnywhere

- [ ] Repo cloned to `/home/yourusername/jobpilot`
- [ ] Virtualenv created with Python 3.11
- [ ] `pip install -r requirements.txt gunicorn`
- [ ] WSGI config points to `app.web.app:app`
- [ ] Environment variables set
- [ ] Web app reloaded

---

## 6. Database migration and persistence

- [ ] `data/jobs.db` will be created on first run (`init_db()` in `app/db.py`)
- [ ] SQLite file is on persistent storage (disk/volume/home dir)
- [ ] `init_db()` runs lightweight migrations for new columns:
  - `jobs.status`, `jobs.posted_date`, `jobs.deadline`, `jobs.hr_email`, `jobs.experience_level`
  - `user_jobs.follow_up_at`
  - `users.onboarding_done`, `users.pref_roles`, `users.pref_days`
  - `profile.user_id`

---

## 7. Post-deploy verification

After deploying, verify these endpoints and features:

### Health check
```bash
curl https://your-app.onrender.com/
```
- [ ] Returns 200 with `JobPilot` in HTML

### Dashboard
- [ ] `/dashboard` loads with job cards
- [ ] Filters work: status, posted window, experience, role
- [ ] Sort dropdown works: Latest posted, Most relevant, Deadline soon
- [ ] Pagination works across filtered/sorted views
- [ ] Source badges show correctly (not full-width on mobile)

### API
```bash
curl -X POST https://your-app.onrender.com/api/scan -H "Content-Type: application/json" -d "{}"
```
- [ ] Returns `{"ok": true, "started": true}`
- [ ] Scan completes without errors (check Render logs)

### Auth
- [ ] Register new user works
- [ ] Login works
- [ ] Logout works
- [ ] Onboarding modal appears for new users

### Profile
- [ ] `/profile` loads
- [ ] Save profile works

### Mobile
- [ ] Job title is clearly visible on small screens
- [ ] Buttons are full-width and tappable (min 44px height)
- [ ] Source badge is compact, not stretched
- [ ] Pagination buttons are large enough for thumbs
- [ ] Header nav scrolls horizontally if needed

---

## 8. Feature checklist

Confirm these features are present in the deployed build:

- [ ] **Date filter** — 1 day / 3 days / 1 week / 1 month
- [ ] **Experience filter** — Fresher, 2y, 3y, 3+ years
- [ ] **Role filter** — All 8 target roles + custom roles
- [ ] **Sort** — Latest posted / Most relevant / Deadline soon
- [ ] **Early applicant badge** — highlighted orange pill when detected
- [ ] **Preloader** — spinner on initial page load
- [ ] **Onboarding** — modal for new users to set preferences
- [ ] **Status tracking** — New / Applied / Dismissed with follow-up reminders
- [ ] **Skill gap analysis** — matched/missing skills bar
- [ ] **Company links** — Glassdoor + Deshimula
- [ ] **Learning hub** — rotating topics every 20 minutes
- [ ] **Gmail draft link** — per job (if HR email found)
- [ ] **Manual job add** — paste URL/text to add external postings
- [ ] **Dark mode** — toggle persists in localStorage

---

## 9. Security checklist

- [ ] `SECRET_KEY` is set to a strong random value (not the default)
- [ ] `.env` is in `.gitignore` and not pushed
- [ ] Passwords are hashed with `werkzeug.security`
- [ ] No credentials or API keys are logged or exposed in templates
- [ ] `FACEBOOK_ACCESS_TOKEN` is optional; app works without it

---

## 10. Performance and limits

- [ ] Free tier limits understood:
  - **Render:** 512 MB RAM, sleeps after 15 min, cron jobs available
  - **Railway:** $5/month credit, then paid
  - **PythonAnywhere:** 512 MB, always-on, no cron on free tier
- [ ] Scans are triggered via cron, not background threads (for Render)
- [ ] SQLite DB is on persistent disk to survive redeploys

---

## Quick deploy commands

```bash
# 1. Switch to main and merge staging
git checkout main
git merge staging
git push origin main

# 2. Verify clean state
git status
git log --oneline -5

# 3. Push any remaining changes
git push origin main
```

Then follow **Option A: Render** steps in `DEPLOYMENT.md` to complete deployment.
