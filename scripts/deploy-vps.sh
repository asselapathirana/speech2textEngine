#!/bin/sh
set -eu

if [ "${FIELD_TRANSCRIBER_ALLOW_DEPLOY:-}" != "YES" ]; then
    echo "Deployment not started. Set FIELD_TRANSCRIBER_ALLOW_DEPLOY=YES after reviewing the target." >&2
    exit 2
fi

: "${FIELD_TRANSCRIBER_VPS_HOST:?missing VPS host}"
: "${FIELD_TRANSCRIBER_VPS_USER:=assela}"
: "${FIELD_TRANSCRIBER_VPS_CODE:=/home/assela/field-transcriber/code}"

repo_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
remote="${FIELD_TRANSCRIBER_VPS_USER}@${FIELD_TRANSCRIBER_VPS_HOST}"

ssh "$remote" "mkdir -p -- ${FIELD_TRANSCRIBER_VPS_CODE}"
rsync -az --delete-delay \
    --exclude '.git/' \
    --exclude '.ai-flow/' \
    --exclude '*.env' \
    --exclude 'config.env' \
    --exclude '*.mp3' \
    --exclude '*.mp4' \
    --exclude '*.wav' \
    --exclude '*.db*' \
    --exclude 'files/' \
    --exclude 'transcripts/' \
    -- "$repo_root/" "${remote}:${FIELD_TRANSCRIBER_VPS_CODE}/"

echo "Code deployed to ${remote}:${FIELD_TRANSCRIBER_VPS_CODE}; field files were excluded."
