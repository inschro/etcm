# Stage 1 Implementation Handoff

This file defines the next concrete implementation steps after Stage 1.

## Step 1: Package Scaffold

Create:

```text
pyproject.toml
src/etcm/__init__.py
src/etcm/py.typed
src/etcm/syntax/
src/etcm/ir/
src/etcm/resolve/
src/etcm/codegen/
src/etcm/cli/
tests/
```

Initial dependencies:

- runtime: `lark>=1.3`, `pydantic>=2.13`
- dev: `pytest`, `ruff`, `basedpyright`

Initial commands:

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run basedpyright
```

## Step 2: Syntax Skeleton

Add only the syntax shell:

- grammar resource file
- parser construction helper
- source span type
- syntax error wrapper
- parse tree to syntax node conversion for a minimal subset

Do not add resolver behavior in this step.

## Step 3: IR Skeleton

Add immutable dataclasses for:

- `SourceSpan`
- `Selector`
- `Document`
- `SpecDef`
- `SpecRef`
- `FieldDef`
- `ImplDef`
- assignment/ref assignment types
- type expression and literal types

Do not expose Lark nodes beyond `etcm.syntax`.

## Step 4: Fixture Harness

Add the first fixtures before expanding grammar:

- one valid `spec` file
- one valid `$spec` implementation-only file
- one invalid duplicate field file
- one invalid parse file
- golden AST/IR summaries

## Step 5: Pydantic View Spike In Package

Move the Pydantic spike into a unit test under `tests/`.

Requirements:

- dynamic class with one constrained int field
- one `Path` field
- frozen and extra-forbid model config
- deterministic class name

## Explicit Deferrals

Do not implement yet:

- full resolver
- graph export
- complete CLI
- YAML migration
- sweep behavior
- package publishing metadata beyond local package basics

