# OpenMind — Distribution

## Canonical package names

- **Project name:** OpenMind
- **Python import package:** `openmind`
- **CLI command:** `openmind`
- **PyPI distribution name:** `openmind-berkeley`

The PyPI package name differs from the project name because `openmind` is already taken on PyPI. Keeping the import package and CLI command as `openmind` preserves the user experience:

```bash
pip install openmind-berkeley
openmind
```

## Supported install channels

### 1. GitHub install

Good for early testers before the first PyPI release:

```bash
pip install git+https://github.com/qazybekb/openmind.git
openmind
```

### 2. PyPI install

This should be the default public install path once the package is published:

```bash
pip install openmind-berkeley
openmind
```

### 3. `pipx` install

Best option for CLI-first users and Homebrew users:

```bash
pipx install openmind-berkeley
openmind
```

On macOS, the cleanest path is:

```bash
brew install pipx
pipx ensurepath
pipx install openmind-berkeley
```

## Release workflow

The repo includes a publish workflow at `.github/workflows/publish.yml`.

Recommended release flow:

1. Merge to `main` with passing CI.
2. Bump the version in `pyproject.toml` and `src/openmind/__init__.py`.
3. Update `CHANGELOG.md`.
4. Create a Git tag like `v0.1.0`.
5. Push the tag.
6. Let GitHub Actions build the sdist and wheel, run `twine check`, and publish to PyPI.

## PyPI setup

Before the first release:

1. Create the `openmind-berkeley` project on PyPI if needed.
2. Configure PyPI trusted publishing for this GitHub repo.
3. Verify the publish workflow has permission to request an OIDC token.

The workflow in this repo is designed for trusted publishing and does not require storing a long-lived PyPI API token in GitHub secrets.

## Optional integrations on PyPI

Once published, extras should install like this:

```bash
pip install "openmind-berkeley[telegram]"
pip install "openmind-berkeley[gmail]"
pip install "openmind-berkeley[calendar]"
pip install "openmind-berkeley[all]"
```

## Homebrew notes

For now, the recommended Homebrew story is:

```bash
brew install pipx
pipx install openmind-berkeley
```

This avoids maintaining a custom Homebrew formula for a Python app whose dependencies already resolve cleanly through PyPI.

If you later want a dedicated Homebrew tap, treat that as a second distribution track after PyPI is stable.
