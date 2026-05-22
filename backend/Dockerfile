FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY app /app/app
COPY data /app/data
COPY scripts /app/scripts

RUN test -f /app/data/imports/samples/cpu_sample.json \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[image]"

EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
