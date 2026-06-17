# Stage 3 Fixture Matrix

Fixtures are the executable language contract once parser and resolver code
exist. Stage 3 names the required corpus before implementation so the parser is
forced to satisfy user-facing use cases rather than the easiest grammar path.

Fixture paths are relative to `tests/fixtures/`.

## Naming Rules

- Valid examples live under `valid/`.
- Invalid examples live under `invalid/`.
- Golden outputs live under `golden/`.
- Multi-file examples use a subdirectory named after the behavior under test.
- Fixture names describe the behavior, not the implementation detail.
- A fixture may be parser-only, resolver-only, or codegen-facing; the matrix
  records which layer owns the first meaningful assertion.

## Valid Fixtures

| Fixture | First layer | Purpose |
| --- | --- | --- |
| `valid/inline_spec.etcm` | Parser | Inline `spec` with a minimal `impl`. Already present from Stage 2. |
| `valid/inline_spec_with_defaults.etcm` | Parser | Field defaults, `Field(...)` metadata, and override policy metadata. |
| `valid/spec_ref_impls.etcm` | Parser | Top-level `$spec` with local implementations. Already present from Stage 2. |
| `valid/spec_inheritance.etcm` | Parser | Spec inheritance by unique spec path without a fragment. |
| `valid/impl_inheritance.etcm` | Parser | Implementation inheritance by selector with `#impl`. |
| `valid/typed_refs/` | Resolver | Cross-file `$field` refs with assignable implementation targets. |
| `valid/path_policies/` | Resolver | `Path` fields with field-level `must_exist`, `allow_missing`, and delegated resolver policy. |
| `valid/nested_literals.etcm` | Parser | Lists, mappings, strings, numbers, booleans, null, and trailing commas where allowed. |
| `valid/comments_blank_lines.etcm` | Parser | YAML-style comments, quoted `#`, and blank lines inside and around blocks. |
| `valid/source_relative_paths/` | Resolver | Path values resolve relative to the source file that declared the value. |
| `valid/ml_train_run/` | Resolver | Realistic ML run with config fields for model, data, optimizer, and runtime settings. |
| `valid/service_settings/` | Resolver | Non-ML service config to prevent the language from becoming ML-only. |

## Invalid Fixtures

| Fixture | First layer | Expected diagnostic |
| --- | --- | --- |
| `invalid/malformed_syntax.etcm` | Parser | `E_PARSE_UNEXPECTED_TOKEN`. Already present from Stage 2. |
| `invalid/bad_indent.etcm` | Parser | `E_PARSE_BAD_INDENT`. |
| `invalid/tab_indent.etcm` | Parser | `E_PARSE_TAB_INDENT`. |
| `invalid/duplicate_spec.etcm` | Parser | `E_DUPLICATE_SPEC`. |
| `invalid/duplicate_field.etcm` | Parser | `E_DUPLICATE_FIELD`. Already present from Stage 2. |
| `invalid/duplicate_impl.etcm` | Parser | `E_DUPLICATE_IMPL`. |
| `invalid/spec_and_spec_ref.etcm` | Parser | `E_SPEC_AND_SPEC_REF`. |
| `invalid/missing_selector.etcm` | Resolver | `E_MISSING_SELECTOR`. |
| `invalid/malformed_literal.etcm` | Parser | `E_PARSE_UNEXPECTED_TOKEN` or `E_PARSE_LITERAL`. |
| `invalid/spec_cycle/` | Resolver | `E_SPEC_CYCLE`. |
| `invalid/impl_cycle.etcm` | Resolver | `E_IMPL_CYCLE`. |
| `invalid/ref_cycle/` | Resolver | `E_REF_CYCLE`. |
| `invalid/type_mismatch/` | Resolver | `E_TYPE_MISMATCH`. |
| `invalid/denied_override.etcm` | Resolver | `E_INVALID_OVERRIDE`. |
| `invalid/invalid_path_kind.etcm` | Resolver | `E_INVALID_PATH`. |
| `invalid/missing_path_must_exist.etcm` | Resolver | `E_INVALID_PATH`. |
| `invalid/path_selector_ambiguity.etcm` | Parser | `E_PARSE_SELECTOR`. |
| `invalid/spec_ref_fragment.etcm` | Parser | `E_PARSE_UNEXPECTED_TOKEN`. |
| `invalid/spec_inheritance_fragment.etcm` | Parser | `E_PARSE_UNEXPECTED_TOKEN`. |

## Behavior Coverage

The matrix must cover these v0 behaviors before parser work starts:

- exactly one inline `spec` or one top-level `$spec` per document
- zero or more `impl` blocks per document
- spec inheritance uses a unique path and does not require `#`
- implementation inheritance uses a full selector when needed
- `$field` refs point to implementation selectors, not arbitrary literals
- field assignment order is deterministic
- duplicate definitions fail locally before resolver graph construction
- YAML-style comments and blank lines are accepted where they do not change
  block meaning
- attached selector fragments are not parsed as comments
- tabs are rejected with a specific diagnostic unless a later stage explicitly
  adopts tab normalization
- `Path` syntax is parsed as data and validated only by the resolver
- resolver path policy combines field metadata and resolver settings

## Use Case Anchors

The valid corpus should include at least one fixture for each adoption target:

- ML experiment config: train run, data source, optimizer, and checkpoint path.
- Data pipeline config: source, transform, sink, and artifact directory.
- Service config: HTTP settings, storage settings, feature flags, and secrets
  references represented as strings or paths.
- Runtime config: worker count, device placement, log level, and output path.

These examples keep the project honest about being useful beyond a toy parser.
