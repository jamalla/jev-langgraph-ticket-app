# One image: FastAPI serves the API and the static frontend.
# Render sets PORT (default 10000); we must bind 0.0.0.0. https://render.com/docs/web-services
FROM python:3.12-slim

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/

WORKDIR /app/backend
EXPOSE 8000
# sh -c expands $PORT; exec lets uvicorn receive stop signals directly.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
