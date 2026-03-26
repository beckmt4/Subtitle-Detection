# SubTagger

**SubTagger** is a Python 3.11+ tool that automatically detects the language of subtitle tracks inside media files and external subtitle files, then writes the correct ISO 639 language tag back to the file — so media players and Plex/Jellyfin/Emby can present the right language labels without manual editing.

---

## Features

- 🔍 **Recursive directory scanning** for `.mkv`, `.mp4`, `.srt`, `.ass`, `.ssa`, `.vtt` files
- 🧠 **Multi-engine language detection** using [lingua](https://github.com/pemistahl/lingua-py) (primary) and [langdetect](https://github.com/Mimino666/langdetect) (fallback)
- 🎤 **Whisper audio fallback** — when subtitle text is absent or too short, transcribes audio via [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- 🤖 **Ollama LLM adjudication** — forwards uncertain samples to a local LLM for conservative, explainable decisions
- 🏷️ **Non-destructive tagging**:
  - `.mkv` — uses `mkvpropedit` (no re-encode)
  - `.mp4` — remux via `ffmpeg`
  - External subtitle files — renames with language code (e.g. `movie.en.srt`)
- 🛡️ **Never overwrites existing tags** — only acts on `und`/unknown streams
- 📋 **Dry-run mode** — see every decision before committing
- 📊 **SQLite audit log** + run summary
- 🔁 **Watch mode** — continuously re-scan on a configurable interval
- 🐳 **Docker / Docker Compose** ready
- ⚙️ **YAML + environment variable** configuration

---

## Prerequisites

| Dependency | Notes |
|---|---|
| Python 3.11+ | For local installation |
| `ffmpeg` / `ffprobe` | Stream inspection and extraction |
| `mkvtoolnix` (`mkvpropedit`) | MKV language tagging (no re-encode) |
| Docker (optional) | For containerised deployment |
| Ollama (optional) | Local LLM adjudication |

---

## Installation

### Docker (recommended)

```bash
git clone https://github.com/your-org/subtagger.git
cd subtagger
cp config.example.yml config/config.yml   # edit paths
docker compose up --build
```

### Local

```bash
git clone https://github.com/your-org/subtagger.git
cd subtagger
pip install -r requirements.txt
pip install -e .
```

---

## Unraid Deployment (Community Applications)

1. Open **Community Applications** and search for *SubTagger*, **or** use the **Docker** tab to add a custom container:
   - **Repository:** `ghcr.io/your-org/subtagger:latest`
   - **Network type:** `bridge`
   - **Volumes:**
     - `/mnt/user/media` → `/media` (Read Only)
     - `/mnt/user/appdata/subtagger` → `/config`
     - `/mnt/user/appdata/subtagger/logs` → `/logs`
   - **Variables:**
     - `SUBTAGGER_CONFIG` = `/config/config.yml`
     - `SUBTAGGER_LOG_LEVEL` = `INFO`
2. Place a `config.yml` in `/mnt/user/appdata/subtagger/` (copy from `config.example.yml`).
3. Set `scan_paths` to your media share paths and `watch_mode: true` for continuous operation.
4. Start the container — logs appear in the **Docker** log viewer.

---

## Configuration

Copy `config.example.yml` and adjust as needed:

```yaml
scan_paths:
  - /media/movies
  - /media/tv

include_extensions:
  - .mkv
  - .mp4
  - .srt
  - .ass
  - .ssa
  - .vtt

exclude_patterns:
  - "*/sample/*"
  - "*/extras/*"
  - "*trailer*"

dry_run: false          # true = preview only, no writes
report_only: false      # true = detect but never write tags
min_confidence: 0.85    # 0–1, reject detections below this
min_text_length: 50     # minimum cleaned-text chars to attempt detection

use_whisper_fallback: false
whisper_model: base     # tiny | base | small | medium | large

use_ollama: false
ollama_url: "http://localhost:11434"
ollama_model: "llama3"

audit_log_path: "/logs/subtagger_audit.db"
log_level: "INFO"       # DEBUG | INFO | WARNING | ERROR

watch_mode: false
watch_interval: 3600    # seconds between scans in watch mode
```

### Environment variables

Every config key can be overridden with `SUBTAGGER_<KEY>`:

| Variable | Config key |
|---|---|
| `SUBTAGGER_DRY_RUN` | `dry_run` |
| `SUBTAGGER_MIN_CONFIDENCE` | `min_confidence` |
| `SUBTAGGER_USE_WHISPER` | `use_whisper_fallback` |
| `SUBTAGGER_USE_OLLAMA` | `use_ollama` |
| `SUBTAGGER_OLLAMA_URL` | `ollama_url` |
| `SUBTAGGER_OLLAMA_MODEL` | `ollama_model` |
| `SUBTAGGER_WHISPER_MODEL` | `whisper_model` |
| `SUBTAGGER_AUDIT_LOG` | `audit_log_path` |
| `SUBTAGGER_WATCH_MODE` | `watch_mode` |
| `SUBTAGGER_WATCH_INTERVAL` | `watch_interval` |
| `SUBTAGGER_LOG_LEVEL` | `log_level` |

---

## CLI Usage

```
subtagger [OPTIONS] [PATH ...]
```

| Option | Description |
|---|---|
| `PATH` | One or more files or directories to scan |
| `--config FILE` | Path to YAML config file |
| `--dry-run` | Preview actions without writing anything |
| `--report-only` | Detect languages, print report, no writes |
| `--min-confidence FLOAT` | Override confidence threshold |
| `--watch` | Enable watch mode |
| `--log-level LEVEL` | DEBUG / INFO / WARNING / ERROR |
| `--no-whisper` | Disable Whisper fallback |
| `--no-ollama` | Disable Ollama adjudication |
| `--version` | Show version and exit |

---

## Example Output

### Dry-run

```
$ subtagger /media/movies --dry-run --log-level INFO

2024-01-15T12:00:01 [INFO    ] subtagger.scanner: Scanning directory: /media/movies
2024-01-15T12:00:01 [INFO    ] subtagger.scanner: Scan complete — 3 file(s) found.
2024-01-15T12:00:02 [INFO    ] subtagger.detector: Language detected: english (97.00%) via lingua
2024-01-15T12:00:02 [INFO    ] subtagger.writer: [DRY-RUN] Would set MKV stream 2 language to 'eng' in The.Movie.mkv
2024-01-15T12:00:03 [INFO    ] subtagger.detector: Language detected: french (91.00%) via lingua
2024-01-15T12:00:03 [INFO    ] subtagger.writer: [DRY-RUN] Would set MKV stream 3 language to 'fra' in The.Movie.mkv

============================================================
  SubTagger — Run Summary
============================================================
  Total processed : 2
  Tagged          : 0
  Skipped         : 0
  Errors          : 0
============================================================
```

### Live run

```
$ subtagger /media/movies --log-level INFO

2024-01-15T12:05:01 [INFO    ] subtagger.scanner: Scan complete — 3 file(s) found.
2024-01-15T12:05:02 [INFO    ] subtagger.detector: Language detected: english (97.00%) via lingua
2024-01-15T12:05:02 [INFO    ] subtagger.writer: MKV language tag updated: stream 2 → 'eng' in The.Movie.mkv
2024-01-15T12:05:03 [INFO    ] subtagger.detector: Language detected: french (91.00%) via lingua
2024-01-15T12:05:03 [INFO    ] subtagger.writer: MKV language tag updated: stream 3 → 'fra' in The.Movie.mkv

============================================================
  SubTagger — Run Summary
============================================================
  Total processed : 2
  Tagged          : 2
  Skipped         : 0
  Errors          : 0

  Tags written by language:
    eng        1
    fra        1

  Detection method breakdown:
    lingua           2
============================================================
```

---

## Ollama Setup

1. [Install Ollama](https://ollama.com/download) and pull a model:
   ```bash
   ollama pull llama3
   ```
2. Enable in config or environment:
   ```yaml
   use_ollama: true
   ollama_url: "http://localhost:11434"
   ollama_model: "llama3"
   ```
3. For Docker Compose with Ollama on the host:
   ```yaml
   environment:
     - SUBTAGGER_USE_OLLAMA=true
     - SUBTAGGER_OLLAMA_URL=http://host.docker.internal:11434
   ```

Ollama is only invoked when primary detection returns `unknown`, so it has minimal performance impact.

---

## Whisper Fallback Setup

Whisper is used when subtitle streams are image-based (e.g. PGS/HDMV) or produce no extractable text.

1. Ensure `faster-whisper` is installed:
   ```bash
   pip install faster-whisper
   ```
2. Enable in config:
   ```yaml
   use_whisper_fallback: true
   whisper_model: base   # smaller = faster; larger = more accurate
   ```
3. On first use the model weights are downloaded automatically (~150 MB for `base`).

Whisper transcribes the first 60 seconds of audio; the transcript is then passed through normal language detection.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ffprobe not found` | Install `ffmpeg`: `apt install ffmpeg` or `brew install ffmpeg` |
| `mkvpropedit not found` | Install `mkvtoolnix`: `apt install mkvtoolnix` |
| All languages detected as `unknown` | Lower `min_confidence` (e.g. `0.70`) or enable Ollama |
| Whisper model download fails | Check internet access inside the container; use `--no-whisper` to disable |
| Ollama connection refused | Verify Ollama is running: `curl http://localhost:11434/api/tags` |
| MP4 tagging is slow | Normal — MP4 requires a full remux; prefer MKV for large libraries |
| Subtitle renamed with wrong language | Check `min_confidence` threshold; enable `--log-level DEBUG` for detail |
| Watch mode never stops | Use `docker stop subtagger` or `Ctrl-C` in terminal |

---

## Running Tests

```bash
pip install -e .
python -m pytest tests/ -v
```

Or with the standard library runner:
```bash
python -m unittest discover tests/
```

---

## License

See [LICENSE](LICENSE).