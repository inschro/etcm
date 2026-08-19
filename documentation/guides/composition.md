# Composition

ETCM composes typed objects through spec inheritance, implementation inheritance,
spec reuse, and reference fields. Every relationship uses an explicit selector and
is preserved in the resolved graph.

## Typed reference fields

A `$` field declares that its value must be an implementation of another spec:

```text title="train.etcm"
spec TrainRun:
  $model: model.etcm#ModelConfig
  $runtime: runtime.etcm#RuntimeConfig
  max_steps: int [>0]

  impl smoke:
    $model: model.etcm#ModelConfig:tiny
    $runtime: runtime.etcm#RuntimeConfig:local
    max_steps: 2
```

The declaration selects a spec; the implementation assignment selects a concrete
implementation. `$model` is a typed edge, not a raw include. ETCM checks that the
selected implementation belongs to `ModelConfig` or to a spec that inherits from
it.

The referenced object becomes part of every runtime view:

```python
from etcm import load

cfg = load("train.etcm#TrainRun:smoke")
print(cfg.model.hidden_size)
```

## Source-relative references

Selector paths are resolved relative to the ETCM file containing the selector:

```text
configs/train.etcm
configs/models/model.etcm
configs/runtime/runtime.etcm
```

From `configs/train.etcm`, these references remain stable regardless of the current
working directory:

```text
$model: models/model.etcm#ModelConfig
$runtime: runtime/runtime.etcm#RuntimeConfig
```

The same rule applies to `Path` and `File[...]` values contributed by referenced or
inherited implementations.

## Patching referenced children

An implementation can select a reference and patch one of its descendants:

```text
spec TrainRun:
  $model: model.etcm#ModelConfig

  impl debug:
    $model: model.etcm#ModelConfig:base
    model.hidden_size: 512
```

The patch is copy-on-write. It changes the `model` attached to `debug`; it does not
mutate `ModelConfig:base` or any other reference to it. Only the leaf field's
[override policy](overrides.md) is applied.

Reference selection and descendant patches may appear in either source order. ETCM
orders the shallower reference selection first. A child cannot be patched unless a
reference implementation is available from the current implementation or its
parent.

Indented and dotted patch forms are equivalent:

```text
impl debug:
  $model: model.etcm#ModelConfig:base
  model:
    hidden_size: 512
```

## Spec inheritance

A spec can extend another spec:

```text title="schedulers/base.etcm"
spec LRScheduler:
  warmup_steps: int = 0 [>=0]
  interval: str = "step" [in ["step", "epoch"]]
```

```text title="schedulers/cosine.etcm"
spec CosineLRScheduler <- base.etcm#LRScheduler:
  min_lr_ratio: float = 0.0 [>=0; <=1]
  cycles: float = 0.5 [>0]

  impl standard:
    warmup_steps: 1000
    min_lr_ratio: 0.01
```

`CosineLRScheduler:standard` is assignable where a field expects `LRScheduler`.
Inherited fields cannot be redefined. Named assertions are accumulated, and a child
cannot replace or disable an inherited assertion.

Inheritance cycles are rejected while resolving specs.

## Reusing an external spec

Use top-level `$spec` when a file should add implementations without extending or
copying a spec:

```text title="optimizers/variants.etcm"
$spec: base.etcm#Optimizer

impl fast:
  kind: "adamw"
  learning_rate: 0.001

impl conservative:
  kind: "adamw"
  learning_rate: 0.0001
```

This file imports `Optimizer` exactly as defined. It may declare top-level
implementations, but it cannot add or change fields. Select an implementation with:

```text
optimizers/variants.etcm#Optimizer:fast
```

Use spec inheritance instead when the new file needs additional fields or
assertions.

## Implementation inheritance

Implementations can inherit resolved values from a compatible implementation and
then apply local assignments:

```text
spec ModelConfig:
  hidden_size: int [>0]
  layers: int [>0]
  dropout: float = 0.0 [>=0; <1]

  impl base:
    hidden_size: 768
    layers: 12

  impl debug <- :base:
    hidden_size: 256
    layers: 2
```

Parents can also live in another file:

```text
impl custom <- presets.etcm#ModelConfig:base:
  dropout: 0.1
```

The child receives parent values before its local assignments are applied. Defaults
and inherited values count as existing values for override-policy purposes.
Implementation cycles and incompatible parents are errors.

## Same-file composition

A file may contain multiple specs. Same-file selectors keep those relationships
explicit:

```text
spec Optimizer:
  learning_rate: float [>0]

  impl fast:
    learning_rate: 0.001

spec Training:
  $optimizer: #Optimizer

  impl debug:
    $optimizer: #Optimizer:fast
```

Within the active local spec, `:implementation` is the shorter selector form used
for implementation inheritance.

## Inspecting the graph

`resolve()` returns a `ResolvedGraph` containing:

- the canonical root selector
- nodes with spec, implementation, source, field, and origin information
- typed edges between referenced objects
- every ETCM source file used during resolution
- filesystem path-resolution records
- override audit data

```python
from etcm import resolve

graph = resolve("train.etcm#TrainRun:smoke")

for edge in graph.edges:
    print(edge.kind, edge.source, edge.target)
```

The CLI exposes the same data as JSON:

```console
$ etcm resolve train.etcm#TrainRun:smoke --format json
```

Use the graph as the reproducibility artifact beside runs, checkpoints, builds, or
deployments. Validate it before treating it as an accepted configuration.
