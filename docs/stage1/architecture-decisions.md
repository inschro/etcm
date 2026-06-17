# Stage 1 Architecture Decisions

## Module Boundaries

The first package scaffold should use these boundaries:

```text
src/etcm/
  __init__.py
  syntax/
  ir/
  resolve/
  codegen/
  cli/
  errors.py
  py.typed
```

Responsibilities:

- `etcm.syntax`: Lark grammar loading, parse tree conversion, source spans, and
  syntax diagnostics.
- `etcm.ir`: immutable parser-independent ETCM definitions: specs,
  implementations, fields, selectors, literals, and type expressions.
- `etcm.resolve`: graph construction, inheritance, refs, override policy, path
  policy, cycle detection, and semantic diagnostics.
- `etcm.codegen`: generated views over resolved graph nodes, starting with
  Pydantic.
- `etcm.cli`: command-line wrappers only.
- `etcm.errors`: shared diagnostic and exception types.

## Public API

The first public API should be:

```python
from etcm import Resolver, load, resolve, validate

cfg = load("configs/train.etcm#smoke", as_="pydantic")
graph = resolve("configs/train.etcm#smoke")
validate("configs/train.etcm#smoke")

resolver = Resolver(path_exists="must_exist")
cfg = resolver.load("configs/train.etcm#smoke", as_="pydantic")
```

Rules:

- Module internals may change; public API and diagnostics should be stable.
- Public return values must not expose Lark parse nodes.
- CLI commands must call the same API rather than reimplementing behavior.

## Core IR

Use immutable dataclasses for the first IR:

- `SourceSpan`: file, line, column, end line, end column, start offset, end
  offset
- `Selector`: path plus optional implementation fragment
- `Document`: source file, one inline `SpecDef` or one top-level `SpecRef`,
  implementation definitions
- `SpecDef`: name, optional parent spec path, fields, source span
- `SpecRef`: top-level immutable `$spec` path
- `FieldDef`: name, type expression, default, validation metadata, override
  policy, source span
- `ImplDef`: name, optional parent selector, assignments, references, source
  span
- `Assignment`: field path, value, source span
- `RefAssignment`: field name, selector, source span

IR rules:

- Syntax conversion owns duplicate declaration checks.
- Resolver owns cross-file checks and semantic validation.
- IR stores unresolved path text and the declaring source file so `Path`
  resolution can happen later with policy.

## Resolved Graph

Resolver output is the canonical runtime artifact:

- nodes represent resolved implementations
- nodes carry spec name, implementation name, source file, source span, parents,
  values, and materialized view metadata
- edges represent parent inheritance and typed field references
- applied overrides are recorded with source span and policy result
- `Path` values store original text, declaring source file, resolved path, path
  kind policy, and existence policy

The resolved graph must be serializable without Pydantic objects. Pydantic is a
view over graph values.

## Resolver Settings

Resolver settings are explicit object configuration:

```python
Resolver(path_exists="allow_missing")
Resolver(path_exists="must_exist")
```

Rules:

- No global process setting controls path validation.
- `path_exists="resolver"` on a field delegates to the resolver setting.
- Path values resolve relative to the file where the value was declared.
- Ref selectors resolve relative to the file that contains the selector.

## Diagnostics

All diagnostics should include:

- stable error code
- source file
- source span when available
- selector or graph path when available
- concise message
- optional details for verbose CLI output

Initial error categories:

- parse error
- duplicate definition
- missing selector
- inheritance cycle
- reference cycle
- type mismatch
- invalid override
- invalid path
- generated view failure

