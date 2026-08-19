# Override reference

Overrides change a selected implementation for one resolution. The
[advanced tutorial](../tutorials/advanced.md#put-ownership-rules-in-the-spec)
shows the policies in one application; this page defines every input form and
policy.

## Input forms

Python accepts a mapping or a sequence of `PATH=VALUE` strings:

```python
from etcm import load

load(selector, overrides={"nights": 5})
load(selector, overrides=["nights=5", "pet.daily_food_grams=320"])
```

CLI commands accept repeatable `--set` values:

```console
$ etcm load "$selector" --set nights=5 --set pet.daily_food_grams=320
```

Mapping values may contain native scalar values, `Path`, lists, and string-keyed
mappings. String and CLI values use ETCM literal syntax.

`validate-all` does not accept overrides because one patch set cannot be applied
meaningfully to every discovered implementation.

## Paths

Paths contain dot-separated declared field names:

```text
nights
pet.daily_food_grams
runtime.launcher.processes
```

They may descend through inline objects and typed references. They do not support
a synthetic `root` prefix, list indexes, mapping keys, runtime attributes, or
expressions.

## Composition order

Values compose in this order:

1. declaration defaults
2. inherited implementation values
3. local implementation assignments
4. external Python or CLI overrides

At each replacement, the field's spec-owned policy decides whether the new value
is accepted. Derived fields are calculated after all accepted overrides and cannot
be assigned.

## Policies

Declare policy beside the field:

```text
ordinary: int = 1 [override="allow"]
fixed: int = 1 [override="deny"]
guarded: int = 1 [override="force_only"]
tags: list[str] = [] [override="append"]
metadata: dict[str, str] = {} [override="merge"]
```

| Policy | Replacing an existing value | First assignment to an unset field |
| --- | --- | --- |
| `allow` | Replace | Set |
| `deny` | Reject | Not applicable; declaration default required |
| `force_only` | Require authorized external force | Set without force |
| `append` | Append list items | Set |
| `merge` | Recursively merge mappings | Set |

`allow` is the default.

### `deny`

`deny` requires a declaration default and rejects every later assignment,
including assignment of the same value. Force authorization never bypasses it.

### `force_only`

Only an external caller can authorize replacement:

```python
load(
    selector,
    overrides={"guarded": 2},
    force_overrides=True,
)
```

```console
$ etcm load "$selector" --set guarded=2 --force-overrides
```

An implementation may make the first assignment to an unset `force_only` field
without force because no existing value is being replaced.

### `append`

`append` requires exactly `list[T]`. New items are appended in source order. A
nullable union such as `list[T] | null` is not a valid `append` declaration.

### `merge`

`merge` requires exactly `dict[str, T]`. Mappings combine recursively; a local
non-mapping leaf replaces the previous leaf. Nullable mapping unions are not
accepted for this policy.

## Typed reference replacement

Override a reference with a selector string:

```python
load(
    selector,
    overrides={
        "pet": "pets.etcm#Pet:luna",
    },
)
```

CLI string values that parse as implementation selectors can replace typed
references. The target must satisfy the declared spec.

Selecting a reference and patching one of its descendants in the same input is
allowed. ETCM applies the shallower selection first.

## External path base

Relative `Path`, `File[...]`, and explicit selector values supplied externally need
a caller-owned base directory:

```python
load(selector, overrides=patches, override_base="/srv/project")
```

```console
$ etcm load "$selector" --override-base /srv/project --set photo=assets/pet.jpg
```

Without `override_base`, relative external paths use the process working directory.
Values inherited from ETCM files keep their own source-file base.

## Conflicts

One override input cannot assign the same canonical path twice or assign both an
object and one of its descendants:

```text
feeding={meals: 2}
feeding.meals=3
```

The typed-reference selection plus descendant-patch case is the deliberate
exception.

## Audit records

`ResolvedValue` records whether an override was applied and may include the
previous origin and value, local value, external base, and force authorization:

```python
from etcm import resolve

graph = resolve(selector, overrides={"nights": 5})
root = next(node for node in graph.nodes if node.graph_path == "root")
audit = root.field_values["nights"]

assert audit.applied_override is True
assert audit.previous_value == 2
assert audit.local_value == 5
```
