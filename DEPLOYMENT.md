# Deployment Guide — JobPilot

## Best free hosts for this project

| Host | Free tier | Notes |
|---|---|---|
| **Render** | 512 MB RAM, web service + cron jobs | Best balance; sleeps after inactivity |
| **PythonAnywhere** | 512 MB, always-on | Easy; web app only (no cron) |
| **Railway** | $5/mo credit | Quick deploy from GitHub |

---

## Option A: Render (Recommended)

### 1. Prepare production files

**`Procfile`** (project root):
```
web: gunicorn app.web.app:app --bind 0.0.0.0:$PORT --timeout 120
```

**`render.yaml`** (project root):
```yaml
services:
  - type: web
    name: jobpilot
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn app.web.app:app --bind 0.0.0.0:$PORT --timeout 120
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

### 2. Fix port binding for cloud

Edit `app/web/app.py` — update `start_web`:
```python
def start_web(host="0.0.0.0", port=None):
    port = port or int(os.environ.get("PORT", 5001))
    print(f"  [web] JobPilot dashboard at http://localhost:{port}")
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
```

### 3. Handle Word COM on Linux

`app/cv/render.py` uses `winreg` and Word COM — this fails on Linux. The code already has a reportlab fallback. Add a guard:
```python
import platform
IS_WINDOWS = platform.system() == "Windows"
```
Skip Word COM calls when `not IS_WINDOWS`.

### 4. Ensure persistent data directory

Render mounts `/opt/render/project/src/data` with the `disk` config above. Make sure your DB init uses an absolute or correctly relative path.

### 5. Push to GitHub

```bash
git add .
git commit -m "prepare for render deploy"
git push origin main
```

### 6. Deploy on Render

1. Go to **https://dashboard.render.com** → **New +** → **Build and deploy from a Git repo**
2. Connect your GitHub repo
3. Select the repo
4. Render auto-detects `render.yaml` — verify settings
5. Add **Environment Variables**:
   - `GEMINI_API_KEY` — your key(s)
   - `FACEBOOK_ACCESS_TOKEN` — (optional)
   - `GEMINI_MODEL` = `gemini-3-flash-preview`
6. Click **Create Web Service**
7. Wait for build (2-5 min)

Your app will be live at `https://jobpilot.onrender.com`.

---

## Option B: PythonAnywhere

### 1. Create a free account at https://www.pythonanywhere.com

### 2. Upload files

Use the **Files** tab or `git clone` in a Bash console.

### 3. Set up virtualenv

```bash
mkvirtualenv --python=/usr/bin/python3.11 jobpilot-env
pip install -r requirements.txt gunicorn
```

### 4. Create WSGI config

Go to **Web** tab → **WSGI configuration file** and replace contents with:
```python
import sys
path = '/home/yourusername/jobpilot'
if path not in sys.path:
    sys.path.insert(0, path)

from app.web.app import app as application
```

### 5. Set env vars

In the **Web** tab → **Environment**:
- `GEMINI_API_KEY` = your key
- `GEMINI_MODEL` = `gemini-3-flash-preview`
- `PORT` = `8080`

### 6. Set static files

Map `/static/` → `/home/yourusername/jobpilot/static/`

### 7. Reload

Click **Reload** in the Web tab.

---

## Option C: Railway

1. Go to https://railway.app → **New Project** → **Deploy from GitHub repo**
2. Select your repo
3. Railway auto-detects Python and deploys
4. Add **Variables** tab → add `GEMINI_API_KEY`, `GEMINI_MODEL`
5. Add a **Volume** (1 GB) mounted at `/app/data` for persistent SQLite DB

---

## Important notes

- **Background scans**: Render free tier sleeps after 15 min of inactivity. Use Render **Cron Jobs** (free tier allows them) to trigger `/api/scan` every few hours instead of in-process threads.
- **Word COM**: On Linux hosts, only the reportlab fallback works. It produces clean PDFs without Word formatting.
- **SQLite**: On Render/Railway, attach a disk/volume so `data/jobs.db` persists across deploys.
- **Free tier limits**: All hosts above are suitable for personal use. For heavier traffic, upgrade to paid tiers.
- **Security**: Change `SECRET_KEY` in production via environment variable.
