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

Stage 6 supported non-path constraints:

- `choices`
- `gt`, `ge`, `lt`, `le`
- `min_length`, `max_length`
- `regex`

Validation returns a new immutable `ResolvedGraph` with `validated=True`.
