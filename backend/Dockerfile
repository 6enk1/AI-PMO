FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY pytest.ini ./
COPY tests ./tests

ENV DATABASE_URL=sqlite:////data/ai_pmo.db \
    UPLOAD_DIR=/data/uploads
RUN mkdir -p /data

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
