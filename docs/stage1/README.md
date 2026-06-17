# Stage 1: Architecture And Tool Selection

Stage 1 decides how ETCM will be built before the parser core exists. The goal
is to choose a small, durable architecture and prove the risky tools with
spikes, not to implement production package code.

## Outcome

Stage 1 chooses:

- greenfield ETCM codebase, not a fork of Hydra, OmegaConf, Gin, or a parser
  project
- Python 3.12+ library with `src/` layout
- `uv` for environment and lock management
- `hatchling` build backend for packaging
- Lark as the first parser implementation target
- Pydantic v2 as the first generated runtime view
- optional stdlib `argparse` CLI wrapper around Python bindings; no Typer for
  v0
- Ruff, basedpyright, and pytest for quality checks
- parser-independent immutable IR
- resolver output as the canonical graph artifact

## Stage 1 Artifacts

- [tooling-decisions.md](tooling-decisions.md): package, parser, validation,
  CLI, lint/type, and test choices.
- [architecture-decisions.md](architecture-decisions.md): module boundaries,
  data ownership, graph shape, and resolver policies.
- [parser-decision-hardening.md](parser-decision-hardening.md): evidence tiers,
  parser alternatives, indentation risk, and go/no-go gates.
- [parser-spike.md](parser-spike.md): Lark source span and syntax spike.
- [pydantic-spike.md](pydantic-spike.md): dynamic model and `Path` field spike.
- [test-strategy.md](test-strategy.md): fixture and golden output strategy.
- [implementation-handoff.md](implementation-handoff.md): exact next steps for
  Stage 2.
- [sources.md](sources.md): primary source links used for decisions.

## Non-Goals

Stage 1 does not create:

- production parser code
- resolver behavior
- generated bindings
- CLI commands
- package scaffolding beyond documentation

Those start after the architecture and fixture contract are accepted.

## Local Findings

- Current repo contains docs only.
- Git is initialized on `main`.
- Local default `python` reports `Python 3.14.5`.
- `lark` is available locally at version `1.3.1`.
- `pydantic`, `typer`, and `pytest` were not available in the base Python
  environment, but Pydantic v2 was validated through `uv run --with pydantic`.
- Among checked parser packages, only `lark` was installed locally. A lightweight
  `pyparsing` alternative smoke test was run through `uv run --with pyparsing`.
