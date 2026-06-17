# Stage 5 Fixture Matrix

Stage 5 fixtures live under `tests/fixtures/valid`,
`tests/fixtures/invalid`, and `tests/fixtures/golden`.

## Valid Graph Fixtures

- `typed_refs`: typed reference assignment and graph edge emission.
- `spec_reuse`: `$spec` reuse across files.
- `spec_inheritance`: inherited spec fields and assignability.
- `impl_inheritance`: implementation inheritance and inherited values.
- `path_policies`: `Path` resolution, path kind checks, field policy, and
  resolver-level existence policy.
- `source_relative_paths`: nested selectors and path values resolved relative
  to their declaring files.

## Invalid Diagnostic Fixtures

- `missing_selector`: selector source or implementation cannot be found.
- `spec_cycle`: cyclic spec inheritance or `$spec` reuse.
- `impl_cycle`: cyclic implementation inheritance.
- `ref_cycle`: cyclic object references.
- `type_mismatch`: literal or reference does not satisfy the field type.
- `missing_required`: required field is absent after defaults and inheritance.
- `denied_override`: local assignment violates inherited field override policy.
- `invalid_path_kind`: existing path does not match declared kind.
- `missing_path_must_exist`: required path does not exist.

## Goldens

Graph goldens are normalized through `ResolvedGraph.to_dict(path_base=...)`.
Diagnostic goldens keep resolver-owned error codes, spans, selectors, graph
paths, and structured details stable.
