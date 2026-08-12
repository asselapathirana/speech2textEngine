#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$repo_root"
exec /home/assela/python/.venv/bin/python -m unittest tests.test_recordings tests.test_upload_script -v
