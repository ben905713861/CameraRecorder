# Repository Guidelines

## Project Structure & Module Organization
- Root-level Python modules contain the full app logic:
  - `main.py`: entrypoint; starts one worker thread per enabled camera.
  - `config.py`: YAML loading, environment placeholder resolution, and Pydantic models.
  - `camera_urls.py`: ONVIF/ISAPI stream discovery.
  - `rtsp_motion_detect.py`: frame-difference motion detection.
  - `rtsp_recorder.py`: FFmpeg-based segment recording and event clip compaction.
- Runtime configuration lives in `config.yml`.
- `__pycache__/` is generated output and should not be edited.

## Build, Test, and Development Commands
- Create/activate venv (PowerShell):
  - `python -m venv .venv`
  - `.venv\Scripts\Activate.ps1`
- Install dependencies (typical):
  - `pip install pydantic PyYAML requests onvif-zeep opencv-python`
- Run locally:
  - `python main.py`
- External runtime requirement:
  - `ffmpeg -version` (must be installed and available on `PATH`).

## Coding Style & Naming Conventions
- Follow PEP 8 with 4-space indentation and clear, descriptive names.
- Use `snake_case` for functions/variables, `PascalCase` for classes.
- Keep modules focused (discovery/config/detection/recording separated as today).
- Prefer explicit exceptions over broad `except:` when changing error handling.

## Testing Guidelines
- There is currently no automated test suite in this repository.
- For changes, run a manual smoke test with a non-production camera:
  - start app with `python main.py`
  - verify reconnect behavior and generated clips under configured `output_path`.
- If adding tests, use `pytest` with files named `tests/test_*.py`.

## Commit & Pull Request Guidelines
- Existing history uses short, imperative subjects (e.g., `reconnect`, `multi-thread`).
- Keep commit titles concise, present-tense, and scoped to one change.
- PRs should include:
  - purpose and behavior change summary,
  - config/runtime impacts (camera settings, FFmpeg assumptions),
  - manual verification steps and sample logs/screenshots when relevant.

## Security & Configuration Tips
- Never commit real camera credentials.
- Use environment placeholders in `config.yml` (for example: `${CAMERA_PASSWORD}`).
- Keep local secrets in environment variables or untracked local config overrides.
