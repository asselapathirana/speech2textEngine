FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYANNOTE_METRICS_ENABLED=0

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY worker/requirements.txt /app/worker/requirements.txt
RUN python3 -m pip install --no-cache-dir --break-system-packages -r /app/worker/requirements.txt
COPY worker/ /app/worker/
RUN chmod 0755 /app/worker/entrypoint.sh

ENTRYPOINT ["/app/worker/entrypoint.sh"]
