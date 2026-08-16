#!/bin/sh
set -e

cd /app

python -c "from app.db import init_db; init_db(); print('DB initialized')"

exec gunicorn app.web.app:app \
    --bind 0.0.0.0:8080 \
    --timeout 120 \
    --workers 1 \
    --access-logfile - \
    --error-logfile -
