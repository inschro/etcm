# Stage 6 Diagnostics

Stage 6 adds:

- `E_CONSTRAINT`: a field value violates or cannot apply a non-path constraint.

Existing ownership remains:

- `E_TYPE_MISMATCH`: type compatibility and reference assignability
- `E_INVALID_PATH`: `Path` existence and kind policy
- `E_INVALID_OVERRIDE`: override policy
- `E_GENERATED_VIEW`: conversion cannot represent an already valid graph

`E_GENERATED_VIEW` also reports attempts to convert an unvalidated graph unless
the caller passes `force=True`.
