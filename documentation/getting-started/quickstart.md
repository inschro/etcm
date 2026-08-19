# Quickstart

This walkthrough defines one typed configuration, validates it from the command
line, and loads it in Python.

You can also download the [complete example](../examples/quickstart.etcm).

## Create a configuration

Create an empty directory and save this file as `train.etcm`:

```text title="train.etcm"
spec TrainRun:
  epochs: int [>0]
  learning_rate: float = 0.001 [>0]
  batch_size: int = 32 [>0]
  total_examples: int := @epochs * @batch_size

  impl smoke:
    epochs: 1
```

The `TrainRun` spec defines four fields. `learning_rate` and `batch_size` have
defaults, `epochs` must be supplied, and `total_examples` is derived during
resolution. The `smoke` implementation supplies the required field.

## Validate it

An implementation selector has the form
`path.etcm#Spec:implementation`:

```console
$ etcm validate train.etcm#TrainRun:smoke --short
OK: train.etcm#TrainRun:smoke
```

Without `--short`, `validate` prints the complete validated graph as JSON:

```console
$ etcm validate train.etcm#TrainRun:smoke
```

Use `resolve` when you need to inspect defaults, origins, and derived values before
validation:

```console
$ etcm resolve train.etcm#TrainRun:smoke --format json
```

## Load a runtime view

The default Python target is a generated Pydantic model:

```python title="load_config.py"
from etcm import load

cfg = load("train.etcm#TrainRun:smoke")

print(cfg.epochs)          # 1
print(cfg.batch_size)      # 32
print(cfg.total_examples)  # 32
```

Choose `dict` when an ordinary nested mapping is a better integration boundary:

```python
from etcm import load

cfg = load("train.etcm#TrainRun:smoke", target="dict")
assert cfg["total_examples"] == 32
```

ETCM validates before `load()` materializes any target.

## Override a value

CLI and Python overrides use the same dot-path semantics:

```console
$ etcm load train.etcm#TrainRun:smoke --target dict --set batch_size=8
```

```python
from etcm import load

cfg = load(
    "train.etcm#TrainRun:smoke",
    target="dict",
    overrides={"batch_size": 8},
)

assert cfg["total_examples"] == 8
```

Derived fields are recomputed after their dependencies change. Assigning
`total_examples` directly is an error because the spec owns its expression.

## Next steps

- Learn the building blocks in [core concepts](../guides/core-concepts.md).
- Compose multiple files with [typed references](../guides/composition.md).
- Define cross-field rules with
  [validation and derived values](../guides/validation.md).
- Control callers with [override policies](../guides/overrides.md).
- See every command in the [CLI reference](../reference/cli.md).
