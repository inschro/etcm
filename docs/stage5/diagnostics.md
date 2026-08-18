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
- `E_FILE_LOAD`

Diagnostics should include source path, span, selector, graph path, and
structured details when known. Path diagnostics include original path text,
resolved path, declaring source file, field policy, resolver policy, expected
kind, and existence result.

File-load diagnostics keep the primary source location on the ETCM value and
include its original and resolved path, declared codec, and failure reason.
Structured parsers report external line/column; strict UTF-8 errors report byte
offsets. Invalid file type shapes and non-path values use `E_TYPE_MISMATCH`.
