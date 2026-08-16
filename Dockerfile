FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080

EXPOSE 8080

CMD ["gunicorn", "app.web.app:app", "--bind", "0.0.0.0:8080", "--timeout", "120", "--workers", "1"]