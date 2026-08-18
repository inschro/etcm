# ETCM Overrides

ETCM uses one override pipeline for implementation assignments, Python calls,
and command-line `--set` values. An override path is a dot-separated field path
rooted at the selected implementation:

```text
dataloader.sampler.seed
runtime.launcher.processes
optimizer.schedule.warmup_steps
```

Paths may cross inline objects and typed references. ETCM patches referenced
objects with copy-on-write, so changing a descendant does not mutate a parent
implementation or another reference to the same implementation. Only the leaf
field's override policy is applied.

## Implementation Overrides

Implementations use the normal assignment colon:

```etcm
spec Training:
  $dataloader: dataloader.etcm#DataLoader

  impl debug:
    $dataloader: dataloader.etcm#DataLoader:train
    dataloader.sampler.seed: 7
```

Indented and dotted forms remain equivalent:

```etcm
impl debug:
  dataloader:
    sampler:
      seed: 7
```

A reference must have a selected implementation before a descendant can be
patched. A whole-reference selection and its descendant patches may appear in
either source order; ETCM always applies the shallower reference selection
first. Exact duplicate paths remain errors. Any other value-versus-descendant
overlap is a path conflict.

## Python API

`resolve()` and `load()`, including their `Resolver` method forms, accept either
a mapping of native Python values or a sequence of `PATH=VALUE` strings:

```python
from etcm import load, resolve

graph = resolve(
    "configs/train.etcm#Training:debug",
    overrides={
        "dataloader.sampler.seed": 11,
        "runtime.processes": 4,
    },
)

cfg = load(
    "configs/train.etcm#Training:debug",
    target="pydantic",
    overrides=[
        "dataloader.sampler.seed=11",
        "runtime.processes=4",
    ],
)
```

The sequence form is suitable for direct use with an `argparse` append action:

```python
parser.add_argument("--set", dest="overrides", action="append", default=[])
args = parser.parse_args()
cfg = load(selector, overrides=args.overrides)
```

String-list values use ETCM literals: numbers, quoted strings, booleans,
`null`, lists, and maps have the same syntax as a file. Text that is not an
ETCM literal is treated as a bare string:

```text
workers=8
enabled=true
tags=["debug", "local"]
limits={cpu: 4, memory: 16}
label=quick experiment
```

Malformed text that starts like a structured, numeric, Boolean, or null literal
is rejected instead of silently becoming a string.

## CLI

`resolve`, `validate`, and `load` accept repeatable `--set` options:

```bash
etcm resolve configs/train.etcm#Training:debug \
  --set dataloader.sampler.seed=11

etcm validate configs/train.etcm#Training:debug \
  --set runtime.processes=4

etcm load configs/train.etcm#Training:debug --target dict \
  --set tags='["debug", "local"]'
```

`validate-all` intentionally does not accept overrides because one patch set
does not have a stable meaning across unrelated implementations.

## Reference Replacement

A field that holds a typed reference can be replaced as a whole. External
overrides express the implementation selector as a string:

```python
cfg = load(
    "configs/train.etcm#Training:debug",
    overrides=[
        "dataloader=:production",
        "dataloader.sampler.seed=11",
    ],
)
```

Supported selector values are `:implementation`, `#Spec:implementation`, and
`path.etcm#Spec:implementation`. A pathless selector uses the current reference
target as its anchor, or the field's declared spec reference when the value is
not yet set. An explicit selector path is resolved from `override_base`.

## Relative Paths

External `Path` values, `File[...]` paths, and explicit reference
selector paths are resolved from `override_base`. It defaults to the process's
current working directory:

```python
cfg = load(
    selector,
    overrides={"checkpoint": "runs/latest.ckpt"},
    override_base="/srv/project",
)
```

The CLI exposes the same setting:

```bash
etcm load "$selector" \
  --override-base /srv/project \
  --set checkpoint=runs/latest.ckpt
```

Typed files are opened only after local and external overrides are fully
composed. A replaced file default is never read. With `append` or `merge`, each
file path keeps the base of the source that contributed it. Decoded contents
are not valid deep-override targets; only the ETCM field or an
ETCM-owned surrounding container can be overridden.

## Override Policies

The target spec owns the policy. Defaults, inherited values, implementation
assignments, and external patches all use the same rules:

| Policy | Existing value | First value for an unset field |
| --- | --- | --- |
| `allow` | replace | set |
| `deny` | reject, even when the new value is equal | unavailable because `deny` requires an inline default |
| `force_only` | require explicit external force authorization | set without force |
| `append` | append list items | set |
| `merge` | recursively merge string-keyed maps | set |

Only external callers can authorize `force_only` replacement:

```python
cfg = load(selector, overrides={"seed": 42}, force_overrides=True)
```

```bash
etcm load "$selector" --set seed=42 --force-overrides
```

`force_overrides` never bypasses `deny`. A local implementation assignment also
cannot authorize `force_only`.

## Resolution and Audit

The visible order is:

```text
1. Resolve defaults and implementation inheritance.
2. Apply local implementation patches.
3. Apply external Python or CLI patches.
4. Load effective typed files.
5. Recompute derived parameters.
6. Validate types, policies, paths, and constraints.
7. Materialize the requested view.
```

External leaf values have `origin="external"` in the resolved graph. Their
audit record includes the override base, previous value and origin when a value
was replaced, and whether a `force_only` replacement was authorized.

Override paths do not support a synthetic root prefix, collection indexing,
attribute access outside typed fields, or arbitrary expressions.
