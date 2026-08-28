# SDK release

The public SDK is versioned and published independently from the desktop
application. Release tags use the `sdk-vX.Y.Z` format and must match the
version in `packages/setuav-studio-sdk/pyproject.toml`.

## Publish a release

1. Update the SDK version in `packages/setuav-studio-sdk/pyproject.toml`.
2. Commit the change on `main`.
3. Create and push the matching tag:

   ```bash
   git tag sdk-v0.1.0
   git push origin sdk-v0.1.0
   ```

The `SDK Release` workflow builds the wheel and source distribution, verifies
their metadata, and publishes both files to PyPI.

Before the first release, configure a PyPI Trusted Publisher for the
`Setuav/Studio` repository, workflow `sdk-release.yml`, and environment
`pypi`. No PyPI token is stored in GitHub secrets.

## Build locally

From the SDK directory, build the same distributions used by CI:

```bash
uv run --project ../.. --locked --group package \
  python -m build --outdir ../../dist/sdk
```
