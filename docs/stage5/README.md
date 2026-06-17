# Stage 5: Resolver And Type Checker

Stage 5 implements deterministic semantic resolution over Stage 4 parser IR.
It makes `resolve()` and `validate()` work, emits a stable resolved graph, and
keeps generated runtime views for Stage 6.

## Outcome

Stage 5 should leave the project with:

- resolver graph dataclasses and deterministic JSON summaries
- selector loading relative to declaring files
- `$spec`, spec inheritance, implementation inheritance, and refs
- primitive, container, union, named-ref, and `Path` type checks
- override policy checks for inherited values
- path existence and kind validation
- resolver-owned diagnostics and fixtures

## Artifacts

- [resolver-contract.md](resolver-contract.md): public API and semantic rules.
- [graph-contract.md](graph-contract.md): resolved graph shape.
- [diagnostics.md](diagnostics.md): resolver diagnostic codes.
- [reasoning.md](reasoning.md): implementation strategy and tradeoffs.
- [fixture-matrix.md](fixture-matrix.md): resolver use cases covered by tests.
- [implementation-handoff.md](implementation-handoff.md): Stage 6 handoff.

## Non-Goals

Stage 5 does not implement Pydantic, dataclass, dict materialization, CLI
commands, DOT graph export, JSON Schema, sweeps, or migration tools.

## Exit Criteria

Stage 5 is complete when resolver-owned valid fixtures match graph goldens,
invalid fixtures match diagnostic goldens, path policy behavior is tested in
both permissive and strict resolver modes, and `uv run pytest`,
`uv run ruff check .`, and `uv run basedpyright` all pass.
