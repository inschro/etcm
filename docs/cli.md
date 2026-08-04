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

All commands accept the path policy option:

```bash
--path-exists allow_missing
--path-exists must_exist
```

The option sets the resolver default for `Path` fields whose field metadata uses
`path_exists="resolver"`.

`resolve`, `validate`, and `load` additionally accept:

```bash
--set PATH=VALUE          # repeatable
--force-overrides
--override-base DIRECTORY
```

`--set` uses ETCM literals with a bare-string fallback and accepts deep paths
through inline objects and selected references. `--force-overrides` authorizes
replacement of `force_only` fields but never bypasses `deny`. Relative external
`Path` values and explicit reference selector paths use `--override-base`,
which defaults to the current working directory. `validate-all` deliberately
does not accept these three options. See [Overrides](overrides.md).

## Output

- `resolve --format json` prints `ResolvedGraph.to_dict()` JSON. Defaults,
  references, and derived parameters are resolved, but constraints and path
  policies have not been validated and `validated` remains `false`.
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

Relational validation failures additionally show the written constraint,
resolved operand values, and substituted evaluation. Attempts to assign a
derived parameter show its defining expression. See
[Parameter Relations](parameter-relations.md) for examples and diagnostic
codes.
