# ETCM Manifest

ETCM is Typed Configuration Markup: a configuration language for defining,
validating, composing, and executing reproducible systems.

The core claim is simple:

> Configuration describes a typed graph of executable objects.

Most configuration systems eventually stop being simple key-value stores. In ML
experiments, distributed jobs, data pipelines, infrastructure tasks, and
production services, config files describe an interconnected system: an ML
model uses an optimizer, an optimizer uses a scheduler, a runtime uses a
launcher, a dataset uses a tokenizer, and a run captures the resolved graph for
audit and replay.

ETCM makes that graph explicit.

## Design Principles

1. One `.etcm` file defines exactly one spec source.
2. Specs are first-class types.
3. Implementations are first-class instances.
4. References are explicit and type-checked.
5. Validation belongs in configuration.
6. Inheritance is visible and deterministic.
7. Override behavior is defined by the spec, not by the caller.
8. The resolved graph is the reproducibility artifact.
9. Python bindings are generated from ETCM definitions.
10. Execution operates on typed objects, not anonymous dictionaries.

## File Shape

Each `.etcm` file either defines one spec inline or imports one external spec
with top-level `$spec`. It may define zero or more implementations of that spec.

```etcm
spec ResNetConfig:
  depth: int = Field(required=true, choices=[18, 34, 50, 101])
  width: int = Field(default=64, gt=0)
  pretrained: bool = Field(default=false)
  norm: str = Field(default="batch", choices=["batch", "layer", "group"])

impl resnet_18:
  depth: 18

impl resnet_50:
  depth: 50
```

The spec defines structure, defaults, validation, and override policy.
Implementations provide concrete named configurations.

Selectors use file fragments:

```text
models/resnet.etcm#resnet_50
```

When the fragment is omitted, ETCM resolves `#default`.

ETCM comments follow YAML-style `#` rules: `#` starts a comment only at the
beginning of a line or after whitespace, outside quoted strings. Attached
selector fragments such as `models/resnet.etcm#resnet_50` are not comments.

## Spec Inheritance

Specs may inherit from other specs. This is the basis for typed polymorphism:
a field that accepts `LRScheduler` may accept any implementation whose spec
inherits from `LRScheduler`.

```etcm
# schedulers/base.etcm
spec LRScheduler:
  warmup_steps: int = Field(default=0, ge=0)
  interval: str = Field(default="step", choices=["step", "epoch"])
```

```etcm
# schedulers/cosine.etcm
spec CosineLRScheduler <- schedulers/base.etcm:
  min_lr_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
  cycles: float = Field(default=0.5, gt=0.0)

impl default:
  warmup_steps: 1000
  min_lr_ratio: 0.01
```

Spec references do not use fragments because each `.etcm` file has exactly one
spec source.

## Spec Reuse

A file can import a spec without extending it by using top-level `$spec`.

```etcm
# optimizers/variants.etcm
$spec: specs/optimizer.etcm

impl adamw_fast:
  type: "adamw"
  lr: 3e-4

impl adamw_slow:
  type: "adamw"
  lr: 1e-4
```

`$spec` is not inheritance. It imports the external spec exactly as written:
the file may define implementations, but it may not add, remove, or modify spec
fields. Extending a spec requires explicit spec inheritance:

```etcm
spec Child <- parent.etcm:
```

## Implementation Inheritance

Implementations may inherit from compatible implementations. The child receives
the parent payload, then applies local values according to the target spec's
override policy.

```etcm
impl baseline:
  depth: 50
  width: 64
  norm: "batch"

impl larger <- baseline:
  width: 96
```

Inheritance may also target another file:

```etcm
impl custom <- models/resnet.etcm#resnet_50:
  width: 128
```

## References

Implementations may reference implementations of other specs. A reference is a
typed relationship, not a raw include.

```etcm
spec TrainConfig:
  model: ResNetConfig
  scheduler: LRScheduler
  epochs: int = Field(default=90, gt=0)

impl imagenet:
  $model: models/resnet.etcm#resnet_50
  $scheduler: schedulers/cosine.etcm#default
```

The compiler validates assignability:

```text
TrainConfig.scheduler expects LRScheduler
CosineLRScheduler inherits LRScheduler
Reference is valid
```

This is the main difference between ETCM and nested data composition. A resolved
reference carries identity, source location, spec type, implementation name,
and validated values.

## Field Validation

Validation is a first-class language feature.

```etcm
spec TrainingConfig:
  max_steps: int = Field(required=true, gt=0)
  lr: float = Field(default=3e-4, gt=0.0)
  optimizer: str = Field(default="adamw", choices=["adamw", "sgd"])
  dataset_path: Path = Field(path_exists="must_exist", path_kind="file")
```

V0 field metadata:

| Metadata | Meaning |
| --- | --- |
| `required` | Field must be supplied by defaults, inheritance, or local values |
| `default` | Field default value |
| `gt`, `ge`, `lt`, `le` | Numeric bounds |
| `min_length`, `max_length` | Collection or string length bounds |
| `regex` | String pattern constraint |
| `choices` | Finite set of valid values |
| `path_exists` | Path existence policy: `resolver`, `allow_missing`, or `must_exist` |
| `path_kind` | Path kind policy: `any`, `file`, or `dir` |
| `override` | Override behavior for inheritance and CLI changes |

## Path Fields

`Path` is a first-class v0 type, not just a string convention.

```etcm
spec DataConfig:
  input_path: Path = Field(path_exists="must_exist", path_kind="file")
  output_dir: Path = Field(path_exists="allow_missing", path_kind="dir")
  cache_path: Path = Field(path_exists="resolver")
```

Path values are resolved relative to the file where the value is declared. A
referenced implementation keeps its own path base, so moving a parent config
does not silently reinterpret child paths.

Field metadata controls existence checking:

| Policy | Meaning |
| --- | --- |
| `must_exist` | The resolver must fail if the path does not exist |
| `allow_missing` | The resolver accepts broken or future-created paths |
| `resolver` | The field delegates existence policy to the resolver default |

`path_kind` is checked when the path exists, and is also checked with
`must_exist`. For example, `path_kind="file"` rejects an existing directory.

The resolver also has a default path policy for fields that use
`path_exists="resolver"`:

```python
from etcm import Resolver

resolver = Resolver(path_exists="must_exist")
cfg = resolver.load("configs/train.etcm#smoke")
```

This allows a project to be permissive during authoring and strict in CI or
production without changing the config files.

Project-specific invariants still belong in application code when they depend
on runtime state or external resources. For example, "the tokenizer vocabulary
must match a model checkpoint" is not a core language invariant.

## Override Policy

Override behavior is part of the spec.

```etcm
spec RuntimeConfig:
  device: str = Field(default="auto", choices=["auto", "cpu", "cuda"])
  seed: int = Field(default=0, override="deny")
  tags: list[str] = Field(default=[], override="append")
  metadata: dict[str, str] = Field(default={}, override="merge")
```

V0 policies:

| Policy | Meaning |
| --- | --- |
| `allow` | Normal replacement behavior |
| `deny` | Field cannot be overridden after initial definition |
| `force_only` | Override requires an explicit force flag |
| `append` | Collection overrides append values |
| `merge` | Mapping overrides deep-merge values |

The point is auditability. A caller should not be able to silently replace a
seed, checkpoint URI, production account, or safety-critical runtime field
unless the spec explicitly permits it.

## Resolved Object Graph

ETCM resolves to an inspectable typed graph.

```text
TrainConfig(imagenet)
├── model: ResNetConfig(resnet_50)
└── scheduler: CosineLRScheduler(default)
```

Every node records:

- spec name and source file
- implementation name and source file
- inherited parents
- applied overrides
- referenced children
- validation result
- materialized runtime representation

The resolved graph is what should be saved beside experiment outputs,
checkpoints, build artifacts, or deployment records.

## Resolution Pipeline

ETCM processing is deterministic and observable:

1. Parse files into an AST.
2. Build spec symbols.
3. Apply spec inheritance or top-level `$spec` reuse.
4. Build implementation symbols.
5. Apply implementation inheritance.
6. Resolve references.
7. Apply explicit overrides under spec-owned policy.
8. Validate field constraints and reference assignability.
9. Materialize a typed graph.
10. Emit requested views: Pydantic, dataclass, dict, JSON Schema, graph.

Each stage should be separately inspectable by CLI tools.

## Python Integration

ETCM definitions are the source of truth. Users should not need to duplicate
schema definitions in Python just to get validation.

```python
from etcm import load

cfg = load("experiments/train.etcm#imagenet", target="pydantic")
```

V0 generated representations:

- `pydantic`: default Python validation and IDE-friendly object view
- `dataclass`: lightweight typed object view
- `dict`: JSON/YAML-compatible resolved payload
- `resolve`: node and edge metadata for inspection and tooling

Pydantic is the first target because it already gives Python projects strong
runtime validation and JSON Schema export.

## CLI

V0 command intent:

```bash
etcm resolve experiments/train.etcm#imagenet --format json
etcm validate experiments/train.etcm#imagenet
etcm validate experiments/train.etcm#imagenet --short
etcm load experiments/train.etcm#imagenet --target pydantic
```

Later extensions:

```bash
etcm sweep experiments/train.etcm#baseline
etcm submit experiments/train.etcm#baseline
etcm bindings experiments/train.etcm --target pydantic
```

## Non-Goals

ETCM v0 is not:

- a Hydra clone
- a general-purpose programming language
- an arbitrary Python object execution system
- a full CUE-style constraint engine
- a secrets manager
- a workflow scheduler

The core job is smaller and sharper: define, validate, compose, inspect, and
materialize typed configuration graphs.
