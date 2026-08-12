#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
image=${FIELD_TRANSCRIBER_WORKER_IMAGE:-field-transcriber-worker:local}

if [ "${FIELD_TRANSCRIBER_ALLOW_DOCKER_BUILD:-}" != "YES" ]; then
    echo "Worker build not started. Set FIELD_TRANSCRIBER_ALLOW_DOCKER_BUILD=YES after approving dependency/image downloads." >&2
    exit 2
fi

cd "$repo_root"
docker build -f worker/Dockerfile -t "$image" .

if docker history --no-trunc "$image" | grep -Eiq '(hf_[A-Za-z0-9]+|private[_ -]?key|password=|token=)'; then
    echo "Potential credential material found in worker image history" >&2
    exit 1
fi

if docker run --rm --entrypoint sh "$image" -c "find /app -type f \( -iname '*.mp3' -o -iname '*.wav' -o -iname '*.srt' -o -iname 'config.env' \) -print" | grep -q .; then
    echo "Field data or runtime configuration found in worker image" >&2
    exit 1
fi

docker run --rm --gpus all --entrypoint python3 "$image" -c "import torch; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))"
echo "Worker image smoke and content inspection passed: $image"
