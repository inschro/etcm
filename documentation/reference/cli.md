# CLI reference

```console
$ etcm --help
usage: etcm [-h] {resolve,validate,validate-all,load} ...
```

Every command returns `0` on success. ETCM resolution, validation, or
serialization failures return `1`; invalid command usage returns `2`.

## Selectors

Commands that operate on one configuration require a complete selector:

```text
path/to/file.etcm#Spec:implementation
```

For example:

```text
pets.etcm#Pet:pepper
stays.etcm#Stay:pepper_weekend
```

## `validate`

Resolve and validate one implementation:

```console
$ etcm validate <selector> [options]
```

Use `--short` for a fast, human-readable check without graph serialization:

```console
$ etcm validate pets.etcm#Pet:pepper --short
OK: /path/to/pets.etcm#Pet:pepper
```

Without `--short`, the command writes the complete validated graph as JSON.

Options:

| Option | Meaning |
| --- | --- |
| `--short` | Print only the success line |
| `--format json` | JSON graph output; current default and only full format |
| `--path-exists POLICY` | `allow_missing` or `must_exist` resolver default |
| `--set PATH=VALUE` | Apply an override; repeatable |
| `--force-overrides` | Authorize external `force_only` replacements |
| `--override-base DIR` | Base for relative external paths and selectors |

## `validate-all`

Recursively discover and validate every concrete implementation below one or more
files or directories:

```console
$ etcm validate-all [PATH ...] [options]
```

With no path, scanning starts in the current directory. Spec-only files are
skipped; every discovered implementation is checked.

```console
$ etcm validate-all configs --verbose
OK: /project/configs/pets.etcm#Pet:pepper
OK: /project/configs/stays.etcm#Stay:pepper_weekend
2 total, 2 OK, 0 fail
```

Options:

| Option | Meaning |
| --- | --- |
| `-v`, `--verbose` | Print one result per selector |
| `--quiet` | Print only the final summary |
| `--format text` | Human-readable output; default |
| `--format json` | Totals and per-selector result objects |
| `--path-exists POLICY` | Resolver default for delegated `Path` fields |

`validate-all` intentionally does not accept override options.

## `load`

Run the complete pipeline, create a runtime view, and serialize that view as JSON:

```console
$ etcm load <selector> [options]
```

```console
$ etcm load stays.etcm#Stay:pepper_weekend --target dict
```

Targets:

| Target | View before JSON serialization |
| --- | --- |
| `dict` | Nested mapping; CLI default |
| `dataclass` | Generated dataclass hierarchy |
| `pydantic` | Generated Pydantic model hierarchy |

The final CLI output is JSON for every target. Use the
[Python API](python-api.md) when the application needs the runtime object itself.

`load` accepts the same path and override options as `validate`.

## `resolve`

Resolve one implementation and print its unvalidated graph as JSON:

```console
$ etcm resolve <selector> [options]
```

Use this command to inspect origins, typed edges, effective values, sources, and
path-resolution records before validation:

```console
$ etcm resolve stays.etcm#Stay:pepper_weekend --format json
```

`resolve` accepts:

| Option | Meaning |
| --- | --- |
| `--format json` | JSON graph output |
| `--path-exists POLICY` | Resolver path default |
| `--set PATH=VALUE` | Apply an override; repeatable |
| `--force-overrides` | Authorize `force_only` replacement |
| `--override-base DIR` | Resolve relative external values from `DIR` |

## Path policy

`--path-exists allow_missing` is the default. It affects only `Path` fields that
declare `path_exists="resolver"`. Fields that explicitly require or allow a path
keep their own policy.

Existing paths are always checked against their declared `path_kind`.

## Overrides

CLI override values use ETCM literal syntax:

```console
$ etcm load stays.etcm#Stay:pepper_weekend \
    --set nights=5 \
    --set pet.daily_food_grams=320
```

See the [override reference](overrides.md) for policies, reference selectors,
conflicts, and external path bases.

## JSON boundaries

CLI JSON supports null, Boolean, finite number, string, list, and string-keyed
object values. `Path` values are strings. Typed binary file content is projected
to `null`; unsupported decoded YAML values fail with `E_SERIALIZATION`.

`validate --short` and text `validate-all` do not serialize graph values.

## Diagnostics and status

Diagnostics are written to standard error and include a stable code, message, and
available source or graph context.

| Status | Meaning |
| --- | --- |
| `0` | Command completed successfully |
| `1` | ETCM resolution, validation, batch, or serialization failure |
| `2` | Invalid CLI usage reported by `argparse` |
