# Publishing `gro` (Python) and `@renglo/gro` (npm)

Publisher account: **renglo** CodeArtifact (`PUBLISHER_NAME=renglo` → SSM `/publisher/renglo/config`).

## Dist names

| Artifact | Name | Version (keep in sync) |
|----------|------|-------------------------|
| PyPI / CodeArtifact | `gro` | `package/pyproject.toml` → `0.0.1` |
| npm / CodeArtifact | `@renglo/gro` | `ui/package.json` → `0.0.1` |

## Repo variables (GitHub)

Set on the `renglo/gro` (or `Arbitium`/org fork) repository:

- `AWS_PUBLISH_ROLE_ARN` — OIDC role that can publish to the renglo domain
- `PUBLISHER_NAME` — `renglo`
- `AWS_REGION` — `us-east-1` (optional; default in workflow)

## How to publish

1. Merge to `main` with versions bumped in `package/pyproject.toml` and `ui/package.json`.
2. Tag and push:
   ```bash
   git tag v0.0.1
   git push origin v0.0.1
   ```
3. Workflow `.github/workflows/publish-extension.yml` runs on `v*` tags:
   - stages `blueprints/*.json` → `package/gro/blueprints/`
   - `python -m build package` + twine → CodeArtifact `python-store`
   - `npm publish` from `ui/` → CodeArtifact `npm-store`

Or use **Actions → Publish extension → Run workflow**.

## Local smoke build (no upload)

From the repo root, stage blueprints then build (same as CI):

```bash
# stage repo-root blueprints/ → package/gro/blueprints/
python -m pip install build
python -m build package
ls package/dist/   # gro-0.0.1-*.whl and .tar.gz
```

## Consumers (arbitium-bom)

After publish, BOM / pip can resolve `gro` from the **renglo** registry while `arbitiumtriage` comes from the **arbitium** registry (multi-index download).

Dependency note: `gro` requires `graphforge>=0.4.0`. That package must also be reachable from an index CI can read (CodeArtifact or public PyPI via upstream).
