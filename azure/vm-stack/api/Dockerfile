# FastAPI backend image for the VM (build context: a copy of the repo's app/, db/, events/ and
# requirements.txt — see azure/vm-stack/api/deploy.sh).
FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY db ./db
COPY events ./events
EXPOSE 8000
# Behind Caddy (TLS termination) — trust its X-Forwarded-* headers.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
