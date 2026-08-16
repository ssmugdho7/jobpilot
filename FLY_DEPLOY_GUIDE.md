# Deploy JobPilot on fly.io — macOS Step-by-Step Guide

This guide walks you through deploying the **JobPilot** Flask app on fly.io from macOS.

---

## Prerequisites

- **macOS** (any version with Homebrew or manual tool installation)
- **Git** (already installed on macOS)
- **GitHub** account with JobPilot repo
- **Google Gemini API key** (`GEMINI_API_KEY`)
- **fly.io account** (free tier available at https://fly.io)
- **Homebrew** (optional, for easy tool installation)

---

## Step 1: Install Flyctl CLI on macOS

The `flyctl` CLI is how you interact with fly.io.

### Option A: Using Homebrew (recommended)

```bash
brew install flyctl
```

Verify installation:
```bash
flyctl version
```

### Option B: Manual Installation

```bash
curl -L https://fly.io/install.sh | sh
```

Then add to your PATH. Open `~/.zshrc` (or `~/.bash_profile`) and add:
```bash
export PATH=$PATH:$HOME/.fly/bin
```

Reload your shell:
```bash
source ~/.zshrc
```

Verify:
```bash
flyctl version
```

---

## Step 2: Authenticate with fly.io

Sign up or log in at https://fly.io, then authenticate from terminal:

```bash
flyctl auth login
```

This opens a browser to create/confirm your fly.io account and generates an auth token locally.

Verify you're logged in:
```bash
flyctl auth whoami
```

---

## Step 3: Prepare Your Project

### 3.1 Ensure required files exist

Your project root should have:
- ✅ **`Procfile`** — already exists
- ✅ **`requirements.txt`** — already exists (includes `gunicorn>=21.0`)
- ✅ **`fly.toml`** — provided (see Step 3.2)

### 3.2 Use the provided fly.toml

A `fly.toml` file has been created in your project root. This configures:
- App name: `jobpilot`
- Region: `sea` (Seattle — change if needed)
- Persistent disk: `jobpilot_data` mounted at `/app/data`
- HTTP health checks
- Concurrency limits

**Customize the region** in `fly.toml` if needed. Common regions:
- `iad` — Northern Virginia (US)
- `lhr` — London (UK)
- `nrt` — Tokyo (Japan)
- `syd` — Sydney (Australia)
- `sea` — Seattle (US)

Find all regions:
```bash
flyctl platform regions
```

### 3.3 Create a `.env.example` file (if not present)

```bash
cat > .env.example << 'EOF'
GEMINI_API_KEY=your-google-ai-studio-key-here
GEMINI_API_KEYS=
GEMINI_MODEL=gemini-3-flash-preview
FACEBOOK_ACCESS_TOKEN=
SECRET_KEY=your-random-secret-key-here
EOF
```

---

## Step 4: Push Code to GitHub

Before deploying, ensure your latest code is on GitHub:

```bash
# From your project root
cd /Volumes/mySSD/python-projects/jobpilot

# Check status
git status

# Add all changes
git add .

# Commit
git commit -m "Add fly.io deployment configuration"

# Push to main
git push origin main
```

Verify on GitHub that `fly.toml` is now in the repo.

---

## Step 5: Create the fly.io App

### 5.1 Launch the fly.io app

```bash
flyctl launch
```

**You'll be prompted:**

1. **App name?** — Press Enter to accept `jobpilot` (from `fly.toml`)
2. **Choose a region?** — Press Enter to use `sea` (from `fly.toml`), or type a region code
3. **Create database now?** — Type **no** (JobPilot uses SQLite with persistent disk)
4. **Deploy now?** — Type **no** (we'll set env vars first)

**Output:**
```
Created app jobpilot in organization personal
Wrote config to /Volumes/mySSD/python-projects/jobpilot/fly.toml
```

### 5.2 Verify app was created

```bash
flyctl status
```

Expected output:
```
App
  Name     = jobpilot
  Owner    = your-username
  Hosting  = Dedicated
  Status   = pending
```

---

## Step 6: Set Environment Variables

Set required secrets in fly.io using the CLI:

```bash
# Core API key
flyctl secrets set GEMINI_API_KEY="your-actual-gemini-api-key-here"

# Optional: if you have multiple keys for quota rotation
flyctl secrets set GEMINI_API_KEYS="key1,key2,key3"

# Flask session secret (generate a random string)
flyctl secrets set SECRET_KEY="$(openssl rand -hex 32)"

# Optional: Facebook token (if you have one)
# flyctl secrets set FACEBOOK_ACCESS_TOKEN="your-token"
```

Verify secrets were set:
```bash
flyctl secrets list
```

You should see:
```
NAME                       DIGEST              CREATED AT
FACEBOOK_ACCESS_TOKEN      ...                 3 hours ago
GEMINI_API_KEY             ...                 3 hours ago
GEMINI_API_KEYS            ...                 3 hours ago
SECRET_KEY                 ...                 3 hours ago
```

---

## Step 7: Create Persistent Storage (Volume)

JobPilot stores the SQLite database and CV files on disk. Create a persistent volume:

```bash
flyctl volumes create jobpilot_data --size 10
```

**Output:**
```
        ID: vol_abc123def456
      Name: jobpilot_data
       App: jobpilot
    Region: sea
      Size: 10 GB
   Created: now
```

Verify:
```bash
flyctl volumes list
```

---

## Step 8: Deploy the App

### 8.1 Deploy to fly.io

```bash
flyctl deploy
```

**What happens:**
1. flyctl reads `fly.toml` and `Procfile`
2. Builds the app using Heroku buildpacks (detects Python)
3. Installs Python + dependencies from `requirements.txt`
4. Attaches the persistent volume
5. Deploys the app to fly.io

**Expected output (last few lines):**
```
Monitoring Deployment of jobpilot
  Updating [app] status as Running
  Updating [app] status as Passing
  
Visit your newly deployed app at: https://jobpilot.fly.dev
```

### 8.2 Verify the deployment

```bash
flyctl status
```

You should see:
```
App
  Name     = jobpilot
  Owner    = your-username
  Status   = running
  Machines = 1 (1 running)

Recent Events
STATUS      TYPE         MESSAGE
Running     Deployment   Deployment complete
```

### 8.3 View logs

```bash
flyctl logs
```

Look for:
```
app[...]: * Running on http://0.0.0.0:8080
```

---

## Step 9: Test Your Deployment

### 9.1 Visit the app in browser

```bash
flyctl open
```

Or manually visit: https://jobpilot.fly.dev

You should see the JobPilot home page.

### 9.2 Test key endpoints

- **Home:** https://jobpilot.fly.dev/
- **Profile upload:** https://jobpilot.fly.dev/profile
- **API scan:** https://jobpilot.fly.dev/api/scan (POST request)

Test the profile page:
```bash
curl https://jobpilot.fly.dev/profile
```

---

## Step 10: Set Up Background Job Scanning

By default, the Flask app runs in the foreground. For recurring job scans, create a fly.io Machine to run periodic scans.

### Option A: Use fly.io's Background Workers (Recommended for Free Tier)

Create a **scheduled task** using fly.io's HTTP POST to trigger `/api/scan`:

```bash
# Later — after confirming the web app works
# You can add a cron job machine (requires paid account or workaround)
```

### Option B: Deploy a Separate "Scan Worker" Machine (Advanced)

Create a second machine that runs `python main.py --once` on a schedule. This requires:

1. A separate `fly.toml` config for the worker
2. Running the worker periodically via GitHub Actions or a cron service

**For now**, rely on the web dashboard's manual "Scan BDJobs / LinkedIn now" button.

---

## Step 11: View Logs and Metrics

### Monitor app logs (real-time)

```bash
flyctl logs -n 50  # Last 50 log lines
flyctl logs        # Stream live logs (Ctrl+C to exit)
```

### View deployment history

```bash
flyctl releases
```

### SSH into the running machine (for debugging)

```bash
flyctl ssh console
# Inside the machine:
ls -la /app/data  # Check persistent volume
cat /app/data/jobs.db  # Inspect database
exit
```

---

## Step 12: Update Environment Variables or Code

### Update an env var or secret

```bash
flyctl secrets set GEMINI_API_KEY="your-new-key"
```

The app will auto-restart.

### Deploy code changes

After pushing to GitHub:

```bash
flyctl deploy
```

---

## Troubleshooting

### App won't start: "Permission denied" or "Address already in use"

**Cause:** Port binding issue.

**Fix:** Ensure `app/web/app.py` reads the `PORT` env var:
```python
def start_web(host="0.0.0.0", port=None):
    port = port or int(os.environ.get("PORT", 5001))
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
```

Redeploy:
```bash
flyctl deploy --now
```

### "Health check failing" or continuous restarts

**Cause:** App crashes or doesn't respond to HTTP requests.

**Fix:** Check logs:
```bash
flyctl logs
```

Common issues:
- Missing `GEMINI_API_KEY` — set it via `flyctl secrets set`
- Database corrupted — SSH in and delete `data/jobs.db`, it will be recreated on next scan
- Import error — verify `requirements.txt` has all dependencies

### Persistent volume not mounted

**Cause:** Volume created but app not using it.

**Fix:** Verify `fly.toml` has:
```toml
[[mounts]]
  source = "jobpilot_data"
  destination = "/app/data"
```

Then redeploy:
```bash
flyctl deploy --now
```

### PDF generation failing (Word COM not available)

**Expected on Linux/fly.io.** JobPilot falls back to reportlab (clean PDFs).

Verify in `app/cv/render.py`:
```python
if os.name != "nt":
    _WORD_AVAILABLE = False
```

This is correct — no action needed.

---

## Cost Estimate (fly.io Free Tier)

- **Compute:** 3 shared-cpu-1x 256MB VMs = **free** (up to 3)
- **Persistent storage:** First 10 GB = **free**
- **Bandwidth:** First 160 GB/month = **free**

**Estimated monthly cost:** $0 (if under free tier limits)

Paid tiers start at **$5–$15/month** for dedicated machines.

---

## Summary

You now have JobPilot running on fly.io! 

**Quick reference:**

```bash
# Check app status
flyctl status

# View logs
flyctl logs

# Open in browser
flyctl open

# Deploy code changes
flyctl deploy

# Set/update secrets
flyctl secrets set KEY=value

# SSH into machine
flyctl ssh console
```

**Next steps:**
1. Upload your CV on `/profile`
2. Click "Scan BDJobs / LinkedIn now" on `/`
3. Generate ATS CVs for interesting jobs
4. Prepare Gmail drafts and apply!

---

## Additional Resources

- **fly.io Docs:** https://fly.io/docs/
- **Python on fly.io:** https://fly.io/docs/languages-and-frameworks/python/
- **Persistent Storage:** https://fly.io/docs/reference/volumes/
- **Secrets Management:** https://fly.io/docs/reference/secrets/
