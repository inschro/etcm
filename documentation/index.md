# ETCM

ETCM typed configuration markup is a typed language for reproducible
configuration graphs.

ETCM is intended for application configuration that has outgrown a flat file or
dictionary. When named configurations share components, accept overrides, or
depend on relationships between fields, their rules tend to become scattered
through application code.

ETCM puts the contract and the concrete values in the configuration language.
That gives both people and tools one place to answer two questions:

1. What shape must this configuration have?
2. Which named set of values do I want to use?

## The smallest useful ETCM file

Suppose we want to describe a pet. The contract needs only one field to begin
with:

```text title="pets.etcm"
spec Pet:
  name: str

  impl pepper:
    name: "Pepper"
```

`spec Pet` defines the contract. It says every `Pet` needs a string called
`name`. `impl pepper` is one named configuration that satisfies that contract.

Check the configuration from the command line before application code consumes
it:

```console
$ etcm validate pets.etcm#Pet:pepper --short
OK: /path/to/pets.etcm#Pet:pepper
```

When application code loads the same named configuration, `load()` validates it
again before returning a runtime object:

```python
from etcm import load

pet = load("pets.etcm#Pet:pepper")
print(pet.name)  # Pepper
```

Specs, implementations, and selectors are ETCM's core concepts. The tutorials
use them to introduce composition, validation rules, derived values, and
controlled overrides.

## When the configuration grows

In a larger project, one configuration may refer to another. A boarding stay can
refer to a pet, for example, without copying the pet's name and feeding needs.
ETCM preserves that relationship as a typed graph and validates the graph before
turning it into Python objects.

This is useful when configuration has real structure: reusable components,
several deployment or execution variants, cross-field rules, controlled
overrides, or files whose contents belong in the resolved result.

For a small collection of unrelated scalar settings, a dictionary or TOML file
may still be the simpler choice.

!!! warning "Alpha software"

    ETCM is under active development. The language and public API are usable, but
    compatibility is not yet guaranteed between releases.

## Start here

1. [Install ETCM](getting-started/installation.md).
2. Build and load one configuration in the
   [quickstart](getting-started/quickstart.md).
3. Build a composed training setup in the [basic tutorial](tutorials/basic.md).
4. Continue with the [advanced tutorial](tutorials/advanced.md) for inheritance,
   controlled overrides, file-backed values, and Python integration.

Use the [language reference](reference/language.md),
[Python API](reference/python-api.md), and [CLI reference](reference/cli.md) when
you need an exact lookup rather than a tutorial.

## What ETCM does not do

ETCM defines, composes, validates, inspects, and materializes configuration. It
does not schedule work, execute arbitrary Python from configuration, manage
secrets, or replace the application that consumes the result.
