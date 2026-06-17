# Stage 1 Sources

Primary sources used for Stage 1 decisions:

- Lark API reference: https://lark-parser.readthedocs.io/en/latest/classes.html
  - `propagate_positions` adds line/column metadata to tree branches.
  - tokens carry start/end position and line/column metadata.
  - `UnexpectedInput.get_context()` supports concise parse error context.
- Pydantic models documentation:
  https://docs.pydantic.dev/latest/concepts/models/
  - `create_model()` supports dynamic model creation from runtime field
    definitions.
  - Pydantic validation produces structured `ValidationError` data.
- uv project documentation:
  https://docs.astral.sh/uv/concepts/projects/init/
  - `uv init --lib` uses a `src` layout for libraries.
  - uv supports packaged projects and build backend selection.
- Hatch build docs:
  https://hatch.pypa.io/latest/config/build/
  - Hatchling is a PEP 517 build backend suitable for pure Python packages.
- Typer documentation: https://typer.tiangolo.com/
  - Typer is type-hint based and useful for polished CLIs, but is deferred for
    v0 dependency focus.
- Python argparse documentation: https://docs.python.org/3/library/argparse.html
  - argparse is the standard library parser for command-line options, arguments,
    and subcommands.
- pyparsing API documentation:
  https://pyparsing-docs.readthedocs.io/en/latest/pyparsing.html
  - pyparsing includes indentation and location helpers, and was used for a
    lightweight parser alternative smoke test.
- Ruff documentation: https://docs.astral.sh/ruff/
  - Ruff provides fast linting and formatting with `pyproject.toml` support.
- pytest documentation: https://docs.pytest.org/en/stable/
  - pytest is the selected test runner for fixture-driven tests.
- basedpyright documentation: https://docs.basedpyright.com/latest/
  - basedpyright is the selected static type checker.
- ANTLR overview: https://www.antlr.org/
  - ANTLR is powerful but adds parser generation workflow weight for v0.
- Tree-sitter introduction: https://tree-sitter.github.io/tree-sitter/
  - Tree-sitter is strong for incremental/editor parsing, but that is not the
    first ETCM implementation need.
