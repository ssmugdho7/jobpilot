import sys, os, io
sys.path.insert(0, r"E:\Coding is FUN\ai-tool")

from app.web.app import app
from app.db import init_db, SessionLocal, User
from werkzeug.security import generate_password_hash

init_db()

# Create test user in DB directly or via register
s = SessionLocal()
s.query(User).filter_by(username="testuser").delete()
s.add(User(username="testuser", password_hash=generate_password_hash("password123")))
s.commit()
s.close()

app.testing = True
c = app.test_client()

# Login test user
resp = c.post("/login", data={"username": "testuser", "password": "password123"}, follow_redirects=True)

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

# --- 4. CV upload: DOCX ---
with open(r"E:\Coding is FUN\ai-tool\data\uploads\test_cv.docx", "rb") as f:
    r = c.post("/api/cv/upload", data={"cv": (f, "test_cv.docx")}, content_type="multipart/form-data")
d = r.get_json()
check("POST /api/cv/upload (docx)", r.status_code == 200 and d.get("parsed"), f"name={d.get('profile',{}).get('name')}")

# --- 5. CV upload: PDF ---
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
pdf_buf = io.BytesIO()
pc = canvas.Canvas(pdf_buf, pagesize=letter)
pc.drawString(72, 720, "Alex Johnson")
pc.drawString(72, 700, "Email: alex@example.com Phone: +44-700000000")
pc.drawString(72, 680, "Summary: Data engineer with Python and SQL.")
pc.drawString(72, 650, "Skills: Python, SQL, Airflow, Docker, AWS")
pc.save()
pdf_buf.seek(0)
r = c.post("/api/cv/upload", data={"cv": (pdf_buf, "alex.pdf")}, content_type="multipart/form-data")
d = r.get_json()
ok_pdf = r.status_code == 200 and d.get("parsed") and d["profile"].get("name")
check("POST /api/cv/upload (pdf)", ok_pdf, f"name={d.get('profile',{}).get('name')} skills={len(d.get('profile',{}).get('skills',[]))}")

# restore DOCX profile
with open(r"E:\Coding is FUN\ai-tool\data\uploads\test_cv.docx", "rb") as f:
    c.post("/api/cv/upload", data={"cv": (f, "test_cv.docx")}, content_type="multipart/form-data")

# --- 6. Bad uploads ---
r = c.post("/api/cv/upload", data={}, content_type="multipart/form-data")
check("POST /api/cv/upload (no file)", r.status_code == 400)
r = c.post("/api/cv/upload", data={"cv": (io.BytesIO(b"not a cv"), "bad.txt")}, content_type="multipart/form-data")
check("POST /api/cv/upload (bad ext)", r.status_code == 400)

# --- 7. Jobs list + status ---
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

# --- 8. Manual add + duplicate ---
murl = "https://www.linkedin.com/jobs/view/endpoint-test-999"
mtext = "DevOps Engineer at ExampleCorp, Kubernetes Docker. Email: hiring@examplecorp.com"
r = c.post("/api/jobs/manual", json={"url": murl, "text": mtext})
d = r.get_json()
check("POST /api/jobs/manual", r.status_code == 200 and d.get("ok"), f"gmail_to={d.get('gmail_link','').split('to=')[-1][:20]}")
manual_id = d.get("id")
r = c.post("/api/jobs/manual", json={"url": murl, "text": mtext})
check("manual duplicate -> 409", r.status_code == 409)
r = c.post("/api/jobs/manual", json={})
check("manual no payload -> 400", r.status_code == 400)

# --- 9. ATS CV generation + downloads ---
r = c.get(f"/api/jobs/{job_id}/cv")
d = r.get_json()
check("GET /api/jobs/<id>/cv", r.status_code == 200 and d.get("ok"), f"err={d.get('error')}")
check("  returns docx/pdf urls", d.get("ok") and d.get("docx_url") and d.get("pdf_url"))
check("  ATS tailored summary non-empty", d.get("ok") and bool(d.get("summary")))

r = c.get(f"/api/jobs/{job_id}/cv.docx")
check("GET cv.docx", r.status_code == 200 and b"PK" in r.data[:2], f"bytes={len(r.data)}")
r = c.get(f"/api/jobs/{job_id}/cv.pdf")
check("GET cv.pdf", r.status_code == 200 and r.data[:4] == b"%PDF", f"bytes={len(r.data)}")

r = c.get("/api/jobs/999999/cv")
check("cv for missing job -> 404", r.status_code == 404)

# --- 10. Scan endpoint (async now — returns immediately, scan runs in background) ---
print("  [scan] starting background scan...")
r = c.post("/api/scan")
d = r.get_json()
check("POST /api/scan (async start)", r.status_code == 200 and d.get("started"))
import time
time.sleep(2)
r2 = c.post("/api/scan")
d2 = r2.get_json()
check("POST /api/scan (already running -> 202)", r2.status_code in (200, 202) and d2.get("started") is False)

# --- cleanup manual test job ---
s = SessionLocal()
s.query(Job).filter_by(source_site="www.linkedin.com").delete()
s.commit()
s.close()

print("\n" + "=" * 60)
passed = sum(1 for _, ok, _ in results if ok)
for name, ok, extra in results:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({extra})" if (extra and not ok) else ""))
print("=" * 60)
print(f"TOTAL: {passed}/{len(results)} passed")
