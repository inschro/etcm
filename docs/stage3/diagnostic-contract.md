# Diagnostic Contract

Diagnostics are part of the public API. They must be stable enough for tests and
clear enough that users can fix a config without reading parser internals.

## Required Fields

Every diagnostic should carry:

- `code`: stable machine-readable code
- `message`: concise human-readable message
- `source_path`: path to the source file when known
- `span`: line and column range when known
- `selector`: selector involved in the failure when known
- `graph_path`: resolved graph path when known
- `details`: structured metadata for programmatic consumers

If a field is not known at the detection layer, use `null` rather than omitting
the key in JSON golden outputs.

## Error Codes

| Code | Layer | Meaning |
| --- | --- | --- |
| `E_PARSE_UNEXPECTED_TOKEN` | Parser | Syntax cannot continue at the current token. |
| `E_PARSE_BAD_INDENT` | Parser | Indentation does not match the block structure. |
| `E_PARSE_TAB_INDENT` | Parser | A tab was used for indentation in v0. |
| `E_PARSE_LITERAL` | Parser | Literal syntax is malformed. |
| `E_PARSE_SELECTOR` | Parser | Selector syntax is malformed or ambiguous. |
| `E_DUPLICATE_SPEC` | Parser | A document defines more than one inline spec. |
| `E_DUPLICATE_FIELD` | Parser | A spec defines the same field more than once. |
| `E_DUPLICATE_IMPL` | Parser | A document defines the same implementation more than once. |
| `E_SPEC_AND_SPEC_REF` | Parser | A document contains both inline `spec` and top-level `$spec`. |
| `E_MISSING_SELECTOR` | Resolver | A referenced selector cannot be found. |
| `E_SPEC_CYCLE` | Resolver | Spec inheritance contains a cycle. |
| `E_IMPL_CYCLE` | Resolver | Implementation inheritance contains a cycle. |
| `E_REF_CYCLE` | Resolver | Field references contain a cycle. |
| `E_TYPE_MISMATCH` | Resolver | A literal or referenced implementation is not assignable to the field type. |
| `E_CONSTRAINT` | Resolver | A field value violates a non-path field constraint. |
| `E_INVALID_OVERRIDE` | Resolver | An assignment or CLI override violates override policy. |
| `E_INVALID_PATH` | Resolver | A `Path` value violates existence or kind policy. |
| `E_GENERATED_VIEW` | Codegen | A generated view cannot represent the resolved graph. |

## Layer Ownership

Parser diagnostics own:

- token, indentation, and literal shape errors
- local duplicate definitions
- the inline `spec` versus top-level `$spec` exclusivity rule
- selector token ambiguity

Resolver diagnostics own:

- missing files and missing selectors
- inheritance and ref cycles
- assignability and type errors
- override policy errors
- `Path` existence and kind checks

Generated-view diagnostics own:

- failures to materialize an already valid resolved graph as Pydantic,
  dataclass, or dict output

CLI diagnostics do not own new error categories. The CLI formats diagnostics
returned by the Python API and maps success or failure to process exit codes.

## Message Rules

- Put the failing user-facing name in the message.
- Avoid parser-library terminology in public messages.
- Include the source file and span in rendered text when available.
- Include the selector chain for resolver cycles.
- Include original path text, resolved path, declaring source file, existence
  policy, and expected kind for path errors.
- Keep messages deterministic so text golden files stay reviewable.

## Path Error Details

`E_INVALID_PATH` diagnostics must include:

- `original`: path string as written in the config
- `declaring_source_path`: source file that declared the value
- `resolved_path`: absolute or fixture-root-relative resolved path
- `field_policy`: field-level path policy
- `resolver_policy`: resolver-level path policy
- `expected_kind`: `file`, `dir`, or `any`
- `exists`: boolean when known

This is required because `Path` is a v0 feature, not a later convenience.
