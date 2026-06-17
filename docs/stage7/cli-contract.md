# Stage 7 CLI Contract

The CLI mirrors the public Python pipeline:

```text
selector -> resolve() -> graph
selector -> resolve() -> validate() -> validated graph
selector -> resolve() -> validate() -> convert(target) -> materialized config
```

## Commands

```bash
etcm resolve <selector> --format json
etcm validate <selector> --format json
etcm validate <selector> --short
etcm load <selector> --target dict
etcm load <selector> --target dataclass
etcm load <selector> --target pydantic
```

All commands accept:

```bash
--path-exists allow_missing
--path-exists must_exist
```

## Semantics

- `resolve` calls `Resolver(...).resolve(selector)` and prints graph JSON with
  `validated: false`.
- `validate` calls `Resolver(...).validate(resolve(selector))` and prints graph
  JSON with `validated: true`.
- `validate --short` performs the same validation but prints only
  `OK: <selector>`.
- `load` calls `Resolver(...).load(selector, target=...)` and prints the
  materialized config as JSON.

`--target` is valid only for `load`. `--format` is currently `json` only.

## Errors

ETCM diagnostics are printed to stderr and return exit code `1`.

Invalid command usage follows normal `argparse` behavior and exits with code
`2`.
