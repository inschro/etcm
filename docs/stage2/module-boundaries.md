# Stage 2 Module Boundaries

## Dependency Direction

```text
etcm.__init__
  -> etcm.resolve placeholders
  -> etcm.ir
  -> etcm.errors

etcm.syntax
  -> lark
  -> etcm.errors
  -> etcm.ir conversion later

etcm.resolve
  -> etcm.ir
  -> etcm.errors
  -> pathlib

etcm.codegen
  -> etcm.ir
  -> pydantic later

etcm.cli
  -> argparse later
  -> public API
```

## Modules

`etcm.syntax`

- Owns grammar loading, parse helpers, source span extraction, and syntax
  diagnostics.
- May import Lark.
- Must convert Lark-specific data before crossing into IR.

`etcm.ir`

- Owns parser-independent immutable dataclasses.
- Must not import Lark, Pydantic, argparse, or resolver modules.

`etcm.resolve`

- Owns resolver settings and future graph construction.
- Stage 2 contains only placeholders and local configuration validation.

`etcm.codegen`

- Owns future Pydantic/dataclass/dict views.
- Stage 2 contains an empty namespace or explicit placeholders only.

`etcm.cli`

- Owns future command wrappers.
- Stage 2 should not add console scripts unless needed for import tests.

`etcm.errors`

- Owns shared diagnostic base types and source-location-friendly messages.
- Stage 2 can define simple exception classes without complete diagnostics.

## Boundary Tests

Stage 2 tests should assert:

- importing `etcm.ir` does not import Lark
- importing `etcm.ir` does not import Pydantic
- importing `etcm` exposes the public placeholder API
- placeholder calls fail with clear `NotImplementedError`

