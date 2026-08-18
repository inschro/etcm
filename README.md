# ETCM

ETCM is Typed Configuration Markup: a configuration language for defining,
validating, composing, and executing reproducible systems.

The thesis:

> Configuration describes a typed graph of executable objects.

ETCM is for projects where configuration is part of the system architecture:
machine learning experiments, distributed runtimes, HPC jobs, data pipelines,
service settings, and reusable infrastructure components.

## Why

ETCM is designed to complement familiar Python configuration workflows. It is
useful when a project benefits from:

- config files that reference reusable definitions across files
- generated Pydantic views from shared configuration definitions
- typed relationships and derived values across nested config objects
- explicit override policy for important fields
- resolved config artifacts for replay and audit
- object graphs made from models, optimizers, datasets, launchers, callbacks,
  and runtime modules

ETCM keeps those relationships explicit, type-checked, and easy to inspect.

## Example

```etcm
spec TrainRun:
  $model: models/lm.etcm#LMConfig
  $data: data/streams.etcm#DataStream
  $optimizer: optimizers/adamw.etcm#Optimizer
  max_steps: int [>0]

  impl smoke:
    $model: models/lm.etcm#LMConfig:tiny
    $data: data/streams.etcm#DataStream:smoke
    $optimizer: optimizers/adamw.etcm#Optimizer:fast
    max_steps: 2
```

Python API:

```python
from etcm import convert, load, resolve, validate

cfg = load("configs/train.etcm#TrainRun:smoke", target="pydantic")

cfg = load(
    "configs/train.etcm#TrainRun:smoke",
    overrides={"data.sampler.seed": 42},
)

graph = resolve("configs/train.etcm#TrainRun:smoke")
graph = validate(graph)
cfg = convert(graph, target="pydantic")
```

Selectors identify their target without inspecting the target file:

- `path.etcm#Spec` and `#Spec` select cross-file and same-file specs.
- `path.etcm#Spec:implementation` and `#Spec:implementation` select named
  implementations.
- `:implementation` selects an implementation in the active local spec.

Root selectors always use `path.etcm#Spec:implementation`. Implementations
named `default` are written explicitly as `:default`; ETCM never infers them.

Parameters can validate against or derive from other parameters. References
start at the containing object and may follow typed child objects:

```etcm
spec TrainingConfig:
  $dataloader: data/dataloader.etcm#DataLoaderConfig
  accumulation_steps: int = 1 [>0]
  world_size: int = 1 [>0]

  global_batch_size: int :=
    @dataloader.local_batch_size * @accumulation_steps * @world_size

  seed_confirmation: int [== @dataloader.sampler.seed]

  assert batch_shape:
    (
      @global_batch_size
      == @dataloader.local_batch_size * @accumulation_steps * @world_size
    )
```

See [Parameter Relations](docs/parameter-relations.md) for dotted-reference,
derived-value, named-assertion, type, evaluation, and diagnostic semantics.

Typing note: `load()` and `convert()` return `Any`. ETCM validates the config
before materializing it, but the returned object is a dynamic boundary for
pyright, Pylance, and mypy. This makes attribute access ergonomic without
repeated `cast(Any, ...)` calls. Static checkers will not catch misspelled
fields or incompatible field usage after that boundary unless your project
provides Python-visible types separately.

CLI:

```bash
etcm resolve configs/train.etcm#TrainRun:smoke --format json
etcm validate configs/train.etcm#TrainRun:smoke
etcm validate configs/train.etcm#TrainRun:smoke --short
etcm validate-all configs/
etcm load configs/train.etcm#TrainRun:smoke --target pydantic
etcm load configs/train.etcm#TrainRun:smoke --set data.sampler.seed=42
```

Python mappings, `PATH=VALUE` string lists, implementation assignments, and CLI
`--set` flags all use the same deep override semantics and spec-owned policies.
See [Overrides](docs/overrides.md) for reference replacement, relative path,
force authorization, and audit behavior.

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
etcm validate examples/ml/train.etcm#TrainRun:smoke --short
etcm load examples/ml/train.etcm#TrainRun:smoke --target dict
python -c 'from etcm import load; print(load("examples/ml/train.etcm#TrainRun:smoke", target="dict")["run_name"])'
```

## Current Status

This repository includes the parser, resolver, generated-view API, thin CLI,
standalone packaging, examples, typed parameter relations, named downward
assertions, and equivalent dotted or indented field paths for declarations and
implementations.

- [Manifest](docs/manifest.md)
- [Product Spec](docs/product_spec.md)
- [Install Guide](docs/install.md)
- [CLI Reference](docs/cli.md)
- [Parameter Relations](docs/parameter-relations.md)
- [Overrides](docs/overrides.md)
- [Implementation Roadmap](docs/roadmap.md)
- [Stage 1 Architecture Notes](docs/stage1/README.md)
- [Stage 2 Scaffold Notes](docs/stage2/README.md)
- [Stage 3 Fixture Contract Notes](docs/stage3/README.md)
- [Stage 4 Parser Core Notes](docs/stage4/README.md)
- [Stage 5 Resolver Core Notes](docs/stage5/README.md)
- [Stage 6 Generated View Notes](docs/stage6/README.md)
- [Stage 7 Pipeline CLI Notes](docs/stage7/README.md)
