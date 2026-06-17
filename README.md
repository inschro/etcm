# ETCM

ETCM is Typed Configuration Markup: a configuration language for defining,
validating, composing, and executing reproducible systems.

The thesis:

> Configuration describes a typed graph of executable objects.

ETCM is for projects where config files are no longer just parameter bags:
machine learning experiments, distributed runtimes, HPC jobs, data pipelines,
service settings, and reusable infrastructure components.

## Why

Config-heavy Python projects often end up with:

- YAML registries and local `$ref` conventions
- Pydantic schemas duplicated beside config files
- CLI overrides that can silently change critical fields
- experiment artifacts that need a resolved config for replay
- object graphs made from models, optimizers, datasets, launchers, callbacks,
  and runtime modules

ETCM makes those relationships explicit and type-checked.

## Example

```etcm
spec TrainRun:
  model: LMConfig
  data: DataStream
  optimizer: Optimizer
  max_steps: int = Field(gt=0)

impl smoke:
  $model: models/lm.etcm#tiny
  $data: data/streams.etcm#smoke
  $optimizer: optimizers/adamw.etcm#fast
  max_steps: 2
```

Planned Python API:

```python
from etcm import load

cfg = load("configs/train.etcm#smoke", as_="pydantic")
```

Planned CLI:

```bash
etcm validate configs/train.etcm#smoke
etcm resolve configs/train.etcm#smoke
etcm inspect configs/train.etcm#smoke
etcm graph configs/train.etcm#smoke
```

## Current Status

This repository is in design stage. The docs define the product direction and
v0 implementation scope before package code is written.

- [Manifest](docs/manifest.md)
- [Product Spec](docs/product_spec.md)
- [Implementation Roadmap](docs/roadmap.md)
