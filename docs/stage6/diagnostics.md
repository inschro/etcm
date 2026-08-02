# Stage 6 Diagnostics

Stage 6 adds:

- `E_CONSTRAINT`: a field value violates or cannot apply a non-path constraint.

The parameter-relation extension adds resolver-owned expression diagnostics:

- `E_PARAMETER_REFERENCE`: an invalid parameter path, self-reference, scalar
  traversal, or object terminal
- `E_EXPRESSION_TYPE`: incompatible expression operands or derived result type
- `E_DERIVED_CYCLE`: a cycle in local derived dependencies
- `E_DERIVED_ASSIGNMENT`: an implementation assignment to a derived field
- `E_EXPRESSION_EVALUATION`: safe expression evaluation failed

`E_CONSTRAINT` details for relational constraints contain the written
constraint, resolved operands, and substituted evaluation. These details are a
content contract; human-facing whitespace is not a byte-for-byte API.

Existing ownership remains:

- `E_TYPE_MISMATCH`: type compatibility and reference assignability
- `E_INVALID_PATH`: `Path` existence and kind policy
- `E_INVALID_OVERRIDE`: invalid policy declarations during resolution and
  disallowed assignments during validation
- `E_GENERATED_VIEW`: conversion cannot represent an already valid graph

`E_GENERATED_VIEW` also reports attempts to convert an unvalidated graph unless
the caller passes `force=True`.
