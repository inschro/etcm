# Stage 7: Pipeline CLI

Stage 7 adds a command-line surface over the Stage 6 Python pipeline.

## Outcome

Stage 7 leaves the project with:

- an installed `etcm` console script
- `python -m etcm.cli` support
- `resolve`, `validate`, and `load` CLI commands
- `--path-exists` resolver policy selection on every command
- `load --target dict|dataclass|pydantic` generated-view selection
- JSON stdout for graph and materialized config payloads

## Artifacts

- [cli-contract.md](cli-contract.md): public command behavior.
- [serialization.md](serialization.md): CLI output and target serialization.
- [fixture-matrix.md](fixture-matrix.md): CLI test coverage.
- [implementation-handoff.md](implementation-handoff.md): next-stage handoff.

## Non-Goals

Stage 7 does not add CLI overrides, DOT graph export, interactive inspection,
JSON Schema export, shell completion, config formatting, package publishing, or
remote execution.

`inspect` and `graph` were intentionally kept out of the public CLI. The command
surface mirrors the Python pipeline instead of exposing every internal view as a
top-level command.

## Exit Criteria

Stage 7 is complete when `etcm --help`, `python -m etcm.cli --help`, CLI tests,
`uv run pytest`, `uv run ruff check .`, and `uv run basedpyright` all pass.
