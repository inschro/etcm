# Stage 4 Implementation Handoff

Stage 4 hands Stage 5 a parser that can produce reliable syntax and IR.

## Implementation Order

1. Add parser-owned fixtures and AST/IR/diagnostic goldens.
2. Add syntax dataclasses that do not depend on Lark.
3. Expand the grammar with Lark `Indenter`.
4. Convert Lark trees to syntax dataclasses.
5. Convert syntax dataclasses to Stage 2 IR.
6. Normalize parser diagnostics to shared ETCM diagnostics.
7. Add parser and module-boundary tests.

## Stage 5 Handoff

Stage 5 starts from `Document` values produced by `parse_document()` and owns
selector loading, default implementation selection, inheritance application,
reference resolution, path validation, type checking, and graph construction.
