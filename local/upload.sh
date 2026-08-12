#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: local/upload.sh SOURCE_MP3" >&2
    exit 2
fi

source_path=$1
config_path=${FIELD_TRANSCRIBER_UPLOAD_CONFIG:-"$(dirname "$0")/config.env"}
if [ ! -f "$config_path" ]; then
    echo "configuration file not found: $config_path" >&2
    exit 2
fi

set -a
. "$config_path"
set +a

: "${FIELD_TRANSCRIBER_VPS_HOST:?missing VPS host}"
: "${FIELD_TRANSCRIBER_VPS_USER:?missing VPS user}"
: "${FIELD_TRANSCRIBER_VPS_CODE:?missing VPS code path}"
: "${FIELD_TRANSCRIBER_VPS_FILES:?missing VPS files path}"
: "${FIELD_TRANSCRIBER_VPS_PYTHON:=python3}"

if [ ! -f "$source_path" ]; then
    echo "source recording not found: $source_path" >&2
    exit 2
fi

name=$(basename "$source_path")
case "$name" in
    *[!A-Za-z0-9._-]*|*.mp3.mp3) echo "source name must use only letters, digits, dot, underscore, or hyphen" >&2; exit 2 ;;
esac
case "$name" in
    *.mp3|*.MP3) ;;
    *) echo "source must have an MP3 extension" >&2; exit 2 ;;
esac

size=$(wc -c < "$source_path" | tr -d ' ')
digest=$(sha256sum "$source_path" | cut -d ' ' -f 1)
remote="${FIELD_TRANSCRIBER_VPS_USER}@${FIELD_TRANSCRIBER_VPS_HOST}"
staged="${name}.partial"

rsync --partial --append-verify -- "$source_path" "${remote}:${FIELD_TRANSCRIBER_VPS_FILES}/uploading/${staged}"
ssh "$remote" "cd ${FIELD_TRANSCRIBER_VPS_CODE} && ${FIELD_TRANSCRIBER_VPS_PYTHON} -m field_transcriber --config config.env publish-upload --staged-name ${staged} --original-name ${name} --size ${size} --sha256 ${digest} --json"
