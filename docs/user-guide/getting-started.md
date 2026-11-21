# Getting started

## Install

Install the locked runtime environment with `uv`:

```bash
uv sync --locked
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

## First design

1. **File → New Project** and choose where to save the `.suav` archive.
2. Add a fuselage, a lifting surface, and a control surface from the toolbar.
   Each starts from a default shape.
3. Select a part in the Project Explorer or the 3D Viewer and edit it in the
   Properties panel. Add a propulsor, a battery, and point masses the same way.
4. Select **Vehicle** to check the total mass and center of gravity.
5. Add an analysis from the toolbar, set its parameters, and click **Run
   Analysis**. Its tables and plots appear under the analysis.

Use **Edit → Undo** and **Edit → Redo** for project changes. See
[Interface](interface.md) for the panels and the 3D Viewer.
