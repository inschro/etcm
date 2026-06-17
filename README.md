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

Python API:

```python
from etcm import convert, load, resolve, validate

cfg = load("configs/train.etcm#smoke", target="pydantic")

graph = resolve("configs/train.etcm#smoke")
graph = validate(graph)
cfg = convert(graph, target="pydantic")
```

CLI:

```bash
etcm resolve configs/train.etcm#smoke --format json
etcm validate configs/train.etcm#smoke
etcm validate configs/train.etcm#smoke --short
etcm load configs/train.etcm#smoke --target pydantic
```

## Install

ETCM is currently scoped as a standalone Python package installable from a
built wheel, a local checkout, or a Git URL. Public PyPI publishing is deferred
until the release process is finalized.

```bash
uv build
python -m pip install dist/etcm-0.1.0-py3-none-any.whl
```

After installation, the CLI and Python API can be smoke-tested against the
example configs:

```bash
etcm validate examples/ml/train.etcm#smoke --short
etcm load examples/ml/train.etcm#smoke --target dict
python -c 'from etcm import load; print(load("examples/ml/train.etcm#smoke", target="dict")["run_name"])'
```

## Current Status

This repository is implemented through the generated-view API stage, with thin
CLI wrappers over the same public Python APIs. The next milestone is standalone
packaging, install smoke coverage, and real examples for consuming projects.

- [Manifest](docs/manifest.md)
- [Product Spec](docs/product_spec.md)
- [Install Guide](docs/install.md)
- [CLI Reference](docs/cli.md)
- [Implementation Roadmap](docs/roadmap.md)
- [Stage 1 Architecture Notes](docs/stage1/README.md)
- [Stage 2 Scaffold Notes](docs/stage2/README.md)
- [Stage 3 Fixture Contract Notes](docs/stage3/README.md)
- [Stage 4 Parser Core Notes](docs/stage4/README.md)
- [Stage 5 Resolver Core Notes](docs/stage5/README.md)
- [Stage 6 Generated View Notes](docs/stage6/README.md)
- [Stage 7 Pipeline CLI Notes](docs/stage7/README.md)
