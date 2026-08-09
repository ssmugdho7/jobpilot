import sys, os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\Coding is FUN\ai-tool")
os.chdir(r"E:\Coding is FUN\ai-tool")
from app.web.app import app
app.testing = True
c = app.test_client()
r = c.get("/?days=30")
data = r.get_data(as_text=True)
idx = data.find('<div class="pagination">')
if idx >= 0:
    print(data[idx:idx+1200])
else:
    print("Pagination div NOT found in body")
    idx2 = data.find("total_pages")
    if idx2 >= 0:
        print(data[max(0,idx2-100):idx2+100])