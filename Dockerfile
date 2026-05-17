FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV ENABLE_CRAWLER=0

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY . /app

WORKDIR /app/backend

CMD ["sh", "-c", "gunicorn main:app --bind 0.0.0.0:${PORT:-8001} --workers 1 --threads 8 --timeout 120"]
