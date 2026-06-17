# Stage 2 Scaffold Plan

## Files To Add

```text
pyproject.toml
.gitignore
src/etcm/__init__.py
src/etcm/py.typed
src/etcm/errors.py
src/etcm/syntax/__init__.py
src/etcm/syntax/parser.py
src/etcm/syntax/grammar.lark
src/etcm/ir/__init__.py
src/etcm/ir/nodes.py
src/etcm/resolve/__init__.py
src/etcm/codegen/__init__.py
src/etcm/cli/__init__.py
tests/test_imports.py
tests/test_public_api_placeholders.py
tests/test_ir_contracts.py
tests/test_fixture_contract.py
tests/fixtures/valid/inline_spec.etcm
tests/fixtures/valid/spec_ref_impls.etcm
tests/fixtures/invalid/duplicate_field.etcm
tests/fixtures/invalid/malformed_syntax.etcm
tests/fixtures/golden/README.md
```

## Project Metadata

Use `pyproject.toml` with:

- package name: `etcm`
- Python: `>=3.12`
- build backend: `hatchling`
- runtime dependencies: `lark>=1.3`, `pydantic>=2.13`
- dev dependencies: `pytest`, `ruff`, `basedpyright`
- `src` layout
- Ruff target: `py312`
- basedpyright include paths: `src`, `tests`

## Gitignore

Add a minimal `.gitignore`:

```gitignore
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
.basedpyright/
dist/
build/
*.egg-info/
```

## Commands

Expected project commands:

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run basedpyright
```

`uv sync --extra dev` may need network access the first time because the repo
does not currently have a lock file or project environment.

