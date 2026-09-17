# AGENTS.md

Guidelines for AI agents working on the Setuav Studio repository.

## Commands

- **Development / Environment:**
  - Run application: `uv run python -m setuav_studio`
  - Linting: `uv run ruff check .`
  - Code formatting: `uv run ruff format .`
  - Type checking: `uv run pyright`

- **Test Execution Policy:**
  - **During Active Iteration:** Do NOT run the full test suite (`python -m tests.suites all`) for routine edits or focused debugging. Run only specific, affected test files (e.g. `uv run pytest tests/core/test_status_bar_problems.py`).
  - **Pre-Push / Pre-PR Only:** Run full verification (`uv run python -m tests.suites all` and `uv run python scripts/sdk_contract_tests.py`) as a final check before committing or pushing changes.

## Architectural Guidelines

- **Core & Plugin Decoupling:**
  - Core studio engine (`src/setuav_studio/`) and plugins (`src/plugins/`) must remain decoupled.
  - Domain assets and data (e.g., `src/plugins/geometry/data/airfoils`) and icons (`src/plugins/<plugin>/assets/icons/`) must reside within their respective plugin directories.

- **Style and Icon Management:**
  - Use `setuav_studio.ui.style` (`icons` and `theme`) for styling and icon resolution.
  - Plugin icon assets are registered dynamically via `register_plugin_icons(...)`. Do not pollute core asset manifests.

- **SDK Contracts & Thread Safety:**
  - Preserve `setuav_studio_sdk` API compatibility.
  - Do not invoke blocking calls (`time.sleep`, synchronous locks) on the main Qt UI event loop thread.

## Code Quality Standards

- **No Symptom Masking:**
  - Do not swallow exceptions silently, remove failing tests, or return dummy fallback values. Identify and fix underlying root causes.
- **Verification:**
  - Code must pass `ruff check`, `ruff format`, and `pyright` without errors or warnings.
