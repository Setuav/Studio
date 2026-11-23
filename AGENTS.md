# AGENTS.md

Operating instructions for coding agents working on Setuav Studio. Keep this file short and concrete.

## Core Rules

1. **Think before coding.**
   - State assumptions out loud before editing.
   - For trivial, unambiguous tasks (typo, local rename, single obvious fix), state a 1-sentence plan and proceed.
   - For non-trivial, multi-file, or ambiguous tasks, **stop before editing** and present this 5-line plan, then wait for approval:
     - **Goal:** 1 sentence
     - **Assumptions / Questions:** explicit assumptions or blockers
     - **Non-Goals:** what will not be touched
     - **Steps:** 2–5 short steps
     - **Verification:** command or check proving done
   - Once approved, complete implementation and verification end-to-end without pausing unless blocked.

2. **Simplicity first.**
   - Write the minimum code that solves the stated problem.
   - No unrequested features, speculative abstractions, or "for future extensibility" hooks.

3. **Surgical changes.**
   - Every changed line must trace directly to the request.
   - Do not refactor, reformat, or "improve" adjacent code or comments you weren't asked to touch.
   - Clean up only unused code/imports created by your own changes.

4. **Goal-driven execution.**
   - Define verifiable success criteria before editing (test, repro script, or check).
   - Run the check and read the output before reporting done. Plausibility is not correctness.

## Communication & Honesty

- **No filler, no flattery.** Skip openers like "Great question" or "You're absolutely right." Start with the answer or action.
- **Disagree when wrong.** If a premise, design, or constraint is flawed, push back before implementing.
- **Never fabricate.** Do not guess file paths, APIs, symbols, or test results. Read the file, run the command, or say "I don't know."

## Project Context

- **Stack:** Python 3.12+, `uv`, PySide6 (Qt6 desktop + OpenGL), NumPy/SciPy, `asteval`, `setuav-pythrust`, `aerosandbox`; `pytest`/`pytest-qt`, `ruff`, `pyright`.
- **Commands:**
  - Install: `uv sync --locked --group dev`
  - Run app: `uv run python -m setuav_studio`
  - Test (single): `uv run pytest tests/core/test_workbench.py` — during active iteration, run only affected test files, NOT the full suite.
  - Test (all): `uv run pytest` — pre-push / pre-PR verification only.
  - Lint / Format / Typecheck: `uv run ruff check .`, `uv run ruff format .` (`--check` in CI), `uv run pyright` — all must pass without errors or warnings.
- **Layout:** Source: `src/setuav_studio/` (core) & `src/plugins/` (bundled plugins) | Tests: `tests/` (`core/`, `plugins/`, domain dirs)
- **Do not modify:** `uv.lock` unless dependencies intentionally change; generated/local dirs (`build/`, `dist/`, `htmlcov/`, `.docs/`).
- **Conventions:**
  - **Core & plugin decoupling:** Keep `src/setuav_studio/` decoupled from `src/plugins/`; domain assets/data (e.g., `src/plugins/geometry/data/airfoils`) and plugin icons (`src/plugins/<plugin>/assets/icons/`) stay inside their plugin directory.
  - **Style & icons:** Resolve theme and icons via `setuav_studio.ui.style` (`icons`, `theme`); each icon is one SVG named after the icon (`<name>.svg`): core icons in `src/setuav_studio/assets/icons/`, plugin icons in the plugin's icon folder, registered with `register_plugin_icons(plugin_id, folder)`. Regenerate the isometric icons with `src/setuav_studio/assets/icons/tools/iso.py`.
  - **Plugin API & thread safety:** Keep `setuav_studio.api` (`StudioAPI`) single and canonical (no legacy names or aliases); never run blocking calls (`time.sleep`, synchronous locks) on the main Qt UI event loop thread.
  - **No symptom masking:** Never swallow exceptions silently, remove failing tests, or return dummy fallbacks; fix underlying root causes.

## Project Learnings

Append a concrete one-line rule when corrected (`Always/Never X for Y`). Prune rules that no longer prevent real mistakes. Keep the full file under 120 lines.

- Always reuse existing Studio APIs, `ui/widget` helpers and native editor patterns in plugins; grep before writing a helper, and never add visuals native editors lack.
- Always build numeric fields with `ParameterField` + `bind_parametric_properties`, and save formulas via `set_expression`, never just the evaluated number.
- Never convert or format unit values by hand in UI code; show them with a read-only `ExpressionPropertyCell` or `get_unit_manager().format_value` / `format_number`.
- Never let project listeners raise domain errors (report via `api.show_status`), and run background work only through `api.tasks.submit`.
