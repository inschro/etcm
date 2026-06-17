# Stage 2 Implementation Handoff

## Step 1: Project Metadata

Add `pyproject.toml` and `.gitignore` exactly as described in
[scaffold-plan.md](scaffold-plan.md).

Do not run `uv init`; create files intentionally so the existing README and docs
are not overwritten.

## Step 2: Package Namespaces

Create the `src/etcm` tree:

- public API placeholder in `src/etcm/__init__.py`
- `py.typed`
- module `__init__.py` files
- empty or placeholder modules for syntax, IR, resolver, codegen, CLI, errors

## Step 3: IR Dataclasses

Implement the Stage 2 IR dataclasses from [ir-contract.md](ir-contract.md).

Keep them frozen and parser-independent.

## Step 4: Placeholder API

Implement:

- `Resolver(path_exists="allow_missing")`
- `Resolver.load(...)`
- `load(...)`
- `resolve(...)`
- `validate(...)`

All behavior methods should raise clear `NotImplementedError`.

## Step 5: Fixtures And Tests

Create fixture tree and tests:

- import tests
- placeholder API tests
- IR frozen dataclass tests
- selector construction tests
- fixture presence tests
- dependency-boundary tests for `etcm.ir`

## Step 6: Verify

Run:

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run basedpyright
```

If dependency installation fails because network access is restricted, rerun the
same command with escalation approval rather than changing the dependency plan.

## Commit Boundary

Commit Stage 2 as one scaffold commit if all checks pass. If dependency
installation is blocked externally, commit only after the repo-local tests that
can run have passed and document the blocked command in the final message.

