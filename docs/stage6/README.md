# Stage 6: Orthogonal API And Generated Views

Stage 6 turns Stage 5 resolution into a staged public pipeline and implements
generated runtime views.

## Outcome

Stage 6 leaves the project with:

- `load(selector, target=...)` as the ergonomic full-pipeline entrypoint
- `resolve(selector)` as selector-to-graph construction
- `validate(graph)` as graph validation and validated-flag marking
- `convert(graph, target=...)` as graph-to-view materialization
- generated `dict`, frozen dataclass, and frozen Pydantic views
- resolver-owned non-path constraint validation

## Artifacts

- [api-contract.md](api-contract.md): public API and pipeline semantics.
- [validation-contract.md](validation-contract.md): graph validation ownership.
- [generated-views.md](generated-views.md): conversion target behavior.
- [diagnostics.md](diagnostics.md): Stage 6 diagnostic additions.
- [fixture-matrix.md](fixture-matrix.md): tests and goldens.
- [implementation-handoff.md](implementation-handoff.md): next-stage handoff.

## Non-Goals

Stage 6 does not implement CLI commands, DOT graph export, JSON Schema export,
override patching, sweep support, or migration tooling.

## Exit Criteria

Stage 6 is complete when the API pipeline tests, resolver validation goldens,
generated-view tests, `uv run pytest`, `uv run ruff check .`, and
`uv run basedpyright` all pass.
