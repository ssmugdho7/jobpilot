import sys, os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\Coding is FUN\ai-tool")
os.chdir(r"E:\Coding is FUN\ai-tool")
from app.sources import fetch_careers
from app.filter import detect_role, is_relevant
from app.pipeline import _clean_job

jobs = fetch_careers()
print(f"Raw career jobs: {len(jobs)}")
for j in jobs:
    cleaned = _clean_job(j)
    role = detect_role(j)
    rel = is_relevant(j)
    print(f"  {j['source_site']:20} | title={j['title'][:45]:45} | loc={j['location'][:30]:30} | role={cleaned['role']!r:30} rel={rel}")