# Stage 2 References

Stage 2 inherits the Stage 1 source base and narrows it to scaffold decisions.

## Project Tooling

- uv project docs: https://docs.astral.sh/uv/concepts/projects/init/
- Hatch build docs: https://hatch.pypa.io/latest/config/build/
- Ruff docs: https://docs.astral.sh/ruff/
- basedpyright docs: https://docs.basedpyright.com/latest/
- pytest docs: https://docs.pytest.org/en/stable/

## Runtime And Parser

- Lark API reference: https://lark-parser.readthedocs.io/en/latest/classes.html
- Pydantic models and dynamic model creation:
  https://docs.pydantic.dev/latest/concepts/models/

## CLI

- argparse docs: https://docs.python.org/3/library/argparse.html
- Typer docs, deferred for v0: https://typer.tiangolo.com/

## Local Stage 1 Evidence

- Lark source-span and indentation spikes are documented in
  [../stage1/parser-spike.md](../stage1/parser-spike.md).
- Pydantic dynamic model and `Path` spike is documented in
  [../stage1/pydantic-spike.md](../stage1/pydantic-spike.md).
- Parser hardening notes are documented in
  [../stage1/parser-decision-hardening.md](../stage1/parser-decision-hardening.md).

