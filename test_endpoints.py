import sys, os
sys.path.insert(0, r"E:\Coding is FUN\ai-tool")

from app.web.app import app
from app.db import init_db, SessionLocal, User
from werkzeug.security import generate_password_hash

init_db()

# Create test user directly
s = SessionLocal()
s.query(User).filter_by(username="testuser").delete()
s.add(User(username="testuser", password_hash=generate_password_hash("password123")))
s.commit()
s.close()

app.testing = True
c = app.test_client()

# Login
c.post("/login", data={"username": "testuser", "password": "password123"}, follow_redirects=True)

results = []

def check(name, cond, extra=""):
    results.append((name, bool(cond), extra))
    print(f"  {'PASS' if cond else 'FAIL'} {name}")

# --- 1. Pages ---
r = c.get("/")
check("GET /", r.status_code == 200 and b"JobPilot" in r.data, f"status={r.status_code}")
r = c.get("/profile")
check("GET /profile", r.status_code == 200, f"status={r.status_code}")

# --- 2. Profile API ---
r = c.get("/api/profile")
d = r.get_json()
check("GET /api/profile", r.status_code == 200 and "skills" in d, f"keys={list(d.keys())[:5]}")

# --- 3. Save profile ---
payload = {
    "name": "Test User", "email": "test@example.com", "phone": "+880111",
    "linkedin": "https://linkedin.com/in/test", "github": "https://github.com/test",
    "portfolio": "", "summary": "Experienced software engineer.",
    "education": "B.Sc. CSE", "experience": "Dev at Co.",
    "skills": ["Python", "Flask", "React"],
}
r = c.post("/api/profile", json=payload)
d = r.get_json()
check("POST /api/profile", r.status_code == 200 and d.get("ok") and d["profile"]["name"] == "Test User")

# --- 4. Jobs list + status ---
from app.db import SessionLocal, Job
s = SessionLocal()
job = s.query(Job).first()
job_id = job.id
s.close()
check("jobs exist in DB", job_id is not None)

r = c.post(f"/api/jobs/{job_id}/status", json={"status": "applied"})
check("POST status -> applied", r.status_code == 200 and r.get_json().get("status") == "applied")
r = c.post(f"/api/jobs/{job_id}/status", json={"status": "invalid"})
check("POST status invalid", r.status_code == 400)
c.post(f"/api/jobs/{job_id}/status", json={"status": "new"})

# --- 5. Scan endpoint ---
print("  [scan] starting background scan...")
r = c.post("/api/scan")
d = r.get_json()
check("POST /api/scan (async start)", r.status_code == 200 and d.get("started"))
import time
time.sleep(2)
r2 = c.post("/api/scan")
d2 = r2.get_json()
check("POST /api/scan (already running -> 202)", r2.status_code in (200, 202) and d2.get("started") is False)

# --- 6. Auth: logout + unauthenticated access ---
c.get("/logout")
r = c.get("/")
check("GET / unauthenticated -> redirect to login", r.status_code == 302 and "/login" in r.headers.get("Location", ""))
r = c.get("/profile")
check("GET /profile unauthenticated -> redirect", r.status_code == 302)

# Re-login for cleanup
c.post("/login", data={"username": "testuser", "password": "password123"}, follow_redirects=True)

print("\n" + "=" * 60)
passed = sum(1 for _, ok, _ in results if ok)
for name, ok, extra in results:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({extra})" if (extra and not ok) else ""))
print("=" * 60)
print(f"TOTAL: {passed}/{len(results)} passed")
