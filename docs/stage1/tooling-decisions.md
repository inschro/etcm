# Stage 1 Tooling Decisions

## Package And Environment

Decision:

- Use a greenfield package in this repository.
- Use a `src/` layout for package code.
- Use Python `>=3.12`.
- Use `uv` for dependency management, lock files, and local commands.
- Use `hatchling` as the build backend for the first package scaffold.

Reasoning:

- The current project is a pure Python library with an optional CLI wrapper, so
  a greenfield package avoids inherited semantics from broader config
  frameworks.
- A `src/` layout prevents accidental imports from the repository root and is
  standard for libraries intended to be installed.
- Python 3.12 is conservative relative to current local Python and gives modern
  typing and dataclass behavior without forcing very new interpreter support.
- `uv` supports library projects with `src` layout and packaged builds, while
  keeping local commands and dependency locking straightforward.
- `hatchling` is a simple established backend and matches the reference ANF
  repository style.

Implementation default:

```toml
[project]
name = "etcm"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "lark>=1.3",
  "pydantic>=2.13",
]

[project.optional-dependencies]
dev = [
  "basedpyright",
  "pytest",
  "ruff",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

## Parser

Decision:

- Use Lark for the first parser core, but treat the decision as provisional
  until Stage 2 fixture tests prove indentation, selectors, and diagnostics.
- Use `parser="lalr"` initially.
- Enable `propagate_positions=True`.
- Use Lark's `Indenter` for indentation-shaped ETCM blocks.
- Keep parser output behind `etcm.syntax`; never expose Lark nodes in public IR.

Reasoning:

- ETCM needs grammar iteration, source spans, useful parse diagnostics, and a
  pure Python installation path.
- Lark accepts EBNF grammars, supports LALR/Earley parser choices, propagates
  line/column metadata, and exposes error context helpers.
- A local Lark indentation spike parsed `spec` and `impl` blocks with source
  spans and rejected a bad nested indent.
- A lightweight pyparsing smoke test proved it can parse indentation-shaped
  blocks, but its grammar style is less close to ETCM's desired language
  reference and produced less compelling structured output in the quick check.
- ANTLR is powerful but adds generator/tooling weight and an external workflow
  too early.
- Tree-sitter is excellent for editor-grade incremental parsing, but its grammar
  and packaging overhead are not justified for v0.
- Hand-written recursive descent would give full control but would slow down
  syntax iteration before the language shape is stable.

Fallback:

- Reconsider recursive descent if Lark cannot express indentation/block
  semantics cleanly, if token ambiguity around paths/selectors becomes
  unmanageable, or if diagnostics cannot meet the fixture contract.
- Reconsider pyparsing if Lark's indenter proves brittle but a parser-combinator
  grammar remains readable.
- Reconsider Tree-sitter only when editor integration becomes a primary goal.

## Runtime Validation

Decision:

- Generate Pydantic v2 models first.
- Use dataclass and dict outputs as adapters over the resolved graph.
- Perform ETCM-specific graph validation before Pydantic materialization.

Reasoning:

- Pydantic v2 supports runtime model creation through `create_model()`, field
  defaults, constraints, immutable models, and JSON Schema export.
- Pydantic is a runtime view, not the source of truth. ETCM specs and resolved
  graph metadata remain canonical.
- ETCM-specific features such as typed refs, source identity, path existence
  policy, and override policy need to be resolved before Pydantic sees values.

## CLI

Decision:

- Treat the CLI as a minimal wrapper around Python bindings.
- Use stdlib `argparse` for the first CLI only if/when a CLI is needed.
- Do not add Typer in v0 unless CLI ergonomics become a product priority.

Reasoning:

- V0 CLI commands are thin wrappers: `validate`, `resolve`, `inspect`, `graph`.
- The Python API is the product surface that needs hardening first.
- Avoiding Typer keeps the dependency graph focused on parser, resolver, and
  generated-view risks.
- `argparse` is in the standard library and handles basic options, subcommands,
  help text, and parse errors well enough for a wrapper.

## Quality And Tests

Decision:

- Use Ruff for linting and formatting.
- Use basedpyright for static type checking.
- Use pytest for tests.
- Use text and JSON golden fixtures, not opaque binary snapshots.

Reasoning:

- Ruff provides linting and formatting in one fast tool.
- basedpyright keeps type checking strict enough for IR and resolver code.
- pytest is the standard Python test harness and supports parametrized fixture
  tests naturally.
- Golden outputs should be reviewable in normal diffs.
