# Stage 4: Parser Core

Stage 4 implements the parser boundary described by the roadmap and Stage 3.
It turns parser-owned fixtures into syntax AST, normalized IR, and stable parse
diagnostics. It does not resolve selectors, validate paths, build graphs,
generate Pydantic models, or implement CLI behavior.

## Outcome

Stage 4 should leave the project with:

- parser-owned fixtures and goldens for valid and invalid syntax
- Lark grammar using indentation-aware parsing
- parser-independent syntax dataclasses
- conversion from syntax dataclasses into the Stage 2 IR
- parse diagnostics using shared ETCM diagnostic types
- tests proving parser behavior and module boundaries

## Artifacts

- [parser-contract.md](parser-contract.md): parser responsibilities and
  non-responsibilities.
- [diagnostics.md](diagnostics.md): Stage 4 diagnostic behavior.
- [implementation-handoff.md](implementation-handoff.md): next implementation
  steps and Stage 5 handoff.

## Exit Criteria

Stage 4 is complete when parser-owned fixtures pass AST, IR, and diagnostic
golden tests, and `uv run pytest`, `uv run ruff check .`, and
`uv run basedpyright` all pass.
