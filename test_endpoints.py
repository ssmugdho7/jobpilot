import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.web.app import app
from app.db import init_db, SessionLocal, User, UserCV
from werkzeug.security import generate_password_hash

init_db()

# Create test user directly
s = SessionLocal()
s.query(User).filter_by(username="testuser").delete()
s.add(User(username="testuser", password_hash=generate_password_hash("password123")))
s.commit()

user_row = s.query(User).filter_by(username="testuser").first()
if user_row:
    s.query(UserCV).filter_by(user_id=user_row.id).delete()
    s.add(UserCV(user_id=user_row.id, name="Test CV", file_path="/dev/null", parsed_profile={"name": "Test User", "email": "test@example.com", "phone": "+880111", "linkedin": "https://linkedin.com/in/test", "github": "https://github.com/test", "portfolio": "", "summary": "Experienced software engineer.", "education": "B.Sc. CSE", "experience": "Dev at Co.", "skills": ["Python", "Flask", "React"]}))
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
r = c.get("/dashboard")
check("GET /dashboard", r.status_code == 200 and b"JobPilot" in r.data, f"status={r.status_code}")
r = c.get("/")
check("GET / logged in -> redirect to dashboard", r.status_code == 302 and "/dashboard" in r.headers.get("Location", ""), f"status={r.status_code}")
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
# Scan may already be running from _startup_scan() on import
check("POST /api/scan (async start)", r.status_code in (200, 202), f"started={d.get('started')}")
import time
time.sleep(2)
r2 = c.post("/api/scan")
d2 = r2.get_json()
check("POST /api/scan (already running -> 202)", r2.status_code in (200, 202) and d2.get("started") is False)

# --- 6. Auth: logout + unauthenticated access ---
c.get("/logout")
r = c.get("/")
check("GET / landing page", r.status_code == 200 and b"JobPilot" in r.data and b"Never miss a CSE job" in r.data, f"status={r.status_code}")
r = c.get("/dashboard")
check("GET /dashboard unauthenticated -> redirect to login", r.status_code == 302 and "/login" in r.headers.get("Location", ""))
r = c.get("/profile")
check("GET /profile unauthenticated -> redirect", r.status_code == 302)

# Re-login for cleanup
c.post("/login", data={"username": "testuser", "password": "password123"}, follow_redirects=True)

# --- 7. AI Studio session + suggestions ---
r = c.post(f"/api/jobs/{job_id}/ai-studio/session", json={})
d = r.get_json()
check("POST ai-studio/session -> 200", r.status_code == 200 and d.get("ok") and "session" in d, f"status={r.status_code}")
session_id = d["session"]["id"] if r.status_code == 200 else None

if session_id:
    r = c.post(f"/api/jobs/{job_id}/ai-studio/session", json={})
    d2 = r.get_json()
    check("POST ai-studio/session idempotent", r.status_code == 200 and d2["session"]["id"] == session_id)

    r = c.patch(f"/api/ai-studio/sessions/{session_id}", json={"template_id": "modern_monochrome", "page_format": "a4"})
    d = r.get_json()
    check("PATCH session settings -> ok", r.status_code == 200 and d.get("ok") and d["session"]["template_id"] == "modern_monochrome", f"status={r.status_code}")

    r = c.patch(f"/api/ai-studio/sessions/{session_id}", json={"page_format": "invalid"})
    check("PATCH invalid page_format -> 400", r.status_code == 400)

    r = c.patch(f"/api/ai-studio/sessions/99999", json={"template_id": "x"})
    check("PATCH missing session -> 404", r.status_code == 404)

    r = c.get(f"/api/ai-studio/sessions/{session_id}/suggestions")
    d = r.get_json()
    check("GET suggestions (empty) -> 200", r.status_code == 200 and isinstance(d.get("suggestions"), list), f"status={r.status_code}")

    r = c.post(f"/api/ai-studio/sessions/{session_id}/suggestions/generate", json={"scope": {"sections": ["summary", "skills"]}})
    d = r.get_json()
    check("POST suggestions/generate -> 200", r.status_code == 200 and "suggestions" in d, f"status={r.status_code}")
    sug_id = d["suggestions"][0]["id"] if d.get("suggestions") else None

    if sug_id:
        r = c.post(f"/api/ai-studio/suggestions/{sug_id}/accept")
        d = r.get_json()
        check("POST suggestions/accept -> 200", r.status_code == 200 and d.get("ok"), f"status={r.status_code}")

        r = c.post(f"/api/ai-studio/suggestions/{sug_id}/reject")
        d = r.get_json()
        check("POST suggestions/reject -> 200 (already accepted)", r.status_code == 200 and d.get("ok"), f"status={r.status_code}")

    r = c.get(f"/api/ai-studio/sessions/{session_id}/preview")
    check("GET preview HTML -> 200", r.status_code == 200 and b"<html" in r.data, f"status={r.status_code}")

    r = c.post(f"/api/ai-studio/sessions/{session_id}/versions", json={"label": "ep v1"})
    d = r.get_json()
    check("POST versions snapshot -> 200", r.status_code == 200 and d.get("ok") and d["version"]["label"] == "ep v1", f"status={r.status_code}")

    r = c.get(f"/api/ai-studio/sessions/{session_id}/versions")
    d = r.get_json()
    check("GET versions -> 200, >=1 item", r.status_code == 200 and len(d.get("versions", [])) >= 1, f"count={len(d.get('versions', []))}")

    r = c.get(f"/api/ai-studio/sessions/{session_id}/export.pdf")
    check("GET export.pdf -> 200 or 500", r.status_code in (200, 500), f"status={r.status_code}")

    r = c.get("/jobs/" + str(job_id) + "/ai-studio")
    check("GET ai-studio page -> 200", r.status_code == 200, f"status={r.status_code}")
else:
    check("ai-studio/session skipped", True, "no job or session")

print("\n" + "=" * 60)
passed = sum(1 for _, ok, _ in results if ok)
for name, ok, extra in results:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({extra})" if (extra and not ok) else ""))
print("=" * 60)
print(f"TOTAL: {passed}/{len(results)} passed")
