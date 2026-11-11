# Releasing Agent Code from GitHub Codespaces

The current source version is **2.2.0** (after 2.1.8). Do not reuse `2.0.0` or the existing `v2.0.0` tag.

## One-time PyPI Trusted Publishing setup (recommended)

1. Open the `agent-code` project on PyPI and add a Trusted Publisher.
2. Select GitHub as the publisher.
3. Set the owner to `Agent-code-dev`, repository to `Agent-code`, workflow to `publish.yml`, and environment to `pypi`.
4. In the GitHub repository, create an environment named `pypi` under Settings → Environments.
5. Ensure the Codespace is opened on the repository's release branch and that the GitHub account has permission to push tags/releases.

No PyPI API token is needed when Trusted Publishing is configured correctly.

## Release from a Codespace

Open the repository in Codespaces, then run this single block. It checks the package version, runs tests, builds and validates wheel/sdist, and creates a local release tag. Review `git status` and the diff before pushing.

```bash
set -euo pipefail
python - <<'PY'
import tomllib
from pathlib import Path
p = tomllib.loads(Path('pyproject.toml').read_text())
version = p['project']['version']
print('Package version:', version)
assert version == '2.2.0', f'Expected 2.2.0, got {version}'
PY
python -m pip install --upgrade build twine pytest
python -m compileall -q src tests
python -m pytest -q
rm -rf build dist
python -m build
python -m twine check dist/*
sha256sum dist/* > SHA256SUMS-2.2.0.txt
git status --short
git diff --check
git add -A
git commit -m "Release Agent Code 2.2.0"
git tag -a v2.2.0 -m "Agent Code 2.2.0"
git push origin HEAD
git push origin v2.2.0
```

Pushing the tag triggers `.github/workflows/publish.yml`. The workflow reruns tests, rebuilds distributions, publishes to PyPI through Trusted Publishing, and creates a GitHub Release with the wheel and source distribution attached. Watch the Actions tab until all jobs finish.

## Manual fallback (only if Trusted Publishing is not configured)

Build and check as above, then use a PyPI API token stored as a Codespaces secret named `PYPI_API_TOKEN`:

```bash
python -m pip install --upgrade twine
python -m twine upload --username __token__ --password "$PYPI_API_TOKEN" dist/*
gh release create v2.2.0 dist/* SHA256SUMS-2.2.0.txt --title "Agent Code 2.2.0" --generate-notes
```

Do not paste a token into the terminal command, source files, or chat. Do not upload the same version twice; PyPI does not allow replacing an already-published file with the same filename/version.

## If the workflow fails

- **PyPI trusted publisher error:** verify owner, repository, workflow filename (`publish.yml`), and environment (`pypi`) match exactly.
- **Tests fail:** fix the failure and make a new patch release version; do not reuse a published version.
- **Tag already exists:** inspect `git tag --list 'v2.2.0'` and GitHub Releases before proceeding. Never force-push a published release tag.
- **Package metadata error:** run `python -m twine check dist/*` before pushing a new tag.
