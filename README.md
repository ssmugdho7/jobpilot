# JobPilot

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Flask](https://img.shields.io/badge/flask-3.0-green)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

**Bangladesh IT Job Finder + ATS CV Generator**

JobPilot scans LinkedIn, BDJobs, and company career pages for IT jobs in Bangladesh, then helps you apply with a tailored ATS CV — all from a clean web dashboard.

---

## Features

- **Multi-source job scanning** — LinkedIn, BDJobs, company career pages (SmartRecruiters, Greenhouse, Lever, Ashby), Facebook groups/pages
- **Smart filtering** — filter by status (new, applied, dismissed) and posting age (1 day, 3 days, 1 week, 1 month)
- **Gmail draft integration** — one-click opens a pre-written email with your CV attached
- **ATS CV generation** — creates a tailored DOCX + PDF for each job while preserving your original CV formatting
- **Manual job entry** — paste any job link or text (Facebook posts, company sites, etc.)
- **Multi-key rotation** — supports multiple Gemini API keys with automatic failover

---

## Quick Start

### Prerequisites

- Python 3.10 or higher
- Microsoft Word (optional, for format-preserving PDF generation)

### Installation

```bash
# Clone the repository
git clone https://github.com/ssmugdho7/jobpilot.git
cd jobpilot

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root:

```env
# Get keys from: https://aistudio.google.com/apikey
# Add multiple keys (comma-separated) for auto-rotation
GEMINI_API_KEYS=your_key_1,your_key_2,your_key_3
GEMINI_MODEL=gemini-3-flash-preview

# Optional: Facebook access token for group/page scraping
FACEBOOK_ACCESS_TOKEN=your_token_here

# Flask secret key (required for sessions)
SECRET_KEY=your_random_secret_key
```

> **Tip:** Free tier gives 20 requests/day per key. Add 2-3 keys for 40-60 requests/day.

### Run the App

```bash
# One-time scan + web dashboard
python main.py --once

# Web dashboard with background scanning (recommended)
python main.py --web
```

Open **http://localhost:5001** in your browser.

---

## How It Works

```
main.py --web
    ├── BDJobs (HTML)
    ├── LinkedIn (HTML)
    └── Company Career Pages (API/HTML)
            │
            ▼
       Pipeline (clean → dedup → score → save)
            │
            ▼
       Web Dashboard (Flask + SQLite)
            │
            ├── Filter & paginate jobs
            ├── Open Gmail draft
            └── Generate ATS CV (Gemini + Word COM)
```

### AI Usage

JobPilot uses **Google Gemini** for exactly two tasks:

1. **CV Parsing** — extracts structured data (name, skills, experience, education) from your uploaded CV
2. **ATS CV Tailoring** — rewrites CV sections to match a specific job posting

Everything else (job fetching, keyword matching, database, web UI, PDF generation) uses traditional Python code — no vector databases, no embeddings, no RAG.

---

## Usage

1. **Upload your CV** — go to **Profile / Upload CV** and upload your PDF or DOCX
2. **Scan for jobs** — click **Scan LinkedIn / BDJobs / Facebook now** on the main page
3. **Filter jobs** — use status and posting-age filters to narrow results
4. **Take action** for each job:
   - **Open Gmail draft** — pre-filled email with your CV attached
   - **View source** — open the original job posting
   - **Generate ATS CV** — create a tailored DOCX + PDF
   - **Mark status** — track applied/dismissed jobs

---

## Configuration

| File | Purpose |
|------|---------|
| `.env` | API keys and tokens (never commit this) |
| `config/search.yaml` | Job search settings (roles, max age, Facebook groups) |
| `config/careers.yaml` | Company career page sources |

### Example `config/search.yaml`

```yaml
roles:
  - "web developer"
  - "software engineer"
  - "devops engineer"

location: "Bangladesh"
bdjobs_max_pages: 3
max_age_days: 30
min_relevance_score: 0.0
```

---

## Adding Job Sources

### Company Career Pages

Edit `config/careers.yaml`:

```yaml
companies:
  - name: "Your Company"
    site: "yourcompany.com"
    careers_url: "https://yourcompany.com/careers/"
    type: html
```

**Supported types:** `html`, `smartrecruiters`, `greenhouse`, `lever`, `ashby`

### Facebook Groups

Facebook blocks anonymous scraping. Add a `FACEBOOK_ACCESS_TOKEN` to `.env` and group IDs to `config/search.yaml`, or use the **manual add** feature for individual posts.

---

## Project Structure

```
jobpilot/
├── main.py                    # Entry point
├── requirements.txt
├── .env                       # Your keys (create this)
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
│   ├── filter.py              # Role detection & scoring
│   ├── gmail_link.py          # Gmail URL builder
│   ├── db.py                  # Database models
│   ├── web/
│   │   ├── app.py             # Flask routes
│   │   └── templates/
│   │       └── index.html     # Dashboard
│   └── cv/
│       ├── parse.py           # CV text extraction
│       ├── profile.py         # Profile from CV
│       ├── ats.py             # Tailor CV to job
│       └── render.py          # DOCX + PDF generation
└── test_endpoints.py          # Integration tests
```

---

## Deployment

### Render (free tier)

See [DEPLOYMENT.md](DEPLOYMENT.md) for full instructions.

1. Push to GitHub
2. Connect repo on [Render](https://dashboard.render.com)
3. Add environment variables
4. Set up a cron job for periodic scans

Your app will be live at `https://jobpilot.onrender.com`.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Gemini API key not set" | Check `.env` has `GEMINI_API_KEYS=` with valid keys |
| "429 RESOURCE_EXHAUSTED" | All keys hit daily limit. Add more keys or wait until midnight UTC |
| "Word not found" for PDF | Install Microsoft Word, or the app falls back to reportlab |
| No jobs found | Click Scan, check internet, try a wider "Posted" filter |
| CV upload fails | Must be PDF or DOCX, not empty or password-protected |

---

## License

Built for Bangladesh IT job seekers.

**Tech stack:** Flask, SQLAlchemy, Google Gemini, python-docx, reportlab, requests, BeautifulSoup
