import sys, os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\Coding is FUN\ai-tool")
os.chdir(r"E:\Coding is FUN\ai-tool")
from app.web.app import app
app.testing = True
c = app.test_client()
# Test default (1 day) filter
r = c.get("/")
data = r.get_data(as_text=True)
idx = data.find('<div class="pagination">')
if idx >= 0:
    print("Pagination FOUND with default 1-day filter")
    print(data[idx:idx+500])
else:
    print("Pagination NOT found with default 1-day filter")
    # Count jobs shown
    job_count = data.count('<div class="job"')
    print(f"Jobs shown on page: {job_count}")