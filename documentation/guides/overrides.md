# Overrides

ETCM uses one override pipeline for declaration defaults, implementation
assignments, implementation inheritance, Python calls, and CLI `--set` values. The
target spec owns how an existing value may be changed.

## Deep field paths

An override path is dot-separated and rooted at the selected implementation:

```text
dataloader.sampler.seed
runtime.launcher.processes
optimizer.schedule.warmup_steps
```

Paths can cross inline objects and typed references. Referenced children are patched
copy-on-write, so one override never mutates the implementation used as its source.

## Implementation assignments

Implementations use normal `field: value` assignments:

```text
spec Training:
  $dataloader: dataloader.etcm#DataLoader

  impl debug:
    $dataloader: dataloader.etcm#DataLoader:train
    dataloader.sampler.seed: 7
```

The equivalent indented form is:

```text
impl debug:
  $dataloader: dataloader.etcm#DataLoader:train
  dataloader:
    sampler:
      seed: 7
```

A referenced implementation must be selected before its descendant can be patched.
The reference selection and descendant patch may appear in either source order;
ETCM applies shallower selections first.

## Python overrides

`resolve()` and `load()`, including their `Resolver` methods, accept a mapping of
native values:

```python
from etcm import load

cfg = load(
    "configs/train.etcm#Training:debug",
    overrides={
        "dataloader.sampler.seed": 11,
        "runtime.processes": 4,
    },
)
```

Supported native values are `None`, Boolean, integer, float, string, `Path`, list,
and string-keyed mapping. They are normalized into ETCM literals before being
applied.

The API also accepts a sequence of `PATH=VALUE` strings:

```python
cfg = load(
    "configs/train.etcm#Training:debug",
    overrides=[
        "dataloader.sampler.seed=11",
        "runtime.processes=4",
    ],
)
```

String-list values use ETCM literal syntax:

```text
workers=8
enabled=true
tags=["debug", "local"]
limits={cpu: 4, memory: 16}
label=quick experiment
```

Text that is not an ETCM literal becomes a bare string. Text beginning like a
structured, numeric, Boolean, or null literal must be valid literal syntax; malformed
input is rejected rather than silently converted to a string.

## CLI overrides

`resolve`, `validate`, and `load` accept repeatable `--set` flags:

```console
$ etcm validate configs/train.etcm#Training:debug \
    --set dataloader.sampler.seed=11 \
    --set runtime.processes=4
```

Quote lists, maps, or strings as required by your shell:

```console
$ etcm load configs/train.etcm#Training:debug --target dict \
    --set 'tags=["debug", "local"]'
```

`validate-all` deliberately has no override options because one patch set has no
stable meaning across unrelated specs and implementations.

## Replacing a reference

A caller can replace a typed reference as a whole and then patch the selected child:

```python
cfg = load(
    "configs/train.etcm#Training:debug",
    overrides=[
        "dataloader=:production",
        "dataloader.sampler.seed=11",
    ],
)
```

Reference override values can use:

- `:implementation`
- `#Spec:implementation`
- `path.etcm#Spec:implementation`

A pathless selector uses the current reference as its anchor, or the declared spec
reference when no value has been selected yet. An explicit selector path is resolved
from `override_base`.

## Relative external paths

External `Path` values, `File[...]` paths, and explicit reference selector paths are
resolved relative to `override_base`. It defaults to the process's current working
directory:

```python
cfg = load(
    "configs/train.etcm#Training:debug",
    overrides={"checkpoint": "runs/latest.ckpt"},
    override_base="/srv/project",
)
```

```console
$ etcm load configs/train.etcm#Training:debug \
    --override-base /srv/project \
    --set checkpoint=runs/latest.ckpt
```

Every contributed path retains its own base through append and merge operations.
Effective typed files are opened only after overrides are composed, so a replaced
file default is never loaded.

## Override policies

Declare policy beside the field:

```text
spec Runtime:
  device: str = "auto" [override="allow"]
  seed: int = 0 [override="deny"]
  checkpoint: Path = "latest.ckpt" [override="force_only"]
  tags: list[str] = [] [override="append"]
  metadata: dict[str, str] = {} [override="merge"]
```

| Policy | Existing value | First value for an unset field |
| --- | --- | --- |
| `allow` | Replace | Set |
| `deny` | Reject | Not applicable; an inline default is required |
| `force_only` | Require explicit external authorization | Set without force |
| `append` | Append list items | Set |
| `merge` | Recursively merge string-keyed maps | Set |

The default policy is `allow`.

### Deny

`deny` requires a declaration default and rejects every later assignment, even an
assignment of the same value. An implementation named `default` receives no special
privilege.

### Force-only

Only an external Python or CLI caller can authorize replacement of an existing
`force_only` value:

```python
cfg = load(
    selector,
    overrides={"checkpoint": "approved.ckpt"},
    force_overrides=True,
)
```

```console
$ etcm load "$selector" \
    --set checkpoint=approved.ckpt \
    --force-overrides
```

Force authorization never bypasses `deny`. A first assignment to an unset
`force_only` field establishes its value without force because nothing is being
replaced.

### Append and merge

`append` requires exactly `list[T]`. Each new list is appended to the existing list.
`merge` requires exactly `dict[str, T]`. Nested mappings combine recursively, while
a local non-mapping leaf replaces the previous leaf.

Nullable unions such as `list[T] | null` and `dict[str, T] | null` are not valid
declarations for these policies.

## Conflicts

Within one override source, exact duplicate paths are rejected. Assigning a value
and one of its descendants also conflicts:

```text
nested={value: 2}
nested.value=3
```

The deliberate exception is selecting a typed reference and then patching one of
its descendants.

Override paths do not support a synthetic root prefix, list indexing, mapping-key
traversal, runtime attributes, or expressions.

## Audit data

The resolved graph records whether a value was overridden and, when applicable:

- the previous origin and value
- the locally contributed value
- the external override base
- whether `force_only` replacement was authorized

```python
from etcm import resolve

graph = resolve(selector, overrides={"runtime.processes": 4})
runtime = next(node for node in graph.nodes if node.graph_path == "root.runtime")
audit = runtime.field_values["processes"]

print(audit.applied_override)
print(audit.previous_origin)
print(audit.local_value)
```

Parent values reset their per-node override marker when inherited, so each node's
audit record describes composition at that node rather than replaying all ancestor
history.
