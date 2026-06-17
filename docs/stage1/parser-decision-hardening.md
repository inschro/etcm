# Parser And CLI Decision Hardening

## Current Evidence Level

Stage 1 now has three evidence tiers:

| Area | Evidence | Confidence |
| --- | --- | --- |
| Lark source spans and parse context | Local spike plus official docs | High for basic syntax |
| Lark indentation | Local spike with `Indenter` | Medium |
| Pydantic dynamic models and `Path` coercion | Local spike plus official docs | High for first generated view |
| pyparsing alternative | Local smoke test through `uv run --with pyparsing` | Low-medium |
| ANTLR and tree-sitter alternatives | Official docs only | Low as ETCM implementation choices |
| CLI wrapper | Python `argparse` docs plus architecture reasoning | Medium |

The previous Stage 1 result was mostly a single-tool testbed for parser behavior:
Lark was locally tested, while alternatives were evaluated from docs. This file
records the stronger but still limited hardening pass.

## Lark Indentation Spike

Goal:

- Prove indentation-shaped `spec` and `impl` blocks are viable with Lark before
  committing to it for parser core work.

Local result:

```text
start 1 1 10 1
spec 2 1 6 1
impl 6 1 10 1
UnexpectedToken
x: int
        ^
```

Interpretation:

- Lark can parse indentation-shaped blocks with `postlex=Indenter()`.
- Source spans survive on relevant tree nodes.
- Bad indentation produces a parse error with useful context.
- Blank-line handling had to be made explicit in the grammar, which is a real
  design constraint for Stage 2.

Stage 2 gate:

- Do not finalize Lark until fixture tests cover blank lines, comments,
  indentation, nested literals, selector paths, `Field(...)`, and malformed
  indentation.

## pyparsing Alternative Smoke Test

Goal:

- Check whether a parser-combinator alternative should displace Lark before
  package work starts.

Local result:

```text
Installed 1 package in 5ms
pyparsing 3.3.2
IndentedBlock True
locatedExpr True
smoke 1
ParseException 3 5
```

Interpretation:

- pyparsing has indentation and location helpers.
- It can parse a tiny indentation-shaped `impl` block.
- The quick grammar was less declarative than the equivalent Lark grammar and
  produced less useful structured output without more custom work.
- pyparsing remains a fallback, not the primary parser choice.

Stage 2 gate:

- Revisit pyparsing only if Lark's indentation, token ambiguity, or diagnostics
  fail against fixtures.

## ANTLR And Tree-sitter

ANTLR:

- Strong fit for mature generated parser workflows.
- Adds generator/tool workflow weight and likely Java/tooling assumptions.
- Not worth adopting before ETCM syntax stabilizes.

Tree-sitter:

- Strong fit for editor-grade incremental parsing and error recovery.
- Adds grammar/package complexity that is unnecessary for the first Python
  library core.
- Revisit when editor integration becomes a real goal.

## Indentation Policy

Decision:

- Keep indentation-shaped ETCM syntax for v0.
- Use Lark `Indenter` in Stage 2 unless fixture tests prove it is brittle.
- Require spaces for indentation in v0 docs and diagnostics; tabs should either
  be rejected or normalized explicitly before parser finalization.

Open parser design issues:

- Exact blank-line and comment behavior inside blocks.
- Whether nested mapping/list literals may span lines in v0.
- Whether path/selectors need a quoted form to avoid token ambiguity.
- Whether field paths like `optimizer.lr` are syntax-level paths or plain keys.

## CLI Policy

Decision:

- CLI is not a core functionality risk in v0.
- Treat CLI as a thin convenience wrapper over Python bindings.
- Use `argparse` if/when the CLI is scaffolded.
- Defer Typer until CLI UX becomes important enough to justify another runtime
  dependency.

Required CLI behavior when implemented:

- parse command and flags
- instantiate `Resolver`
- call public Python API
- format diagnostics
- exit with stable status code

The CLI must not contain parser, resolver, graph, or codegen logic.

## What Is Still Not Proven

- Full ETCM grammar with indentation and multiline literals.
- Selector/path token ambiguity.
- High-quality diagnostics across all failure categories.
- Parser performance on large config graphs.
- Generated Pydantic classes for nested refs.
- Graph serialization stability.

These become Stage 2 fixture gates.
