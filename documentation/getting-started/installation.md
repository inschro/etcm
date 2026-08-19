# Installation

ETCM is a pure Python package with an `etcm` console command. It requires Python
3.12 or newer.

!!! note "Release status"

    ETCM is not currently published on the public Python Package Index. Install it
    from a checkout, a built wheel, or its Git repository.

## Install from a checkout

Clone the repository and install the package into your active environment:

```console
$ git clone https://github.com/inschro/etcm.git
$ cd etcm
$ python -m pip install .
```

For development with [uv](https://docs.astral.sh/uv/):

```console
$ uv sync --extra dev
```

## Install from Git

Install the current default branch directly:

```console
$ python -m pip install "git+https://github.com/inschro/etcm.git"
```

Pin a tag or commit after the `@` when reproducibility matters:

```console
$ python -m pip install "git+https://github.com/inschro/etcm.git@<revision>"
```

## Build and install a wheel

From a repository checkout:

```console
$ uv build
$ python -m pip install dist/etcm-0.1.0-py3-none-any.whl
```

## Verify the installation

```console
$ etcm --help
usage: etcm [-h] {resolve,validate,validate-all,load} ...
```

You can also verify the public Python entry point:

```console
$ python -c 'from etcm import load; print(load)'
```

Continue with the [quickstart](quickstart.md) to create and load your first ETCM
configuration.

## Preview these docs locally

Documentation contributors can install the dedicated dependency extra and start
Zensical's live preview server:

```console
$ uv sync --extra docs
$ uv run --extra docs zensical serve
```

Open <http://localhost:8000>. To run the same strict build used by CI:

```console
$ uv run --extra docs zensical build --clean --strict
```
