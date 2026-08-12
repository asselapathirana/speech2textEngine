#!/bin/sh
set -eu

export PYANNOTE_METRICS_ENABLED=0
exec python3 -m worker.transcribe "$@"
