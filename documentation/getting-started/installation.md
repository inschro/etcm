# Installation

ETCM requires Python 3.12 or newer. It provides both the `etcm` command and the
Python package imported in the guides.

!!! note "Release status"

    ETCM is not yet published on PyPI. Install it from Git or from a repository
    checkout.

## Install from Git

Install the current default branch into an existing Python environment:

```console
$ python -m pip install "git+https://github.com/inschro/etcm.git"
```

For a reproducible installation, replace the default branch with a tag or commit:

```console
$ python -m pip install "git+https://github.com/inschro/etcm.git@<revision>"
```

## Work from a checkout

Clone the repository when you want to run the examples, change ETCM itself, or
build these docs:

```console
$ git clone https://github.com/inschro/etcm.git
$ cd etcm
$ uv sync --extra dev
```

Without `uv`, install the checkout with pip:

```console
$ python -m pip install .
```

## Check the installation

The command should list four operations:

```console
$ etcm --help
usage: etcm [-h] {resolve,validate,validate-all,load} ...
```

The Python entry point should import from the same environment:

```console
$ python -c 'from etcm import load; print(load)'
```

Continue with the [quickstart](quickstart.md). It creates a complete ETCM file,
validates it, and loads it from Python.

## Preview the documentation

Documentation contributors need the dedicated extra:

```console
$ uv sync --extra docs
$ uv run --extra docs zensical serve
```

The preview is available at <http://127.0.0.1:8000>. Run the same strict build as
CI with:

```console
$ uv run --extra docs zensical build --clean --strict
```
