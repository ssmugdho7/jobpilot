# JobPilot — Bangladesh IT Job Finder

A simple, practical tool that finds IT jobs in Bangladesh and helps you apply with a tailored CV.

---

## What This Does

- **Finds jobs** from LinkedIn, BDJobs, and company career pages (all Bangladesh-focused, office in Bangladesh)
- **Shows jobs** in a clean web page with filters (by status, by how recently posted)
- **Gmail draft** — one click opens a pre-written email to the employer (you review & send)
- **ATS CV** — generates a tailored CV (DOCX + PDF) for each job, keeping your original CV's formatting
- **Manual add** — paste any job link/text (Facebook posts, company sites, etc.) and it becomes a normal job card

> **No RAG, no vector database, no embeddings.** This project uses **Google Gemini** for two specific tasks only: (1) parsing your uploaded CV into structured data, and (2) rewriting CV sections to match a job posting. There's no vector database, no document retrieval, no semantic search.

---

## Quick Start (5 minutes)

### 1. Get the code
```bash
git clone <your-repo-url>
cd ai-tool
```

### 2. Install requirements
```bash
pip install -r requirements.txt
```

### 3. Add your Gemini API keys
Create a `.env` file in the project root:
```bash
# Get keys from: https://aistudio.google.com/apikey
# Add multiple keys (comma-separated) — when one hits its daily limit, the next is used
GEMINI_API_KEYS=your_key_1,your_key_2,your_key_3
GEMINI_MODEL=gemini-3-flash-preview
```

**How to get a key:**
1. Go to https://aistudio.google.com/apikey
2. Click "Create API Key"
3. Copy the key (starts with `AQ.`)
4. Paste into `.env`

> **Tip:** Free tier gives 20 requests/day per key. Add 2-3 keys to get 40-60 requests/day automatically.

### 4. Run the app
```bash
# One-time scan + web dashboard
python main.py --once

# Or: web dashboard with background scanning (recommended)
python main.py --web
```
Open your browser to **http://localhost:5001**

---

## How the AI Works (Simple Explanation)

This project uses **Google Gemini** (via the `google-genai` Python library) for exactly **two things**:

### 1. CV Parsing (Profile Extraction)
When you upload your CV (PDF or DOCX):
1. The app extracts raw text from the file (using `pypdf` for PDF, `python-docx` for DOCX)
2. Sends the text to Gemini with a prompt: *"Extract name, email, phone, skills, experience, education, summary from this CV and return JSON"*
3. Gemini returns structured JSON: `{name, email, phone, skills: [...], experience: "...", education: "...", summary: "..."}`
4. This becomes your **base profile** — stored in the database

**No AI fallback:** If Gemini fails (quota exhausted, network error), a regex-based parser extracts what it can.

### 2. ATS CV Tailoring (Job-Specific CV Generation)
When you click "Generate ATS CV" for a job:
1. The app sends Gemini: *"Here's the job posting. Here's the candidate's base profile. Rewrite the summary, skills, experience, and education sections to match this job. Keep it honest — don't invent skills."*
2. Gemini returns tailored JSON: `{summary: "...", skills: [...], experience: "...", education: "..."}`
3. The app takes your **original uploaded CV file** (DOCX, or PDF converted to DOCX via Microsoft Word) and **swaps only the text** in the summary/skills/experience/education sections — **all formatting (fonts, colors, bullets, tables, layout) stays exactly the same**
4. Output: personalized DOCX + PDF (via Microsoft Word COM automation)

**No AI fallback:** If Gemini fails, the base profile is used as-is (no tailoring).

---

### What This Does NOT Use (No RAG, No Vector DB)

| Technique | Used? | Why Not |
|-----------|-------|---------|
| **RAG (Retrieval-Augmented Generation)** | ❌ No | We don't need to retrieve documents — the job posting is already given, and the CV is already uploaded |
| **Vector Database / Embeddings** | ❌ No | No semantic search needed — we match jobs by keywords + location, not by "similarity" |
| **Semantic Search / Similarity** | ❌ No | Job matching is done by keyword scoring (see `app/filter.py`) |
| **Fine-tuning / Custom Models** | ❌ No | Gemini's general knowledge is sufficient for CV parsing & tailoring |
| **LangChain / LlamaIndex / Frameworks** | ❌ No | Direct API calls are simpler and more controllable |

---

### Multi-Key Rotation (Auto-Failover)

The app supports **multiple Gemini API keys** in `.env`:
```env
GEMINI_API_KEYS=key1,key2,key3
```
When one key hits its daily quota (20 requests/day on free tier):
1. The key is marked "exhausted for today"
2. The next key is tried immediately
3. Keys rotate automatically — zero manual intervention

**Free tier math:** 20 requests/day × 3 keys = 60 requests/day total.

---

### Fallback Chain (What Happens When AI Fails)

| Step | What Happens |
|------|--------------|
| 1. Try Key 1 | If success → done |
| 2. Key 1 quota exhausted | Mark exhausted, try Key 2 |
| 3. All keys exhausted | Use regex/template fallback (no AI) |
| 4. Network error / other | Retry once with backoff, then fallback |

**Result:** The app **never crashes** due to AI quota. It gracefully degrades to non-AI mode.

---

### File Map for AI Parts

| File | Purpose |
|------|---------|
| `app/gemini.py` | Multi-key client, rotation, rate-limit handling |
| `app/cv/profile.py` | CV → structured profile (calls Gemini) |
| `app/cv/ats.py` | Tailor CV to job (calls Gemini) |
| `app/cv/render.py` | **Format-preserving** DOCX/PDF generation (no AI — uses Word COM) |
| `app/cv/parse.py` | Text extraction from PDF/DOCX (no AI) |
| `app/filter.py` | Keyword-based role detection & scoring (no AI) |

---

### Mental Model: AI as a "Text Rewriter"

Think of the AI as a **smart text rewriter** that:
1. **Reads** your CV → gives you structured data
2. **Reads** a job posting + your profile → rewrites 4 sections to match

Everything else (job fetching, keyword matching, database, web UI, Gmail links, PDF generation) is **classic code** — no AI involved.

---

> **Bottom line:** This is a **practical tool with targeted AI**, not an "AI-first" architecture. The AI does exactly two focused text tasks; the rest is reliable, debuggable Python.

---

## How to Use the Dashboard

### 1. Upload Your Base CV
- Click **Profile / Upload CV** in the top nav
- Upload your PDF or DOCX
- The app extracts your name, skills, experience, education
- This becomes your "base CV" — all tailored CVs start from this

### 2. Scan for Jobs
- On the main page, click **Scan LinkedIn / BDJobs / Facebook now**
- Wait ~30-60 seconds (it fetches from multiple sources)
- Jobs appear in the list, newest first

### 3. Filter Jobs
- **Status:** All / New / Applied / Dismissed
- **Posted:** 1 day / 3 days / 1 week / 1 month
- **Pagination:** 20 jobs per page, click page numbers at bottom

### 4. For Each Job You Can:
| Button | What It Does |
|--------|--------------|
| **Open Gmail draft** | Opens Gmail compose with email pre-filled (to HR, subject, body, your CV attached) — you just hit Send |
| **View source website** | Opens the original job posting |
| **Generate ATS CV** | Creates a tailored DOCX + PDF for this specific job |
| **Mark: applied / dismissed** | Organize your pipeline |

---

## Adding More Job Sources

### Company Career Pages
Edit `config/careers.yaml`:
```yaml
companies:
  - name: "Your Company"
    site: "yourcompany.com"
    type: html              # or smartrecruiters, greenhouse, lever, ashby
    careers_url: "https://yourcompany.com/careers/"
    type: html              # for static HTML pages
    # OR for SmartRecruiters:
    identifier: "YourCompanySlug"
    type: smartrecruiters
```

**Supported types:**
| Type | What It Is | Example |
|------|------------|---------|
| `html` | Static HTML page with job links | Therap, Reve Systems |
| `smartrecruiters` | SmartRecruiters API | Portonics |
| `greenhouse` | Greenhouse job board API | (add when found) |
| `lever` | Lever API | (add when found) |
| `ashby` | Ashby GraphQL API | (add when found) |

### Facebook Jobs
Facebook blocks anonymous scraping. To auto-fetch:
1. Create a Facebook App at https://developers.facebook.com
2. Get a **User Access Token** or **Page Access Token** with `pages_read_engagement` / `groups_read_member`
3. Add to `.env`:
   ```
   FACEBOOK_ACCESS_TOKEN=your_token_here
   ```
4. Add group/page IDs to `config/search.yaml`:
   ```yaml
   facebook_groups:
     - "your_job_group_id"
   ```

> **Note:** If you just follow groups (not admin), the API won't work. Use the **manual-add box** for Facebook posts — paste the link/text and it works instantly.

---

## Configuration Files

| File | Purpose |
|------|---------|
| `.env` | API keys, tokens (never commit this!) |
| `config/search.yaml` | Job search settings (roles, max age, Facebook groups) |
| `config/careers.yaml` | Company career page sources |
| `requirements.txt` | Python packages |

### `config/search.yaml` Example
```yaml
roles:
  - "web developer"
  - "ai engineer"
  - "it executive"
  - "software engineer"
  - "devops or cloud engineer"
  - "qa analyst"
  - "data analyst"
  - "app developer"

location: "Bangladesh"
bdjobs_max_pages: 3
max_age_days: 30
min_relevance_score: 0.0

facebook_groups:
  - "jobcircularsbd"
facebook_pages:
  - "jobpilotbd"
facebook_terms:
  - "vacancy"
  - "hiring"
```

---

## How It Works (Simple Mental Model)

```
┌─────────────────────────────────────────────────────────────┐
│                      main.py --web                          │
└─────────────────────────┬───────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
   ┌─────────┐       ┌──────────┐      ┌──────────┐
   │ BDJobs  │       │ LinkedIn │      │ Careers  │
   │ (HTML)  │       │ (HTML)   │      │ (API/HTML)│
   └────┬────┘       └────┬─────┘      └────┬─────┘
        │                 │                 │
        └─────────────────┼─────────────────┘
                          ▼
                   ┌──────────────┐
                   │  Pipeline    │
                   │  (dedup,     │
                   │   role,      │
                   │   score,     │
                   │   save)      │
                   └──────┬───────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
   ┌──────────┐     ┌───────────┐     ┌────────────┐
   │  SQLite  │     │  Web UI    │     │  Gmail     │
   │  (jobs)  │◄───►│  (Flask)   │     │  draft     │
   └──────────┘     └───────────┘     └────────────┘
                          │
                          ▼
                   ┌──────────────┐
                   │  ATS CV Gen  │
                   │  (Gemini +   │
                   │   Word COM)  │
                   └──────────────┘
```

**Key ideas:**
- **Sources** fetch raw job data → **Pipeline** cleans, deduplicates, scores → **Database** stores
- **Web UI** reads from DB, shows filters + pagination
- **Gmail link** builds a `mailto:` URL with subject, body, attachment flag
- **ATS CV** uses your uploaded CV as a template, swaps only the text sections (summary, skills, experience, education) using Gemini, keeps all formatting

---

## Key Files & What They Do

| File | Role |
|------|------|
| `main.py` | Entry point (`--web`, `--once`) |
| `app/web/app.py` | Flask routes (web UI + API) |
| `app/web/templates/index.html` | Single-page dashboard (HTML + JS) |
| `app/sources.py` | Job fetchers (BDJobs, LinkedIn, Career pages, Facebook) |
| `app/pipeline.py` | Scan orchestration (fetch → clean → dedup → score → save) |
| `app/filter.py` | Role detection + relevance scoring |
| `app/gemini.py` | **NEW:** Multi-key rotation, rate-limit handling |
| `app/cv/render.py` | Format-preserving CV generation (DOCX + PDF via Word COM) |
| `app/cv/profile.py` | CV parsing → structured profile |
| `app/cv/ats.py` | Tailoring CV to a job posting |
| `app/gmail_link.py` | Gmail compose URL builder |
| `app/db.py` | SQLAlchemy models (Job, Profile) |
| `config/search.yaml` | Search settings |
| `config/careers.yaml` | Career page sources |

---

## Common Tasks

### Run a One-Time Scan (no web server)
```bash
python main.py --once
```

### Run on a Different Port
```bash
python main.py --web --port 8080
```

### Reset the Database
```bash
rm data/jobs.db
python main.py --once
```

### View Logs
All scans print to console:
```
=== JobPilot scan (Bangladesh) ===
  [bdjobs] collected 50 jobs
  [linkedin] collected 365 jobs
  [careers] Therap (BD) Ltd: 3 jobs
  [careers] Portonics: 2 jobs
  [sources] collected 420 raw jobs
  [scan] inserted=5 skipped_dups=380 no_role=25 too_old=0
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Gemini API key not set" | Check `.env` has `GEMINI_API_KEYS=` with valid keys |
| "429 RESOURCE_EXHAUSTED" | All keys hit daily limit (20 req/day each). Add more keys or wait until midnight UTC. |
| "Word not found" for PDF | Install Microsoft Word, or the app falls back to reportlab (basic PDF) |
| No jobs found | Click Scan, check internet, try wider "Posted" filter (7/30 days) |
| CV upload fails | Must be PDF or DOCX, not empty, not password-protected |
| Facebook shows 0 jobs | Add `FACEBOOK_ACCESS_TOKEN` to `.env` and group IDs to `config/search.yaml` |

---

## Adding More API Keys (Auto-Rotation)

The app supports **multiple Gemini keys** out of the box. When one key hits its daily 20-request limit, it automatically switches to the next key.

**In `.env`:**
```env
# Option 1: Comma-separated (recommended)
GEMINI_API_KEYS=key1,key2,key3

# Option 2: Numbered (also works)
GEMINI_API_KEY_1=key1
GEMINI_API_KEY_2=key2
```

**How it works:**
1. App tries key 1
2. If key 1 gets 429 (quota exhausted), it marks key 1 as "exhausted for today"
3. Immediately tries key 2, then key 3
4. Keys are rotated automatically — you don't do anything

---

## Project Structure

```
ai-tool/
├── main.py                    # Entry point
├── requirements.txt
├── .env                       # Your keys (create this)
├── .env.example               # Template
├── config/
│   ├── search.yaml            # Search settings
│   └── careers.yaml           # Career page sources
├── data/
│   ├── jobs.db                # SQLite database
│   ├── uploads/               # Uploaded CVs
│   └── cv/                    # Generated ATS CVs
├── app/
│   ├── gemini.py              # Multi-key Gemini client
│   ├── pipeline.py            # Scan orchestration
│   ├── sources.py             # Job fetchers
│   ├── filter.py              # Role detection
│   ├── gmail_link.py          # Gmail URL builder
│   ├── db.py                  # Database models
│   ├── config.py              # Config loaders
│   ├── paths.py               # Path helpers
│   ├── web/
│   │   ├── app.py             # Flask routes
│   │   └── templates/
│   │       └── index.html     # Dashboard
│   └── cv/
│       ├── parse.py           # CV text extraction
│       ├── profile.py         # Profile from CV
│       ├── ats.py             # Tailor CV to job
│       ├── render.py          # Format-preserving DOCX/PDF
│       └── word_convert.ps1   # Word COM helper
└── test_endpoints.py          # Integration tests
```

---

## License & Credits

Built for Bangladesh IT job seekers. Uses:
- **Flask** — web framework
- **SQLAlchemy** — database
- **google-genai** — Gemini API
- **python-docx** — DOCX manipulation
- **reportlab** — PDF fallback
- **requests + BeautifulSoup** — web scraping

---

## TL;DR for Beginners

1. **Install Python 3.10+**
2. **Clone repo → `pip install -r requirements.txt`**
3. **Create `.env` with your Gemini keys** (get from aistudio.google.com)
4. **Run `python main.py --web`**
5. **Open http://localhost:5001**
6. **Upload your CV → Click Scan → Apply to jobs!**

That's it. Happy job hunting! 🎯