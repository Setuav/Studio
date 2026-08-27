# Getting started

## Install

Install the locked runtime environment with `uv`:

```bash
uv sync --locked --all-extras
```

Start Setuav Studio:

```bash
uv run --locked setuav-studio
```

To open a project directly, pass its folder, `project.json`, or `.suav` path:

```bash
uv run --locked setuav-studio path/to/project
```

## Project files

Setuav Studio supports three project forms:

- a project folder;
- a `project.json` file;
- a portable `.suav` archive.

Use **File → Open Project** to open a project. **File → Save** writes the
current format, while **Save As** creates a new project or archive.

## Editing

Select an item in the Project Explorer to inspect it in the Properties panel.
Use **Edit → Undo** and **Edit → Redo** for project changes.
