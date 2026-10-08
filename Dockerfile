FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libsndfile1 sox libsox-fmt-all gosu ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 locutor && useradd -u 10001 -g locutor -m locutor
WORKDIR /app
COPY deploy/debian_cpu/requirements-linux.lock /app/requirements-linux.lock
RUN pip install --require-hashes -r requirements-linux.lock --extra-index-url https://download.pytorch.org/whl/cpu
COPY pyproject.toml README.md /app/
COPY app /app/app
COPY scripts /app/scripts
COPY config /app/config
COPY samples /app/samples
COPY tests /app/tests
COPY deploy/easypanel /app/deploy/easypanel
RUN pip install --no-deps . && chmod +x /app/deploy/easypanel/entrypoint.sh
ENV PERSONAL_VOICE_ENABLED=true PERSONAL_VOICE_DEFAULT=true PERSONAL_VOICE_BACKEND=torch_cpu \
    PERSONAL_VOICE_MODEL=/models/qwen-base PERSONAL_VOICE_REFERENCE=/voice/referencia_13s.wav \
    PERSONAL_VOICE_TRANSCRIPT=/voice/referencia_13s.txt VOICES_CONFIG=/app/config/personal-only.yaml \
    DB_URL=sqlite:////data/locutor.db WORK_DIR=/data/jobs HF_HOME=/models/hf-cache \
    HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 COOKIE_SECURE=true TRUST_PROXY=false \
    NUM_THREADS=4 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 CONCURRENCY=1 MAX_CONCURRENT_JOBS=1 \
    MAX_INPUT_CHARS=3000 CHUNK_MAX_CHARS=400 PER_CHUNK_TIMEOUT_S=1800 \
    DEFAULT_SPEED=0.9 DEFAULT_MUSIC=calma SILENCE_MS=350 MP3_BITRATE=192k
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30m --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4)"
ENTRYPOINT ["/app/deploy/easypanel/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
