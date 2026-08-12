#!/bin/sh
set -eu

export PYANNOTE_METRICS_ENABLED=0
if [ "${1:-}" = "serverless" ]; then
    shift
    exec python3 -m worker.serverless "$@"
fi
exec python3 -m worker.transcribe "$@"
