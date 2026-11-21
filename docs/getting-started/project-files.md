# Project Files

Setuav Studio supports three project forms:

- a project folder;
- a `project.json` file;
- a portable `.suav` archive.

Use **File → New Project** to create an empty `.suav` archive, or **Open
Project** to open an existing project folder. **File → Save** writes
the current project, while **Save As** creates a copy in another format or
location. A `project.json` or `.suav` file can also be opened by passing its
path on the command line.

## Project format version

Every project file records its format version, such as `1.0`, and the Studio
version that saved it. Studio opens files of its own major format version.

| File | Result |
|---|---|
| Same major, same or older minor | Opens normally. |
| Same major, newer minor | Opens with a warning: data this Studio does not know may be lost when you save. |
| Other major, or no format version | Does not open; the message names the format and the Studio that saved it. |
