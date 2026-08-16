# Deployment Guide — JobPilot

## Deploy on Render (free tier)

### 1. Prepare production files

**`Procfile`** (project root):
```
web: gunicorn app.web.app:app --bind 0.0.0.0:$PORT --timeout 120 --workers 1
```

**`render.yaml`** (project root):
```yaml
services:
  - type: web
    name: jobpilot
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn app.web.app:app --bind 0.0.0.0:$PORT --timeout 120 --workers 1
    envVars:
      - key: GEMINI_MODEL
        value: gemini-3-flash-preview
      - key: PYTHON_VERSION
        value: 3.11.9
    disk:
      name: jobpilot-data
      mountPath: /opt/render/project/src/data
      sizeGB: 1
```

Add to `requirements.txt`:
```
gunicorn>=21.0
```

### 2. Production-ready code checks already in place

**Port binding** — `app/web/app.py`:
```python
def start_web(host="0.0.0.0", port=None):
    port = port or int(os.environ.get("PORT", 5001))
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
```

**Word COM guard** — `app/cv/render.py`:
```python
if os.name != "nt":
    _WORD_AVAILABLE = False
    return False
```
PDF generation falls back to reportlab when Word is unavailable.

**Data directory** — `app/paths.py`:
- Creates `data/`, `data/uploads/`, `data/cv/` on startup
- DB path: `data/jobs.db`
- Render disk mount: `/opt/render/project/src/data`

### 3. Push to GitHub

```bash
git add .
git commit -m "prepare for render deploy"
git push origin main
```

### 4. Deploy on Render

1. Go to **https://dashboard.render.com** → **New +** → **Build and deploy from a Git repo**
2. Connect your GitHub repo
3. Select `ssmugdho7/jobpilot`
4. Render auto-detects `render.yaml` — verify settings
5. Add **Environment Variables**:
   - `GEMINI_API_KEY` — your key(s)
   - `GEMINI_API_KEYS` — comma-separated keys (optional, for quota rotation)
   - `GEMINI_MODEL` = `gemini-3-flash-preview`
   - `FACEBOOK_ACCESS_TOKEN` — optional
   - `SECRET_KEY` — random long string for Flask sessions
6. Click **Create Web Service**
7. Wait for build (2-5 min)

Your app will be live at `https://jobpilot.onrender.com`.

### 5. Set up cron job for scans

Render free tier sleeps after 15 minutes of inactivity. Use a Render Cron Job to keep scans running:

1. In Render dashboard → **Cron Jobs** → **New Cron Job**
2. Settings:
   - **Name:** `scan-jobs`
   - **Schedule:** `0 */3 * * *` (every 3 hours)
   - **URL:** `/api/scan`
   - **Method:** `POST`
   - **Service:** `jobpilot`

---

## Important notes

- **Background scans**: Do not rely on in-process background threads on Render free tier. Use the cron job above.
- **Word COM**: On Linux hosts, only the reportlab fallback works. It produces clean PDFs without Word formatting.
- **SQLite persistence**: The `render.yaml` disk config ensures `data/jobs.db` survives redeploys.
- **Free tier limits**: Render free tier gives 512 MB RAM. Suitable for personal use. For heavier traffic, upgrade to paid tiers.
- **Security**: Always set `SECRET_KEY` in production via environment variable.
