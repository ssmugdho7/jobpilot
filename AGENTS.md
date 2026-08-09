# JobPilot

AI job scanner for **CSE jobs in Bangladesh** (office/onsite). The platform is for Bangladeshis and only surfaces postings with an **office located in Bangladesh**. Discovers the 8 target roles from **BDJobs** + **LinkedIn (Bangladesh)**, then prepares a **Gmail compose link** and an **ATS-friendly CV** (DOCX + PDF) for every job, personalized from a user-uploaded base CV while **preserving the uploaded CV's formatting**. Postings found on **Facebook**, **NextJobz** or **company sites** are added through the manual-add box (paste URL/text).

## Target roles (jobs tab)

`web developer`, `ai engineer`, `it executive`, `software engineer`, `devops or cloud engineer`, `qa analyst`, `data analyst`, `app developer`

## Posted-within filter

Default **1 day**, with 3 days / 1 week / 1 month options. Jobs are stored with a `posted_date` (BDJobs `publishDate`, LinkedIn `time[datetime]`); the `/` route filters `posted_date >= now - days`.

## Tech Stack

- Python 3.14, Flask, SQLAlchemy (SQLite at `data/jobs.db`)
- Sources: **BDJobs** SSR page (`gateway.bdjobs.com/joblist/jobs?fcatId=8`, ng-state JSON) + **LinkedIn** jobs search (guest HTML, `location=Bangladesh`, `f_TPR`) + **company career pages** (HTML list pages, SmartRecruiters / Greenhouse / Lever / Ashby JSON APIs — configured in `config/careers.yaml`) + **Facebook** job posts (Graph API, needs `FACEBOOK_ACCESS_TOKEN`), fetched in parallel. Facebook blocks anonymous scraping (HTTP 400 on this network), so without a token its posts arrive via the manual-add box.
- Every posting is verified as **Bangladesh-located**: `_is_bangladesh_location()` in `app/sources.py` keeps jobs whose location mentions a BD city/district or "Bangladesh", and **drops** jobs whose location names a non-BD country (India, US, UK, UAE, Singapore, ...). Pure "Remote" (no non-BD country) is kept — these are remote roles hired from BD.
- Gemini (`google-genai`) for CV parsing + ATS CV tailoring (regex/template fallback)
- `pypdf` (PDF read), `python-docx` (DOCX read/write), `reportlab` (PDF fallback), Word COM (PowerShell) for DOCX→PDF and PDF→DOCX template conversion
- `test_endpoints.py` — 22 endpoint tests (22/22 pass)

## Running

```bash
pip install -r requirements.txt
python main.py --web        # scan in background + dashboard on http://localhost:5001
python main.py --once       # run one scan and exit
python main.py --web --port 8080
```

Then in the browser:
1. `/profile` → upload your default CV (PDF/DOCX), review the parsed profile, save.
2. `/` → click **Scan BDJobs / LinkedIn now**, pick a **Posted** window (1d/3d/1w/1m), open the **Gmail draft** for any job, or click **Generate ATS CV**.
3. Mark jobs **new / applied / dismissed** and filter by status. The manual-add box pastes any posting URL/text (e.g. a company careers page).

## Env Vars (`.env`)

```
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3-flash-preview
FACEBOOK_ACCESS_TOKEN=   # optional; enables automatic Facebook job fetching
```

## Config

- `config/search.yaml` — 8 target roles, BDJobs pages, `max_age_days` (default 30), `min_relevance_score`, `facebook_groups`/`facebook_pages`/`facebook_terms`.
- `config/careers.yaml` — company career pages. Each entry has `name`, `site`, `type` (`html`/`smartrecruiters`/`greenhouse`/`lever`/`ashby`), and a type-specific key (`careers_url` for HTML, `identifier` for SmartRecruiters, `board` for Greenhouse, `slug` for Lever/Ashby). Only Bangladesh-located jobs that match one of the 8 roles are kept. Career page positions use `posted_date=None` (open until removed, never age-filtered).

## Key Architecture

- `app/sources.py` — `fetch_bangladesh_jobs()` = `fetch_bdjobs()` (ng-state from the Software/IT category page, job details URL `jobs.bdjobs.com/jobdetails/?id=<Jobid>`) + `fetch_linkedin()` (parallel per-role keyword searches in Bangladesh, filtered by `_is_bangladesh_location`) + `fetch_careers()` (config-driven career pages: HTML list parsers + SmartRecruiters/Greenhouse/Lever/Ashby JSON APIs, configured in `config/careers.yaml`) + `fetch_facebook()` (Graph API; groups/pages from config; needs token). Every job carries `source_site` (`bdjobs.com` / `linkedin.com` / company domain / `facebook.com`), `posted_date`, `deadline`, `salary`.
- `app/filter.py` — `detect_role()` assigns one of the 8 roles by keyword matching (specific roles first, software engineer as catch-all); `score_job()`/`is_relevant()` gate storage.
- `app/gmail_link.py` — `mail.google.com/?view=cm&...` builder (never auto-sends).
- `app/pipeline.py` — `run_scan()`: fetch → clean → role-detect → score → dedup → persist. `run_scan_async()` runs scans in a background thread (lock-guarded).
- `app/gemini.py` — fails fast when the daily free-tier quota (20 req/day) is exhausted so fallbacks kick in quickly.
- `app/cv/parse.py` — PDF/DOCX text extraction + contact regex.
- `app/cv/profile.py` — Gemini (with regex fallback) turns raw CV text into a structured profile.
- `app/cv/ats.py` — Gemini tailors summary/skills/experience/education to a job's posting.
- `app/cv/render.py` — **strictly format-preserving renderer**: `render_cv_docx` copies the uploaded CV (DOCX, or PDF converted to DOCX via Word) and swaps ONLY the text of the summary/skills/experience/education sections — each new line maps onto an existing paragraph (fonts/colors/bullets/numbering/spacing kept), extra lines clone the first paragraph's formatting, surplus paragraphs are removed, and tables (contact/sidebar layouts) are never touched; `render_cv_pdf` converts the personalized DOCX to PDF via Word COM, falling back to a clean reportlab render when Word is unavailable. Helper `app/cv/word_convert.ps1` drives Word COM.
- `app/web/app.py` — Flask routes: `/`, `/profile`, `/api/scan`, `/api/cv/upload`, `/api/profile`, `/api/jobs/manual` (paste URL/text), `/api/jobs/<id>/status`, `/api/jobs/<id>/cv`, `/api/jobs/<id>/cv.docx`, `/api/jobs/<id>/cv.pdf`.

## Notes

- Facebook: anonymous scraping is blocked (HTTP 400 from this network) and the Graph API only returns posts from Pages/Groups the app's admin **owns** (dev-mode apps cannot read groups/pages you merely follow). So Facebook job posts are added via the manual-add box (paste the post link/text) unless the user manages a Page or administers a Group.
- BDJobs SSR only exposes the latest 50 Software/IT postings (pageNo is ignored); LinkedIn adds ~200+ BD postings per scan, so the combined feed is fresh daily.
- No emails are sent automatically — Gmail links open a pre-filled draft for the user to review/send.
- CV generation never fabricates credentials; Gemini is instructed to reword only.
