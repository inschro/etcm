# ETCM

**Typed Configuration Markup for reproducible configuration graphs.**

ETCM is a configuration language for defining, validating, composing, and loading
typed systems. It is designed for projects where configuration is part of the
architecture: machine-learning experiments, data pipelines, distributed runtimes,
service settings, and reusable infrastructure components.

!!! warning "Alpha software"

    ETCM is under active development. The language and public API are usable, but
    compatibility is not yet guaranteed between releases.

## Why ETCM?

A real configuration often describes more than scalar settings. Models depend on
optimizers, runtimes depend on launchers, and experiments need a complete record of
the graph that produced a result. ETCM makes those relationships explicit and
type-checked.

- **Typed definitions** keep structure and validation beside the configuration.
- **Explicit references** compose reusable implementations across files.
- **Derived values and assertions** express relationships without executing Python.
- **Spec-owned overrides** control which values callers may replace or combine.
- **Resolved graphs** retain source identity and override history for audit and replay.
- **Python and CLI entry points** use the same resolve, validate, and convert pipeline.

## A small example

```text title="train.etcm"
spec TrainRun:
  epochs: int [>0]
  learning_rate: float = 0.001 [>0]
  batch_size: int = 32 [>0]
  total_examples: int := @epochs * @batch_size

  impl smoke:
    epochs: 1
```

Select the implementation by its exact file, spec, and implementation identity:

```console
$ etcm validate train.etcm#TrainRun:smoke --short
OK: train.etcm#TrainRun:smoke
```

Load the same configuration in Python:

```python
from etcm import load

cfg = load("train.etcm#TrainRun:smoke")
print(cfg.total_examples)
```

## Where to begin

- [Install ETCM](getting-started/installation.md), then follow the
  [quickstart](getting-started/quickstart.md).
- Read [core concepts](guides/core-concepts.md) for specs, implementations, fields,
  selectors, and paths.
- Use [composition](guides/composition.md) to connect typed objects across files.
- Add invariants with [validation and derived values](guides/validation.md).
- Integrate ETCM through the [Python API](reference/python-api.md) or
  [CLI](reference/cli.md).

## Design boundary

ETCM defines, validates, composes, inspects, and materializes typed configuration.
It is not a workflow scheduler, secrets manager, arbitrary Python execution system,
or general-purpose programming language.
