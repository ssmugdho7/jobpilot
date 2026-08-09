import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
CV_DIR = os.path.join(DATA_DIR, "cv")
CONFIG_DIR = os.path.join(BASE_DIR, "config")

for _d in (DATA_DIR, UPLOAD_DIR, CV_DIR):
    os.makedirs(_d, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "jobs.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"
