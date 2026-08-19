# Advanced tutorial: build Python objects from ETCM

The [basic tutorial](basic.md) composed a training run with a model. This tutorial
extends the same setup into a small application boundary: ETCM resolves and
validates the configuration, argparse supplies temporary overrides, and a
generated dataclass drives ordinary Python and PyTorch constructors.

The runnable project includes
[`train.etcm`](../examples/ml-training/02-advanced/train.etcm) and
[`train.py`](../examples/ml-training/02-advanced/train.py). It does not train a
model or download data. It constructs a random input tensor, a model, an
optimizer, one forward result, and a checkpoint path.

## Reuse model variants through inheritance

The advanced `ModelConfig` adds activation and dropout settings. The baseline
variant starts from the tiny variant and changes only the fields that distinguish
it:

```text title="model.etcm"
spec ModelConfig:
  name: str
  hidden_size: int = 32 [>0]
  layers: int = 2 [>0]
  activation: str = "relu" [in ["relu", "gelu"]]
  dropout: float = 0.0 [>=0; <1]

  impl tiny:
    name: "tiny-mlp"
    hidden_size: 16
    layers: 1

  impl baseline <- :tiny:
    name: "baseline-mlp"
    hidden_size: 64
    layers: 3
    activation: "gelu"
    dropout: 0.1
```

`impl baseline <- :tiny` resolves the parent first and then applies the local
assignments. Both implementations still satisfy the same spec.

## Represent the runtime and its output path

Runtime choices have their own identity, so they use another referenced spec:

```text title="runtime.etcm"
spec RuntimeConfig:
  device: str = "cpu" [in ["cpu", "cuda"]]
  num_threads: int = 1 [>0]
  output_dir: Path = "runs" [path_exists="allow_missing"; path_kind="dir"]

  impl local:
    output_dir: "runs/local"

  impl cuda <- :local:
    device: "cuda"
    output_dir: "runs/cuda"
```

`Path` is appropriate because the application needs a location, not the contents
of a file. With the dataclass target, `output_dir` becomes a `pathlib.Path`, so
the application can form a checkpoint path with `/`.

## Load a small JSON manifest

The generated input dimensions live in a normal JSON file:

```json title="dataset.json"
{
  "name": "synthetic-classification",
  "input_features": 8,
  "classes": 3
}
```

Declare it as `File[json]`:

```text
dataset: File[json] = "dataset.json"
```

ETCM resolves the filename relative to the configuration source and decodes the
document before creating the dataclass. The application receives the mapping
through `config.dataset`; it does not open or decode the file itself.

## Put ownership rules in the spec

Some values need stricter rules than ordinary replacement:

```text
config_version: int = 1 [override="deny"]
seed: int = 7 [>=0; override="force_only"]
tags: list[str] = ["training"] [override="append"]
metadata: dict[str, str] = {team: "research"} [override="merge"]
```

- `config_version` is a contract constant. Neither implementations nor external
  callers may replace it, even with force authorization.
- `seed` may be replaced externally only when the caller explicitly authorizes a
  `force_only` override.
- `tags` accumulate instead of replacing the existing list.
- `metadata` recursively combines mapping values, with later leaf values winning.

These policies belong to the spec. The argparse layer merely forwards the
caller's requested values and force authorization.

## Keep related fields together

Optimizer values belong together but do not need independent named
implementations, so they are ordinary nested fields:

```text
optimizer:
  learning_rate: float = 0.001 [>0; <=1]
  weight_decay: float = 0.01 [>=0; <=1]
```

They materialize as another generated dataclass. Python reads
`config.optimizer.learning_rate`, and an override addresses the same value as
`optimizer.learning_rate`.

## Derive and assert relationships

The effective batch size remains derived:

```text
effective_batch_size: int := @micro_batch_size * @gradient_accumulation_steps
```

A named assertion protects a relationship that does not produce a new value:

```text
assert checkpoint_schedule:
  @checkpoint_every <= @max_steps
```

After resolution and derivation, every training run must schedule its first
checkpoint no later than its final configured step.

## Extend complete runs

The training implementations reuse both referenced children and parent runs:

```text
impl smoke:
  $model: model.etcm#ModelConfig:tiny
  $runtime: runtime.etcm#RuntimeConfig:local
  run_name: "smoke"
  max_steps: 2
  tags: ["smoke"]
  metadata: {purpose: "tutorial"}

impl baseline <- :smoke:
  $model: model.etcm#ModelConfig:baseline
  run_name: "baseline"
  max_steps: 20
  micro_batch_size: 16
  gradient_accumulation_steps: 2
  checkpoint_every: 5
  tags: ["baseline"]
  metadata: {purpose: "baseline"}

impl cuda_debug <- :baseline:
  $runtime: runtime.etcm#RuntimeConfig:cuda
  run_name: "cuda-debug"
  max_steps: 3
  micro_batch_size: 4
  gradient_accumulation_steps: 1
  checkpoint_every: 1
  tags: ["cuda"]
  metadata: {purpose: "debug"}
```

Loading `baseline` produces an effective batch size of `32`, tags
`["training", "smoke", "baseline"]`, and metadata
`{"team": "research", "purpose": "baseline"}`. Inheritance, append, and merge
all happen before validation and conversion.

## Forward argparse overrides to ETCM

The application accepts one selector and the same `PATH=VALUE` strings as the
ETCM CLI:

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build PyTorch objects from ETCM config."
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--set", dest="overrides", action="append", default=[])
    parser.add_argument("--force-overrides", action="store_true")
    return parser


def load_config(args: argparse.Namespace) -> Any:
    return load(
        args.config,
        target="dataclass",
        overrides=args.overrides,
        force_overrides=args.force_overrides,
        override_base=Path.cwd(),
    )
```

ETCM remains responsible for parsing override literals, applying policies,
recalculating derived fields, validating the graph, and building the dataclass.
The application does not duplicate that logic.

## Construct PyTorch objects from the dataclass

The generated view follows the configuration graph. Referenced and nested
objects use attribute access, `File[json]` exposes decoded content, and `Path`
stays a `Path`:

```python
inputs = torch.randn(
    config.micro_batch_size,
    config.dataset["input_features"],
    device=config.runtime.device,
)

model = torch.nn.Sequential(...)
optimizer = torch.optim.AdamW(
    model.parameters(),
    lr=config.optimizer.learning_rate,
    weight_decay=config.optimizer.weight_decay,
)
logits = model(inputs)
checkpoint = config.runtime.output_dir / f"{config.run_name}.pt"
```

The full constructor below expands the model layers from
`config.model.layers`. It performs one forward pass only to show that the
constructed objects agree on their shapes.

Run the smoke configuration:

```console
$ python train.py
config: smoke
inputs: (8, 8)
model: Sequential
optimizer: AdamW
logits: (8, 3)
checkpoint: /path/to/runs/local/smoke.pt
```

Choose another implementation and apply deep overrides:

```console
$ python train.py \
    --config train.etcm#TrainRun:baseline \
    --set model.hidden_size=32 \
    --set optimizer.learning_rate=0.0005
```

Replacing the protected seed requires explicit authorization:

```console
$ python train.py --set seed=11 --force-overrides
```

Force never bypasses `deny`. The argparse diagnostic ends with:

```console
$ python train.py --set config_version=2 --force-overrides
train.py: error: E_INVALID_OVERRIDE: Field 'config_version' cannot be overridden with policy 'deny'.
```

## Complete advanced project

The final project contains five files:

```text
02-advanced/
├── dataset.json
├── model.etcm
├── runtime.etcm
├── train.etcm
└── train.py
```

### `model.etcm`

```text
spec ModelConfig:
  name: str
  hidden_size: int = 32 [>0]
  layers: int = 2 [>0]
  activation: str = "relu" [in ["relu", "gelu"]]
  dropout: float = 0.0 [>=0; <1]

  impl tiny:
    name: "tiny-mlp"
    hidden_size: 16
    layers: 1

  impl baseline <- :tiny:
    name: "baseline-mlp"
    hidden_size: 64
    layers: 3
    activation: "gelu"
    dropout: 0.1
```

### `runtime.etcm`

```text
spec RuntimeConfig:
  device: str = "cpu" [in ["cpu", "cuda"]]
  num_threads: int = 1 [>0]
  output_dir: Path = "runs" [path_exists="allow_missing"; path_kind="dir"]

  impl local:
    output_dir: "runs/local"

  impl cuda <- :local:
    device: "cuda"
    output_dir: "runs/cuda"
```

### `dataset.json`

```json
{
  "name": "synthetic-classification",
  "input_features": 8,
  "classes": 3
}
```

### `train.etcm`

```text
spec TrainRun:
  config_version: int = 1 [override="deny"]
  $model: model.etcm#ModelConfig
  $runtime: runtime.etcm#RuntimeConfig
  dataset: File[json] = "dataset.json"
  run_name: str
  seed: int = 7 [>=0; override="force_only"]
  max_steps: int [>0]
  micro_batch_size: int = 8 [>0]
  gradient_accumulation_steps: int = 1 [>0]
  optimizer:
    learning_rate: float = 0.001 [>0; <=1]
    weight_decay: float = 0.01 [>=0; <=1]
  checkpoint_every: int = 1 [>0]
  tags: list[str] = ["training"] [override="append"]
  metadata: dict[str, str] = {team: "research"} [override="merge"]
  effective_batch_size: int := @micro_batch_size * @gradient_accumulation_steps

  assert checkpoint_schedule:
    @checkpoint_every <= @max_steps

  impl smoke:
    $model: model.etcm#ModelConfig:tiny
    $runtime: runtime.etcm#RuntimeConfig:local
    run_name: "smoke"
    max_steps: 2
    tags: ["smoke"]
    metadata: {purpose: "tutorial"}

  impl baseline <- :smoke:
    $model: model.etcm#ModelConfig:baseline
    run_name: "baseline"
    max_steps: 20
    micro_batch_size: 16
    gradient_accumulation_steps: 2
    checkpoint_every: 5
    tags: ["baseline"]
    metadata: {purpose: "baseline"}

  impl cuda_debug <- :baseline:
    $runtime: runtime.etcm#RuntimeConfig:cuda
    run_name: "cuda-debug"
    max_steps: 3
    micro_batch_size: 4
    gradient_accumulation_steps: 1
    checkpoint_every: 1
    tags: ["cuda"]
    metadata: {purpose: "debug"}
```

### `train.py`

```python
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from etcm import load
from etcm.errors import ETCMError

DEFAULT_CONFIG = f"{Path(__file__).with_name('train.etcm')}#TrainRun:smoke"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build PyTorch objects from ETCM config.")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--set", dest="overrides", action="append", default=[])
    parser.add_argument("--force-overrides", action="store_true")
    return parser


def load_config(args: argparse.Namespace) -> Any:
    return load(
        args.config,
        target="dataclass",
        overrides=args.overrides,
        force_overrides=args.force_overrides,
        override_base=Path.cwd(),
    )


def build_objects(config: Any) -> tuple[Any, Any, Any, Any, Path]:
    import torch

    torch.manual_seed(config.seed)
    torch.set_num_threads(config.runtime.num_threads)
    device = torch.device(config.runtime.device)

    inputs = torch.randn(
        config.micro_batch_size,
        config.dataset["input_features"],
        device=device,
    )

    activation = {
        "relu": torch.nn.ReLU,
        "gelu": torch.nn.GELU,
    }[config.model.activation]
    layers: list[Any] = []
    in_features = config.dataset["input_features"]
    for _ in range(config.model.layers):
        layers.append(torch.nn.Linear(in_features, config.model.hidden_size))
        layers.append(activation())
        if config.model.dropout > 0:
            layers.append(torch.nn.Dropout(config.model.dropout))
        in_features = config.model.hidden_size
    layers.append(torch.nn.Linear(in_features, config.dataset["classes"]))

    model = torch.nn.Sequential(*layers).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.optimizer.learning_rate,
        weight_decay=config.optimizer.weight_decay,
    )
    logits = model(inputs)
    checkpoint = config.runtime.output_dir / f"{config.run_name}.pt"
    return inputs, model, optimizer, logits, checkpoint


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        config = load_config(args)
        inputs, model, optimizer, logits, checkpoint = build_objects(config)
    except ETCMError as exc:
        parser.error(f"{exc.diagnostic.code}: {exc.diagnostic.message}")
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))

    print(f"config: {config.run_name}")
    print(f"inputs: {tuple(inputs.shape)}")
    print(f"model: {model.__class__.__name__}")
    print(f"optimizer: {optimizer.__class__.__name__}")
    print(f"logits: {tuple(logits.shape)}")
    print(f"checkpoint: {checkpoint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

The [language reference](../reference/language.md),
[override reference](../reference/overrides.md), and
[Python API reference](../reference/python-api.md) contain the exhaustive forms
and edge-case behavior intentionally left out of this tutorial.
