# Stage 3 Implementation Handoff

Stage 3 hands Stage 4 a parser-first implementation path.

## Step 1: Expand Fixtures

Add the fixture files named in [fixture-matrix.md](fixture-matrix.md).

Keep fixture content small. Each file should test one behavior unless the file
is explicitly a realistic use case fixture.

## Step 2: Add Golden Directories

Create:

```text
tests/fixtures/golden/ast/
tests/fixtures/golden/ir/
tests/fixtures/golden/diagnostics/
```

Do not add resolver graph or Pydantic golden files until those stages have
serializers.

## Step 3: Implement Parser Tests

Add tests that:

- parse each parser-owned valid fixture
- reject each parser-owned invalid fixture
- compare AST summaries for stable source spans
- compare IR summaries for stable normalized syntax data
- compare diagnostic JSON for parser-owned failures

Resolver-owned fixtures may exist before resolver implementation, but Stage 4
should mark them as future resolver fixtures rather than forcing parser tests to
interpret semantics.

## Step 4: Expand Grammar And Transformer

Implement the Lark grammar and transformer inside `etcm.syntax`.

Keep the transformer output independent from Lark objects. Public API and IR
objects must not expose parser-library classes.

## Step 5: Verify Boundaries

Parser tests should prove:

- no filesystem checks occur in `etcm.syntax`
- no Pydantic imports occur in `etcm.syntax` or `etcm.ir`
- CLI code remains absent or only calls public Python APIs

## Step 6: Verify Commands

Run:

```bash
uv run pytest
uv run ruff check .
uv run basedpyright
```

If dependency installation is blocked by network restrictions, use the existing
`uv sync --extra dev` workflow with approval rather than changing tooling.

## Commit Boundary

Commit Stage 3 documentation separately from Stage 4 parser code. Commit Stage
4 only after parser-owned fixtures and golden outputs pass.
