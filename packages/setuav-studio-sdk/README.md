# Setuav Studio SDK

This package defines the Python contracts used by third-party Setuav Studio
plugins. The source and API reference are kept together for versioned releases.

## Developer documentation

From this directory:

```bash
doxygen Doxyfile
```

Open `docs/html/index.html` in a browser.

The generated reference documents only public SDK modules. Application
implementation modules are deliberately excluded.

## Example plugin

The [`packages/example-plugin`](../example-plugin) project shows the
smallest installable plugin: it declares the SDK dependency, publishes an
entry point, and cleans up its workspace and panel during deactivation.

Run the SDK and example-plugin tests from the repository root:

```bash
python scripts/sdk_contract_tests.py
```
