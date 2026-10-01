# Build from the repo root:  docker compose up --build
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    FINSIGHT_SHARED_DIR=/app/shared FINSIGHT_MODELS_DIR=/app/models
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/pyproject.toml ./
COPY backend/finsight_api ./finsight_api
RUN pip install --no-cache-dir --no-deps .
COPY shared ./shared
COPY backend/models ./models
RUN useradd --create-home finsight
USER finsight
EXPOSE 8443
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,ssl; urllib.request.urlopen('https://127.0.0.1:8443/healthz', context=ssl._create_unverified_context())" || exit 1
CMD ["python", "-m", "finsight_api"]
