# Stage 6 Validation Contract

Validation owns semantic config correctness after graph construction.

`resolve()` still fails on blockers that prevent graph construction:

- parse errors
- missing source files or implementations
- spec inheritance cycles
- implementation inheritance cycles
- reference cycles

`validate(graph)` owns:

- required field checks
- literal type compatibility
- reference assignability
- implementation-parent assignability
- override policy checks
- path existence and kind policy checks
- non-path field constraints

Stage 6 supported non-path constraints:

- `choices`
- `gt`, `ge`, `lt`, `le`
- `min_length`, `max_length`
- `regex`

Validation returns a new immutable `ResolvedGraph` with `validated=True`.
