# CLI reference

The `etcm` command mirrors the public Python pipeline. All commands operate on
explicit selectors and print text to standard output.

```console
$ etcm --help
usage: etcm [-h] {resolve,validate,validate-all,load} ...
```

## `resolve`

Resolve an implementation and print its unvalidated graph as JSON:

```console
$ etcm resolve <selector> [options]
```

```console
$ etcm resolve configs/train.etcm#TrainRun:smoke --format json
```

The graph contains defaults, inheritance, references, override audit data, loaded
typed files, and derived parameters. Its `validated` field is `false` because field
constraints, path policy, and assertions have not completed.

Options:

| Option | Meaning |
| --- | --- |
| `--format json` | Output format; JSON is currently the only choice |
| `--path-exists POLICY` | Resolver default: `allow_missing` or `must_exist` |
| `--set PATH=VALUE` | Apply an override; repeatable |
| `--force-overrides` | Authorize replacement of `force_only` fields |
| `--override-base DIR` | Base for relative external paths and selectors |

## `validate`

Resolve and validate one implementation:

```console
$ etcm validate <selector> [options]
```

Print the complete validated graph:

```console
$ etcm validate configs/train.etcm#TrainRun:smoke --format json
```

Print only a compact success message:

```console
$ etcm validate configs/train.etcm#TrainRun:smoke --short
OK: configs/train.etcm#TrainRun:smoke
```

`validate` accepts the same path and override options as `resolve`, plus `--short`.
The JSON graph has `validated: true`.

## `validate-all`

Discover and validate every concrete implementation below one or more paths:

```console
$ etcm validate-all [PATH ...] [options]
```

With no paths, scanning starts at the current directory:

```console
$ etcm validate-all
```

Files are scanned recursively by `.etcm` suffix. Every discovered implementation is
validated, while files containing only specs are skipped.

Text output prints failures followed by a summary:

```text
381 total, 379 OK, 2 fail
```

Options:

| Option | Meaning |
| --- | --- |
| `-v`, `--verbose` | Print one status line per selector |
| `--quiet` | Print only the final summary |
| `--format text` | Text output; the default |
| `--format json` | Totals and per-selector result objects |
| `--path-exists POLICY` | Resolver default for delegated `Path` fields |

`validate-all` does not accept `--set`, `--force-overrides`, or `--override-base`.

## `load`

Run the complete pipeline, build a runtime view, and serialize it as JSON:

```console
$ etcm load <selector> [options]
```

```console
$ etcm load configs/train.etcm#TrainRun:smoke --target dict
$ etcm load configs/train.etcm#TrainRun:smoke --target dataclass
$ etcm load configs/train.etcm#TrainRun:smoke --target pydantic
```

Targets:

| Target | Behavior before JSON serialization |
| --- | --- |
| `dict` | Build a nested mapping; the CLI default |
| `dataclass` | Build generated dataclass objects |
| `pydantic` | Build generated Pydantic models |

The CLI always emits JSON text after materializing the selected target. Use the
[Python API](python-api.md) when the application needs the runtime object itself.

`load` accepts `--path-exists`, all three override options, and `--target`.

## Path policy

All commands accept:

```text
--path-exists allow_missing
--path-exists must_exist
```

This sets the resolver default for `Path` fields declared with
`path_exists="resolver"`. A field that explicitly declares `must_exist` or
`allow_missing` keeps its own policy.

## Overrides

`resolve`, `validate`, and `load` accept:

```text
--set PATH=VALUE          repeatable
--force-overrides
--override-base DIRECTORY
```

Examples:

```console
$ etcm load configs/train.etcm#TrainRun:smoke --target dict \
    --set runtime.devices=2 \
    --set 'tags=["debug", "local"]'
```

`--set` values use ETCM literals with a bare-string fallback. Relative external
`Path` values, typed-file paths, and explicit reference selector paths use
`--override-base`, which defaults to the current working directory.

See the [override guide](../guides/overrides.md) for policy and reference-replacement
semantics.

## JSON boundaries

Typed `File[bytes]` leaves are emitted as `null` in graph and loaded-config JSON.
Python API values retain their exact bytes.

Safe YAML may decode values outside standard JSON, including dates, sets, binary
values, or mappings with non-string keys. If output contains one of those values,
the CLI fails with `E_SERIALIZATION` and identifies the output path rather than
stringifying it. `validate --short` does not serialize the graph and can still
succeed.

Read [typed files](../guides/typed-files.md) for the complete codec contract.

## Diagnostics and exit status

ETCM diagnostics are printed to standard error.

| Status | Meaning |
| --- | --- |
| `0` | Command completed successfully |
| `1` | ETCM resolution, validation, serialization, or batch failure |
| `2` | Invalid CLI usage reported by `argparse` |

Diagnostics include a stable error code, message, source location when available,
and contextual details. Relational failures also report the original expression,
resolved operands, and substituted evaluation.
