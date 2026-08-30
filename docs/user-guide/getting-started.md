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

Use **File → New Project** to create an empty `.suav` archive, or **Open
Project** to open an existing project folder. **File → Save** writes
the current project, while **Save As** creates a copy in another format or
location. A `project.json` or `.suav` file can also be opened by passing its
path on the command line.

## Editing

Select an item in the Project Explorer to inspect it in the Properties panel.
Use **Edit → Undo** and **Edit → Redo** for project changes.
