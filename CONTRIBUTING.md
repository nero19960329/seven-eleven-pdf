# Contributing

Thanks for considering a contribution.

## Development setup

Install runtime tools:

```sh
brew install ghostscript uv
```

Install project dependencies:

```sh
uv sync --dev
uv run pre-commit install
```

## Checks

Run the same checks used by CI:

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## Pull request expectations

- Keep changes small and directly tied to the issue or feature.
- Add or update tests when behavior changes.
- Do not introduce optional PDF strategies unless the default behavior remains
  simple and predictable.
- Document any new external system dependency.
- Keep user-facing text in English.

## Release notes

This project does not have an automated release process yet. For now, maintainers
should tag releases manually after CI passes on `main`.
