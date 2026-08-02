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

1. One `.etcm` file may define multiple spec sources.
2. Specs are first-class types.
3. Implementations are first-class instances.
4. References are explicit and type-checked.
5. Validation belongs in configuration.
6. Inheritance is visible and deterministic.
7. Override behavior is defined by the spec, not by the caller.
8. The resolved graph is the reproducibility artifact.
9. Python bindings are generated from ETCM definitions.
10. Execution operates on typed objects, not anonymous dictionaries.
11. Configured, defaulted, and derived values have distinct visible semantics.

## File Shape

Each `.etcm` file either defines one or more specs inline or imports one
external spec with top-level `$spec`. Inline implementations are owned by the
spec block they are indented under. Top-level implementations are only valid in
`$spec` implementation files.

```etcm
spec ResNetConfig:
  depth: int [in [18, 34, 50, 101]]
  width: int = 64 [>0]
  pretrained: bool = false
  norm: str = "batch" [in ["batch", "layer", "group"]]

  impl resnet_18:
    depth: 18

  impl resnet_50:
    depth: 50
```

The spec defines structure, defaults, validation, and override policy.
Implementations provide concrete named configurations.

Field paths may be written with indentation, dots, or a mixture of both. These
declarations are equivalent and produce the same anonymous `optimizer` object:

Indented:

```etcm
optimizer:
  learning_rate: float = 1e-3
```

Dotted:

```etcm
optimizer.learning_rate: float = 1e-3
```

Dotted prefixes create anonymous containers. An explicit indented container may
be combined with other dotted descendants:

```etcm
optimizer:
  learning_rate: float = 1e-3

optimizer.weight_decay: float = 0.0
$optimizer.schedule: schedulers/base.etcm#LRScheduler
```

Implementations accept the same two path forms:

```etcm
impl fast:
  optimizer.learning_rate: 3e-3
  optimizer:
    weight_decay: 0.01
    $schedule: schedulers/cosine.etcm#CosineLRScheduler:default
```

Paths inside an indented block are relative to that block. `$` marks the
terminal field as a typed reference, so `$optimizer.schedule` and an indented
`optimizer` block containing `$schedule` are equivalent. Duplicate canonical
leaf paths and value-versus-container conflicts are errors.

Named `impl` blocks belong directly to a real spec; they cannot appear inside
an anonymous field declaration. A `$field` reference may be selected as a
whole, including at a nested inline path, but its resolved target is opaque to
implementation writes. For example, `model.hidden_size: 512` is invalid when
`$model` is a referenced field.

Selectors use file fragments:

```text
models/resnet.etcm#ResNetConfig
models/resnet.etcm#ResNetConfig:resnet_50
```

The selector shape determines its target. A spec selector ends at the spec
name; an implementation selector always includes `:implementation`, including
`:default`. Same-file selectors omit the path as `#Spec` or
`#Spec:implementation`. Within an active spec, `:implementation` is the concise
form for one of that spec's local implementations.

ETCM comments follow YAML-style `#` rules outside selector positions and quoted
strings: `#` starts a comment at line start or after whitespace. Where the
grammar expects a selector, `#Spec` instead begins a same-file selector.

## Spec Inheritance

Specs may inherit from other specs. This is the basis for typed polymorphism:
a field that accepts `LRScheduler` may accept any implementation whose spec
inherits from `LRScheduler`.

```etcm
# schedulers/base.etcm
spec LRScheduler:
  warmup_steps: int = 0 [>=0]
  interval: str = "step" [in ["step", "epoch"]]
```

```etcm
# schedulers/cosine.etcm
spec CosineLRScheduler <- schedulers/base.etcm#LRScheduler:
  min_lr_ratio: float = 0.0 [>=0.0; <=1.0]
  cycles: float = 0.5 [>0.0]

  impl default:
    warmup_steps: 1000
    min_lr_ratio: 0.01
```

Spec references use the same selector form as every other spec position:
`path/to/file.etcm#SpecName`.

## Spec Reuse

A file can import a spec without extending it by using top-level `$spec`.

```etcm
# optimizers/variants.etcm
$spec: specs/optimizer.etcm#Optimizer

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
spec Child <- parent.etcm#Parent:
```

## Implementation Inheritance

Implementations may inherit from compatible implementations. The child receives
the parent payload, then applies local values according to the target spec's
override policy.

```etcm
spec ResNetConfig:
  depth: int
  width: int
  norm: str = "batch"

  impl baseline:
    depth: 50
    width: 64
    norm: "batch"

  impl larger <- :baseline:
    width: 96
```

Inheritance may also target another file:

```etcm
spec ResNetConfig:
  width: int

  impl custom <- models/resnet.etcm#ResNetConfig:resnet_50:
    width: 128
```

## References

Implementations may reference implementations of other specs. A reference is a
typed relationship, not a raw include.

```etcm
spec TrainConfig:
  $model: models/resnet.etcm#ResNetConfig
  $scheduler: schedulers/cosine.etcm#LRScheduler
  epochs: int = 90 [>0]

  impl imagenet:
    $model: models/resnet.etcm#ResNetConfig:resnet_50
    $scheduler: schedulers/cosine.etcm#CosineLRScheduler:default
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
  max_steps: int [>0]
  lr: float = 3e-4 [>0.0]
  optimizer: str = "adamw" [in ["adamw", "sgd"]]
  dataset_path: Path [path_exists="must_exist"; path_kind="file"]
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

Numeric comparison syntax is represented as ordered validation constraints,
not metadata. Constraints can reference sibling or nested object parameters:

```etcm
spec ModelConfig:
  $dataloader: dataloader.etcm#DataLoaderConfig
  attention_heads: int [>0]
  hidden_size: int [% @attention_heads == 0]
  seed_confirmation: int [== @dataloader.sampler.seed]
```

ETCM also distinguishes defaults from derived values:

```etcm
optional: int = 10
total: int := @left + @right
```

A default may be replaced under the field's override policy. A derived value is
computed by ETCM during resolution and cannot be assigned by an implementation.
See [Parameter Relations](parameter-relations.md) for the complete expression,
dotted-path, type, cycle, timing, and diagnostic contract.

## Path Fields

`Path` is a first-class v0 type, not just a string convention.

```etcm
spec DataConfig:
  input_path: Path [path_exists="must_exist"; path_kind="file"]
  output_dir: Path [path_exists="allow_missing"; path_kind="dir"]
  cache_path: Path [path_exists="resolver"]
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
cfg = resolver.load("configs/train.etcm#TrainConfig:smoke")
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
  device: str = "auto" [in ["auto", "cpu", "cuda"]]
  seed: int = 0 [override="deny"]
  tags: list[str] = [] [override="append"]
  metadata: dict[str, str] = {} [override="merge"]
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
8. Compute derived parameters in dependency order.
9. Validate field types, paths, reference assignability, and constraints.
10. Materialize a typed graph.
11. Emit requested views: Pydantic, dataclass, dict, and graph.

Each stage should be separately inspectable by CLI tools.

## Python Integration

ETCM definitions are the source of truth. Users should not need to duplicate
schema definitions in Python just to get validation.

```python
from etcm import load

cfg = load("experiments/train.etcm#TrainConfig:imagenet", target="pydantic")
```

V0 generated representations:

- `pydantic`: default Python validation and object-style runtime view
- `dataclass`: lightweight typed object view
- `dict`: JSON/YAML-compatible resolved payload
- `resolve`: node and edge metadata for inspection and tooling

Pydantic is the first target because it already gives Python projects strong
runtime validation and a familiar model surface. Direct JSON Schema export from
ETCM specs is a later adoption feature.

## CLI

V0 command intent:

```bash
etcm resolve experiments/train.etcm#TrainConfig:imagenet --format json
etcm validate experiments/train.etcm#TrainConfig:imagenet
etcm validate experiments/train.etcm#TrainConfig:imagenet --short
etcm load experiments/train.etcm#TrainConfig:imagenet --target pydantic
```

Later extensions:

```bash
etcm sweep experiments/train.etcm#TrainConfig:baseline
etcm submit experiments/train.etcm#TrainConfig:baseline
etcm bindings experiments/train.etcm#TrainConfig --target pydantic
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
