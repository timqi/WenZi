# VoiceText - Claude Code Instructions

## Release Process

1. Ensure all changes are committed and tests pass (`uv run pytest tests/`)
2. Update version in `pyproject.toml` (single source of truth — all other files read from it dynamically)
3. Commit: `git commit -m "chore: bump version to X.Y.Z"`
4. Tag: `git tag vX.Y.Z`
5. Push: `git push && git push --tags`
