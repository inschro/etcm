# ETCM CLI

The `etcm` command mirrors the public Python pipeline. Parser, resolver,
validation, and conversion behavior live in package APIs, not in CLI commands.

## Commands

```bash
etcm resolve <selector> --format json
etcm validate <selector> --format json
etcm validate <selector> --short
etcm validate-all [PATH ...]
etcm validate-all [PATH ...] --verbose
etcm validate-all [PATH ...] --quiet
etcm validate-all [PATH ...] --format json
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
- `validate-all` recursively scans `.etcm` files under the provided paths, or
  the current directory when no path is provided. It validates every concrete
  implementation selector it discovers and skips spec-only files.
- `validate-all` default text output prints failures first, then a summary such
  as `381 total, 379 OK, 2 fail`.
- `validate-all --verbose` also prints one status line per validated selector.
- `validate-all --quiet` prints only the final summary.
- `validate-all --format json` prints totals and per-artifact result objects.
- `load --target ...` resolves, validates, builds the selected generated view,
  and prints the materialized config as JSON.

CLI output is always text. `load --target dataclass` and
`load --target pydantic` still serialize to JSON after building the selected
runtime object.

ETCM diagnostics are printed to stderr and exit with code `1`. Invalid CLI
usage follows normal `argparse` behavior.
