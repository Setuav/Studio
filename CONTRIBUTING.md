# Contributing

Thank you for your interest in Setuav Studio. Contributions of any size are
welcome: bug fixes, features, documentation, plugins, or ideas.

## Report a bug or suggest an idea

Open an [issue](https://github.com/Setuav/Studio/issues). For a bug, mention
your operating system, the Studio version, and the steps that lead to it; a
small project file helps a lot.

## Make a change

1. Fork the repository and create a branch from `main`.
2. Install the development environment:

   ```bash
   uv sync --locked --group dev
   uv run --locked setuav-studio
   ```

3. Make your change, and check it before you push:

   ```bash
   uv run --locked ruff check .
   uv run --locked ruff format .
   uv run --locked pyright
   uv run --locked pytest
   ```

4. Open a pull request against `main` and describe what it changes
   and why. CI runs the same checks.

Not sure about an approach? Open a draft pull request or an issue early and
ask.

## Writing a plugin

Plugins do not need to live in this repository. The
[developer guide](https://setuav.github.io/Studio/developer/) shows how to
write and install one.
