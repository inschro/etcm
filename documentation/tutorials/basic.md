# Basic tutorial: build a training configuration

The quickstart covered ETCM's smallest useful workflow. This tutorial starts from
that knowledge and builds something with structure: two model variants and two
training runs that reuse them.

The finished example contains
[`model.etcm`](../examples/ml-training/01-basic/model.etcm) and
[`train.etcm`](../examples/ml-training/01-basic/train.etcm).

## Describe the model variants

A training run needs a model, but model settings should not be copied into every
run. Put their contract and named variants in `model.etcm`:

```text title="model.etcm"
spec ModelConfig:
  name: str
  hidden_size: int [>0]
  layers: int = 2 [>0]

  impl tiny:
    name: "tiny-mlp"
    hidden_size: 16
    layers: 1

  impl baseline:
    name: "baseline-mlp"
    hidden_size: 64
    layers: 3
```

The spec defines one required string, one required positive integer, and one
positive integer with a default. Each implementation supplies a complete model.
The default would be used if an implementation omitted `layers`; these two
variants override it deliberately.

Validate every implementation in the file:

```console
$ etcm validate-all model.etcm --quiet
2 total, 2 OK, 0 fail
```

## Make a training run refer to a model

Create `train.etcm` beside it:

```text title="train.etcm"
spec TrainRun:
  $model: model.etcm#ModelConfig
  max_steps: int [>0]
  micro_batch_size: int = 8 [>0]
  gradient_accumulation_steps: int = 1 [>0]
  learning_rate: float = 0.001 [>0; <=1]
  effective_batch_size: int := @micro_batch_size * @gradient_accumulation_steps

  impl smoke:
    $model: model.etcm#ModelConfig:tiny
    max_steps: 2

  impl baseline:
    $model: model.etcm#ModelConfig:baseline
    max_steps: 100
    micro_batch_size: 16
    gradient_accumulation_steps: 2
```

The declaration and implementation use similar-looking reference syntax for two
different jobs:

- `$model: model.etcm#ModelConfig` requires a child that satisfies `ModelConfig`.
- `$model: model.etcm#ModelConfig:tiny` selects the concrete child for `smoke`.

The `baseline` run chooses the other model without duplicating its fields. ETCM
resolves each run into a graph with a `TrainRun` root and a referenced
`ModelConfig` child.

## Derive a value from other fields

`effective_batch_size` is calculated from two resolved values:

```text
effective_batch_size: int := @micro_batch_size * @gradient_accumulation_steps
```

`:=` makes the field derived. Implementations and callers cannot assign it.
ETCM recalculates it after defaults, implementation values, and overrides have
been applied.

Validate the complete example:

```console
$ etcm validate-all . --quiet
4 total, 4 OK, 0 fail
```

## See a constraint reject an override

An override changes one resolution without editing the source configuration.
Use one to try an invalid learning rate:

```console
$ etcm validate train.etcm#TrainRun:smoke --short \
    --set learning_rate=-0.1
```

ETCM exits with status `1`. The relevant diagnostic is:

```text
E_CONSTRAINT: Validation failed for TrainRun.learning_rate.
graph_path: root.learning_rate

constraint:
  >0

resolved values:
  learning_rate: -0.1

evaluation:
  -0.1 > 0
```

The type is still `float`, but the value fails the positive-number constraint.
Validation stops before a Python object is created.

## Load the composed result

Load the smoke run as a dictionary:

```python
from etcm import load

config = load("train.etcm#TrainRun:smoke", target="dict")

assert config["model"] == {
    "name": "tiny-mlp",
    "hidden_size": 16,
    "layers": 1,
}
assert config["max_steps"] == 2
assert config["effective_batch_size"] == 8
```

The referenced model becomes a nested mapping. The result contains only concrete
values; selectors and expressions have already done their work.

## Override inputs and keep derivation consistent

Override both inputs to the derived field:

```console
$ etcm load train.etcm#TrainRun:smoke --target dict \
    --set micro_batch_size=4 \
    --set gradient_accumulation_steps=3
```

The relevant result is:

```json
{
  "micro_batch_size": 4,
  "gradient_accumulation_steps": 3,
  "effective_batch_size": 12
}
```

Nothing modifies the `smoke` implementation on disk. A later load without those
overrides again produces an effective batch size of `8`.

## What the basic workflow establishes

The example now has the pieces ETCM applications use most often:

1. Specs define typed contracts, defaults, and constraints.
2. Implementations name valid configurations.
3. Selectors address an exact implementation.
4. Typed references compose independently reusable configurations.
5. Derived fields keep dependent values consistent.
6. Validation runs before conversion to a Python view.
7. Overrides customize one resolution without changing the source.

The [advanced tutorial](advanced.md) keeps this training setup and adds
inheritance, controlled overrides, file-backed JSON, paths, assertions, and an
argparse entry point that builds Python and PyTorch objects.
