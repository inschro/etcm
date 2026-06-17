# Stage 2: Scaffold And Fixture Contract

Stage 2 turns the Stage 1 architecture into an implementation-ready package
plan. It defines the package scaffold, public API placeholders, module
boundaries, immutable IR contracts, syntax shell, fixture harness, and test
commands before the first production parser or resolver behavior is written.

## Outcome

Stage 2 should leave the project ready for code-bearing scaffold work:

- project layout and dependency choices are fixed
- public Python API placeholders are specified
- `etcm.syntax`, `etcm.ir`, `etcm.resolve`, `etcm.codegen`, `etcm.cli`, and
  `etcm.errors` responsibilities are fixed
- initial immutable IR dataclasses are specified
- initial fixture names and golden output expectations are fixed
- full parser, resolver, graph export, codegen, and CLI behavior remain
  intentionally deferred

## Stage 2 Artifacts

- [scope.md](scope.md): what Stage 2 includes and excludes.
- [scaffold-plan.md](scaffold-plan.md): exact files and project metadata to add.
- [api-contract.md](api-contract.md): public API placeholders and behavior.
- [module-boundaries.md](module-boundaries.md): package responsibilities and
  dependency direction.
- [ir-contract.md](ir-contract.md): immutable data contracts for Stage 2.
- [fixture-contract.md](fixture-contract.md): fixture directories, first
  examples, and golden outputs.
- [reasoning.md](reasoning.md): why Stage 2 is shallow and fixture-first.
- [implementation-handoff.md](implementation-handoff.md): ordered execution
  steps for the implementer.
- [references.md](references.md): sources and inherited Stage 1 decisions.

## Non-Goals

Stage 2 does not implement:

- full Lark grammar
- resolver semantics
- graph export
- generated Pydantic bindings beyond a small test spike
- CLI command behavior
- YAML migration
- sweep behavior

## Exit Criteria

Stage 2 is complete when:

- package scaffold imports successfully
- public placeholder API exists and fails clearly
- core IR dataclasses are importable and frozen
- first fixture tree exists
- tests prove the scaffold and fixture contract
- `uv run pytest`, `uv run ruff check .`, and `uv run basedpyright` are defined
  and expected to run in the project environment

