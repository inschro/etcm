# Stage 4 Diagnostics

Stage 4 parser errors use the shared `Diagnostic` and `ETCMError` types.

Parser-owned codes:

- `E_PARSE_UNEXPECTED_TOKEN`
- `E_PARSE_BAD_INDENT`
- `E_PARSE_TAB_INDENT`
- `E_DUPLICATE_SPEC`
- `E_DUPLICATE_FIELD`
- `E_DUPLICATE_IMPL`
- `E_SPEC_AND_SPEC_REF`
- `E_PARSE_SELECTOR`

Diagnostics should include source path, line, column, end line, end column, and
a concise deterministic message whenever the parser knows those values.

Resolver-owned errors stay out of Stage 4 even if a parsed selector points to a
missing file or incompatible implementation.
