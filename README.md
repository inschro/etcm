# ETCM

[![Documentation](https://github.com/inschro/etcm/actions/workflows/docs.yml/badge.svg)](https://github.com/inschro/etcm/actions/workflows/docs.yml)

[Documentation](https://inschro.github.io/etcm/) ·
[Quickstart](documentation/getting-started/quickstart.md) ·
[Language reference](documentation/reference/language.md)

ETCM is **ETCM Typed Configuration Markup**: a configuration language for
defining named, reusable configurations and validating them before application
code consumes them.

Start with a contract and one implementation:

```etcm
spec Pet:
  name: str
  daily_food_grams: int [>0]

  impl pepper:
    name: "Pepper"
    daily_food_grams: 300
```

`spec Pet` says which fields every pet must provide. `impl pepper` supplies one
named set of values. The selector `pets.etcm#Pet:pepper` identifies that exact
implementation, so the CLI and Python API load the same thing:

```bash
etcm validate pets.etcm#Pet:pepper --short
```

```python
from etcm import load

pet = load("pets.etcm#Pet:pepper")
print(pet.name)  # Pepper
```

As configuration grows, ETCM can compose implementations into a typed graph,
apply controlled overrides, check cross-field constraints, derive values, and
load typed file contents. For a few unrelated scalar settings, a dictionary or
TOML file may still be the simpler choice.

## Install

ETCM requires Python 3.12 or newer. It is not yet published on PyPI; install the
current package directly from GitHub:

```bash
python -m pip install "etcm @ git+https://github.com/inschro/etcm.git"
etcm --help
```

For development, clone the repository and install the locked environment:

```bash
git clone https://github.com/inschro/etcm.git
cd etcm
uv sync --locked --extra dev --extra docs
```

See the [installation guide](documentation/getting-started/installation.md) for
the supported install paths, then follow the
[quickstart](documentation/getting-started/quickstart.md) to create and load a
configuration.

## Everyday workflow

Validate the implementation you changed:

```bash
etcm validate path/to/config.etcm#Spec:implementation --short
```

If you changed a shared spec or reference, validate every implementation below
the affected configuration directory:

```bash
etcm validate-all path/to/configs
```

Load a validated result as a generated Pydantic model (the default) or as a
plain dictionary:

```python
from etcm import load

run = load("train.etcm#TrainRun:smoke")
run_dict = load("train.etcm#TrainRun:smoke", target="dict")
```

The documentation continues from the basic workflow without assuming prior
ETCM knowledge:

- [Basic tutorial](documentation/tutorials/basic.md)
- [Advanced tutorial](documentation/tutorials/advanced.md)
- [Language reference](documentation/reference/language.md)
- [Override reference](documentation/reference/overrides.md)
- [File-types reference](documentation/reference/files.md)
- [Python API](documentation/reference/python-api.md)
- [CLI reference](documentation/reference/cli.md)

## Development

Run the project checks from a development checkout:

```bash
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync basedpyright
uv run --no-sync zensical build --clean --strict
```

Start the documentation preview at `http://127.0.0.1:8000/`:

```bash
uv run --no-sync zensical serve
```

ETCM is alpha software: the language and public API are usable, but compatibility
is not yet guaranteed between releases. The project is licensed under
[Apache-2.0](LICENSE).
