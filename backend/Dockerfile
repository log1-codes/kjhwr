# backend/Dockerfile
# Designed for build context "./backend":
#   docker build -t wind-backend:latest -f backend/Dockerfile backend/
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first for efficient layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application source code and pre-cached market data
COPY app/ ./backend/app/
COPY data/ /app/data/

# Environment variables
ENV PYTHONPATH=/app
ENV DATA_DIR=/app/data
ENV PORT=8000

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
