# Stage 7 Fixture Matrix

Stage 7 adds CLI tests over existing parser, resolver, validation, and generated
view fixtures.

## Covered Cases

- `resolve` emits graph JSON with `validated: false`
- `validate` emits graph JSON with `validated: true`
- `validate --short` emits `OK: <selector>`
- `validate` reports ETCM diagnostics on invalid input
- `load` defaults to `--target dict`
- `load --target dict`, `dataclass`, and `pydantic` emit equivalent JSON for a
  generated config object
- dataclass target output serializes `Path` values as strings
- `load` reports ETCM diagnostics on invalid input
- removed commands such as `inspect` and `graph` fail through argparse

## Verification

The stage is verified with:

```bash
uv run pytest
uv run ruff check .
uv run basedpyright
uv run etcm --help
uv run python -m etcm.cli --help
```
