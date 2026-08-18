# Stage 6 Validation Contract

Validation owns semantic config correctness after graph construction.

`resolve()` still fails on blockers that prevent graph construction:

- parse errors
- missing source files or implementations
- spec inheritance cycles
- implementation inheritance cycles
- reference cycles
- invalid override declarations, including unknown policies, incompatible
  policy types, and `deny` without an inline default
- invalid `File[...]` type shapes, missing files, UTF-8 decode failures, and
  JSON/YAML parse failures

`validate(graph)` owns:

- required field checks
- literal type compatibility
- reference assignability
- implementation-parent assignability
- override policy checks for assignments to existing defaults or inherited
  values
- path existence and kind policy checks
- non-path field constraints
- named object assertions after derived values and field constraints are valid

Materialized file content is deliberately not part of ETCM validation.
Relations, assertions, deep overrides, and direct constraints do not traverse a
`File[...]` leaf. Constraints on an ETCM-owned surrounding list or
dictionary still apply to that container.

Stage 6 supported non-path constraints:

- `choices`
- `gt`, `ge`, `lt`, `le`
- `min_length`, `max_length`
- `regex`

Validation returns a new immutable `ResolvedGraph` with `validated=True`.
