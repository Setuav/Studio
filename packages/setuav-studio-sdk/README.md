# Setuav Studio SDK

This package defines the Python contracts used by third-party Setuav Studio
plugins. The source and API reference are kept together for versioned releases.

## API documentation

From this directory:

```bash
doxygen Doxyfile
```

Open `docs/html/index.html` in a browser.

The generated reference documents only public SDK modules. Application
implementation modules are deliberately excluded.

## Example plugin

The [`examples/hello-plugin`](examples/hello-plugin) project shows the
smallest installable plugin: it declares the SDK dependency, publishes an
entry point, and cleans up its workspace and panel during deactivation.

Run the SDK and example-plugin tests from the repository root:

```bash
PYTHONPATH=packages/setuav-studio-sdk/src \
  python -m unittest discover -s packages/setuav-studio-sdk/tests
PYTHONPATH=packages/setuav-studio-sdk/src:packages/setuav-studio-sdk/examples/hello-plugin/src \
  python -m unittest discover -s packages/setuav-studio-sdk/examples/hello-plugin/tests
```
