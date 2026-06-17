# Stage 5 Diagnostics

Resolver-owned diagnostics:

- `E_MISSING_SELECTOR`
- `E_SPEC_CYCLE`
- `E_IMPL_CYCLE`
- `E_REF_CYCLE`
- `E_TYPE_MISMATCH`
- `E_MISSING_FIELD`
- `E_INVALID_OVERRIDE`
- `E_INVALID_PATH`

Diagnostics should include source path, span, selector, graph path, and
structured details when known. Path diagnostics include original path text,
resolved path, declaring source file, field policy, resolver policy, expected
kind, and existence result.
