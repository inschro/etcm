# ETCM CLI

The `etcm` command mirrors the public Python pipeline. Parser, resolver,
validation, and conversion behavior live in package APIs, not in CLI commands.

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

The option sets the resolver default for `Path` fields whose field metadata uses
`path_exists="resolver"`.

## Output

- `resolve --format json` prints `ResolvedGraph.to_dict()` JSON. The graph is
  resolved but not marked validated.
- `validate --format json` resolves, validates, and prints graph JSON with
  `validated: true`.
- `validate --short` resolves and validates, then prints `OK: <selector>` on
  success.
- `load --target ...` resolves, validates, builds the selected generated view,
  and prints the materialized config as JSON.

CLI output is always text. `load --target dataclass` and
`load --target pydantic` still serialize to JSON after building the selected
runtime object.

ETCM diagnostics are printed to stderr and exit with code `1`. Invalid CLI
usage follows normal `argparse` behavior.
