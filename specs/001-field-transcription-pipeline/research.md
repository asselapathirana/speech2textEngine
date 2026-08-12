# Research: Field Audio Transcription Pipeline

## Worker transcription stack

**Decision**: Use a stable, pinned WhisperX release as the worker's single speech
pipeline. Configure `large-v3`, CUDA `float16`, VAD, forced word alignment, and
speaker assignment through the current pyannote community diarization model.

**Rationale**: WhisperX already uses faster-whisper as its backend and exposes the
required alignment and speaker-assignment stages in one supported flow. Its current
documentation describes VAD, word alignment, diarization, GPU `float16`, and
language-specific alignment behavior. This avoids maintaining parallel integration
code around faster-whisper and WhisperX. See the official
[WhisperX repository](https://github.com/m-bain/whisperX) and
[faster-whisper repository](https://github.com/SYSTRAN/faster-whisper).

**Alternatives considered**:

- Direct faster-whisper plus custom alignment and speaker assignment: more control,
  but duplicates behavior WhisperX already provides.
- Whisper CLI alone: does not satisfy aligned word timestamps and diarization.

## Diarization model and access

**Decision**: Use `pyannote/speaker-diarization-community-1` locally on the rented
worker. Require the owner to accept its model terms and supply a read-only Hugging
Face token at runtime. Disable optional telemetry for field processing.

**Rationale**: `community-1` is the current open self-hosted pipeline documented by
pyannote, supports local GPU execution, and provides regular and exclusive speaker
diarization. The official instructions require accepted user conditions, FFmpeg,
and a Hugging Face token. Telemetry control is documented and should be disabled
because field audio metadata need not leave the worker. See the official
[pyannote.audio repository](https://github.com/pyannote/pyannote-audio).

**Alternatives considered**:

- pyannote premium hosted diarization: sends processing outside the disposable
  worker and adds service cost and another data boundary.
- Legacy `speaker-diarization-3.1`: superseded by the current community pipeline.

## CUDA and container baseline

**Decision**: Pin the worker image and Python dependencies together after a build
compatibility check, use Python 3.11, and require a worker with a compatible NVIDIA
driver, Docker, and NVIDIA Container Toolkit. Do not install host CUDA libraries
from the controller.

**Rationale**: Current WhisperX documentation identifies CUDA 12.8 for GPU use,
while NVIDIA documents that the host driver/runtime must be compatible with the
container and that Docker exposes GPUs through the NVIDIA runtime. Keeping CUDA
user-space dependencies inside the image makes disposable workers repeatable. See
[WhisperX setup](https://github.com/m-bain/whisperX#setup-) and the
[NVIDIA Container Toolkit guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html).

**Alternatives considered**:

- Install the Python stack directly on each worker: slower and less repeatable.
- Build around a provider-specific GPU image: would couple the initial pipeline to
  one rental vendor.

## VPS controller dependency policy

**Decision**: Implement the VPS controller with Python 3.11 standard-library
modules (`sqlite3`, `subprocess`, `hashlib`, `json`, `pathlib`, `argparse`) and
existing OpenSSH/rsync commands. Keep the JSON Schema as a documentary and test
fixture contract; implement matching runtime structure/content checks directly in
the controller without the third-party `jsonschema` package.

**Rationale**: The controller needs transactional local state and process
orchestration, not a service framework. Standard-library Python minimizes VPS
setup and fits the owner's lightweight quality target.

**Alternatives considered**:

- SQLAlchemy: unnecessary for a small fixed SQLite schema.
- `jsonschema`: capable, but would make a third-party package mandatory on the VPS
  for a small fixed document shape that direct checks can cover.
- Celery/Redis or a web service: additional deployment and recovery surfaces with
  no value for one operator and one active job.

## Claim renewal during remote processing

**Decision**: Run the remote worker as a pollable subprocess, renewing the SQLite
claim every 60 seconds against a configurable five-minute lease. Refuse results and
attempt remote termination if renewal fails or ownership changes.

**Rationale**: A transcription can exceed any short fixed lease. Renewal in the
same controller loop keeps a healthy paid run owned without adding a daemon or
background service, while token-guarded updates prevent split-brain completion.

**Alternatives considered**:

- Renew only between steps: transcription can outlive the lease.
- Set one very long lease: delays genuine crash recovery and still assumes an
  uncertain maximum recording duration.
- Separate heartbeat service: unnecessary infrastructure for one active job.

## Empty and speechless output

**Decision**: Require at least one segment containing non-whitespace transcript
text before completion. Require Markdown to contain a rendered segment and SRT to
contain a timed cue. Classify zero-segment/textless output as retryable
`no_speech_detected`, retaining the source and diagnostics.

**Rationale**: The approved specification makes non-empty output a completion gate.
A distinct error explains legitimate silence or an overly aggressive VAD result
without fabricating speech or publishing misleading empty derivatives.

**Alternatives considered**:

- Complete with empty Markdown/SRT: violates the completion gate.
- Insert a synthetic "no speech" subtitle: invents transcript content.

## Transfer direction and credentials

**Decision**: The laptop pushes only to the VPS. For worker activity, the VPS
pushes input and code, starts the worker, and pulls results. The worker never opens
a connection to the VPS and never receives the VPS private key.

**Rationale**: This directly enforces the credential boundary and makes a
compromised disposable worker unable to authenticate back to permanent storage.
The Hugging Face read token is a separate, narrowly scoped external-service secret
passed only to the container runtime.

**Alternatives considered**:

- Worker pushes results to the VPS: requires a return credential and violates the
  project constitution.
- Shared object storage: adds credentials and infrastructure not otherwise needed.

## Upload and recording identity

**Decision**: Transfer to an `uploading/` partial path, verify source size and
SHA-256 on the VPS, then atomically rename into `incoming/`. Use SHA-256 as stable
identity across filenames and lifecycle directories.

**Rationale**: Discovery can safely scan only `incoming/`; an interrupted transfer
never becomes a job. Digest identity prevents duplicate work after relocation or a
same-content/different-name upload.

**Alternatives considered**:

- Discover directly from the rsync destination: races with partial transfers.
- Filename-only identity: fails across renaming and collisions.

## Test strategy

**Decision**: Use dependency-free `unittest` for deterministic controller logic,
inject the external command runner, and reserve a single real GPU/outdoor-audio
scenario for owner acceptance.

**Rationale**: This provides strong coverage where errors risk data loss or stuck
jobs without trying to reproduce CUDA, network, and diarization behavior in every
development run.

**Alternatives considered**:

- Full GPU CI: costly and disproportionate for this personal project.
- Manual-only validation: insufficient for the state machine and idempotency rules.
