# Parser Gates

Stage 4 may start parser implementation only after Stage 3 has made the fixture
and diagnostic contract explicit.

## Entry Gates For Stage 4

Before expanding `src/etcm/syntax/grammar.lark`, Stage 4 should have:

- fixture names for every v0 syntax behavior
- invalid fixture names for every parser-owned diagnostic category
- golden AST and IR summary format documented
- diagnostic JSON shape documented
- a clear rule that resolver and codegen behavior stay out of parser tests
- a clear rule that CLI is only a wrapper over Python bindings

## Parser Responsibilities

Stage 4 parser work should implement:

- `spec` blocks
- top-level `$spec`
- `impl` blocks
- spec inheritance by path without a fragment
- implementation inheritance by selector when needed
- field declarations
- literal assignments
- `$field` reference assignments
- type expressions
- `Field(...)` metadata
- comments and blank lines
- source spans for definitions, assignments, refs, and literals

## Parser Non-Responsibilities

The parser must not:

- check whether referenced files exist
- resolve a selector to a concrete implementation
- enforce type assignability across refs
- check `Path` existence or kind policy
- instantiate Pydantic classes
- contain CLI behavior

The parser may reject syntax that is locally invalid, such as duplicate fields
inside one inline spec or a document that defines both `spec` and `$spec`.

## Indentation Gates

Stage 4 must prove:

- spaces are accepted for nested blocks
- tabs used for indentation fail with `E_PARSE_TAB_INDENT`
- inconsistent indentation fails with `E_PARSE_BAD_INDENT`
- blank lines inside blocks do not accidentally close the block
- YAML-style `#` comments inside blocks do not alter indentation state

If Lark's `Indenter` cannot satisfy these gates cleanly, Stage 4 should stop and
reopen the parser choice rather than pushing indentation complexity into the
resolver.

## Selector And Path Gates

Stage 4 must prove:

- spec inheritance paths do not require `#`
- implementation inheritance and refs can still target `#impl`
- `#` attached to a selector is not a comment
- `#` starts a comment only at line start or after whitespace, outside quoted
  strings
- path-like strings remain literals when quoted
- selector syntax is unambiguous in `$field` refs and parent declarations
- filesystem validation is deferred to the resolver

This protects the earlier decision that spec identity is unique by path, while
implementation identity may require a fragment.

## Exit Gates For Stage 4

Stage 4 is complete when:

- parser tests cover all parser-owned valid fixtures
- parser tests cover all parser-owned invalid fixtures
- AST summary golden output is stable
- IR summary golden output is stable
- parse diagnostics include code, source path, span, and concise message
- `uv run pytest`, `uv run ruff check .`, and `uv run basedpyright` pass
