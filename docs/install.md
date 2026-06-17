# Installing ETCM

ETCM is packaged as a pure Python library with an `etcm` console script. The
current release-readiness target is installation from a built wheel, local
checkout, or Git URL. Public PyPI publishing is deferred until the package
release process is finalized.

## Build A Wheel

```bash
uv build
```

The wheel is written under `dist/`.

## Install From A Wheel

```bash
python -m pip install dist/etcm-0.1.0-py3-none-any.whl
```

## Install From A Checkout

```bash
python -m pip install .
```

## Install From Git

```bash
python -m pip install "git+https://example.com/your-org/etcm.git"
```

Replace the URL with the repository URL you want the consuming project to use.

## Smoke Test

From this repository checkout, the example configs can be used to verify the
installed package and CLI:

```bash
etcm --help
etcm validate examples/ml/train.etcm#smoke --short
etcm load examples/ml/train.etcm#smoke --target dict
python -c 'from etcm import load; print(load("examples/ml/train.etcm#smoke", target="dict")["run_name"])'
```
