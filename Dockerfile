# Cycle 19 (D-052): scoring-service image. Runnable the day a Docker daemon exists.
FROM python:3.12-slim

WORKDIR /app

# deps first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY finguard/ ./finguard/
COPY data/model_v0.pkl ./data/model_v0.pkl

# operational config comes from the environment (see DEPLOYMENT.md); no secrets baked in
ENV FINGUARD_HOST=0.0.0.0 \
    FINGUARD_PORT=8100 \
    FINGUARD_LOG_LEVEL=info

EXPOSE 8100

# container healthcheck hits the readiness probe
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8100/ready').status==200 else 1)"

CMD ["python", "-m", "finguard.scoring"]
