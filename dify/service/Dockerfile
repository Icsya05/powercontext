# Memory service for the Midnight Convenience Store Dify workflow.
# Build context is the repository root so that the `dify.service` package
# layout is preserved:  docker build -f dify/service/Dockerfile .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /workspace

COPY dify/service/requirements.txt /workspace/dify/service/requirements.txt
RUN pip install --no-cache-dir -r /workspace/dify/service/requirements.txt

COPY dify /workspace/dify

EXPOSE 8077

CMD ["uvicorn", "dify.service.app:app", "--host", "0.0.0.0", "--port", "8077"]
