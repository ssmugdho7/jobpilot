import sys, os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\Coding is FUN\ai-tool")
os.chdir(r"E:\Coding is FUN\ai-tool")
from app.web.app import app
app.testing = True
c = app.test_client()
r = c.get("/?days=30")
print("Status:", r.status_code)
data = r.get_data(as_text=True)
if "pagination" in data.lower() or "Page" in data:
    print("Pagination found in HTML!")
else:
    print("Pagination NOT found in HTML")
    if 'id="jobs"' in data:
        print("Jobs div found")
    else:
        print("Jobs div NOT found")