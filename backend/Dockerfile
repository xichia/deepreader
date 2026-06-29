FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEEPREADER_DATABASE_URL=sqlite:////app/data/deepreader.sqlite3 \
    DEEPREADER_CORS_ORIGINS=http://127.0.0.1:5173,http://localhost:5173

WORKDIR /app

COPY backend/pyproject.toml ./pyproject.toml
COPY backend/src ./src

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -e .

RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "deepreader.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
