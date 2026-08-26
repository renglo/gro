# Publishing `renglo-gro` (Python) and `@renglo/gro` (npm)

Publisher account: **renglo** CodeArtifact (`PUBLISHER_NAME=renglo` → SSM `/publisher/renglo/config`).

## Dist names

| Artifact | Name | Version (keep in sync) |
|----------|------|-------------------------|
| PyPI / CodeArtifact | `renglo-gro` | `package/pyproject.toml` → `0.0.1` |
| Import package | `gro` | unchanged (`from gro...`) |
| npm / CodeArtifact | `@renglo/gro` | `ui/package.json` → `0.0.1` |

Same pattern as `renglo-schd` / `schd` and `renglo-data` / `data`.

## Repo variables (GitHub)

Set on the `renglo/gro` repository:

- `AWS_PUBLISH_ROLE_ARN` — OIDC role that can publish to the renglo domain
- `PUBLISHER_NAME` — `renglo`
- `AWS_REGION` — `us-east-1` (optional; default in workflow)

## How to publish

1. Merge to `main` with versions bumped in `package/pyproject.toml` and `ui/package.json`.
2. Tag and push (if `v0.0.1` already exists for the old `gro` name, use workflow_dispatch or a new tag such as `v0.0.1-renglo`):
   ```bash
   git tag v0.0.1
   git push origin v0.0.1
   ```
3. Workflow `.github/workflows/publish-extension.yml` runs on `v*` tags:
   - stages `blueprints/*.json` → `package/gro/blueprints/`
   - `python -m build package` + twine → CodeArtifact `python-store` as **`renglo-gro`**
   - `npm publish` from `ui/` → CodeArtifact `npm-store` as **`@renglo/gro`**

Or use **Actions → Publish extension → Run workflow**.

## Local smoke build (no upload)

```bash
python -m pip install build
python -m build package
ls package/dist/   # renglo_gro-0.0.1-*.whl and .tar.gz
```

## Consumers (arbitium-bom)

Depend on the **dist name** `renglo-gro` (e.g. `arbitiumtriage` → `renglo-gro>=0.0.1`). Import code stays `from gro...`.

Dependency note: `renglo-gro` requires `graphforge>=0.4.0`. That package must also be reachable from an index CI can read.
