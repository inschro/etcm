# Stage 1 Test Strategy

ETCM should create fixtures before production parser work. Tests should encode
language behavior as stable inputs and reviewable outputs.

## Fixture Layout

Proposed layout:

```text
tests/
  fixtures/
    valid/
    invalid/
    golden/
```

Valid fixture groups:

- inline spec with no implementations
- inline spec with one implementation
- inline spec with multiple implementations
- implementation-only file with top-level `$spec`
- spec inheritance without fragments
- implementation inheritance with `#impl`
- typed refs across files
- `Path` fields with `must_exist`, `allow_missing`, and resolver-controlled
  policy

Invalid fixture groups:

- duplicate specs
- duplicate fields
- duplicate implementations
- inline `spec` plus top-level `$spec`
- malformed literals
- missing selector target
- spec inheritance cycle
- implementation inheritance cycle
- reference cycle
- type mismatch
- denied override
- invalid path kind
- missing path under `must_exist`

## Golden Outputs

Use ordinary text and JSON files:

- parsed AST summary
- normalized IR summary
- resolved graph JSON
- generated Pydantic schema summary
- diagnostic text for expected failures

Golden files must be deterministic and diff-friendly. Avoid binary snapshots.

## Test Phases

Parser tests:

- parse valid files
- reject invalid syntax
- check source spans for representative nodes
- assert diagnostics include file, line, column, and context

IR tests:

- reject duplicates
- normalize selectors
- preserve raw literal values and source spans
- keep Lark classes out of IR values

Resolver tests:

- apply spec inheritance and `$spec` reuse
- apply implementation inheritance
- resolve refs and detect cycles
- enforce assignability
- enforce override policies
- resolve `Path` values relative to declaring source file
- enforce field and resolver path policies

Codegen tests:

- generate Pydantic classes for primitives, containers, refs, paths, defaults,
  choices, bounds, and nullable fields
- reject invalid values with wrapped ETCM diagnostics
- export stable dict/JSON payloads from resolved graph values

CLI tests:

- `validate` succeeds and fails correctly
- `resolve --format json` emits stable JSON
- `inspect` includes spec fields, refs, parents, and source paths
- `graph --format dot` includes typed edges

## Acceptance For Stage 2 Start

Before production parser work starts:

- fixture names and expected golden file formats are documented
- first parser tests are written against docs examples
- first generated Pydantic test is written from the spike case
- CI command set is defined, even if CI is not configured yet

