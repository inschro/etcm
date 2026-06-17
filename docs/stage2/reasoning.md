# Stage 2 Reasoning

## Why Scaffold Before Parser

Parser work will quickly create pressure to make ad hoc choices about source
spans, diagnostics, selector data, and syntax-tree ownership. Creating the
package shell and IR contracts first keeps those concerns separate.

The main risk is not writing a parser. The main risk is writing parser behavior
that leaks into every other layer before the boundaries are clear.

## Why Placeholder APIs

The public imports should exist before the behavior does. This lets tests,
docs, and downstream examples converge on one API shape:

```python
from etcm import Resolver, load, resolve, validate
```

Placeholders should fail loudly. Silent partial behavior is worse than no
behavior because users may mistake it for a working resolver.

## Why Fixture-First

Fixtures make language decisions concrete. They also prevent parser work from
silently drifting away from the manifest.

Stage 2 creates only the first fixtures. Stage 3 will turn them into a full
fixture and golden-output contract. Stage 4 will make parser tests consume that
contract.

## Why No CLI Yet

The CLI is not a core risk. The Python bindings are the real contract. A CLI can
be a thin wrapper later, and the Stage 1 decision is to avoid Typer unless CLI
ergonomics become a product priority.

## Why No Resolver Yet

Resolver behavior depends on:

- parsed syntax
- IR shape
- source spans
- path policy
- diagnostic shape

Implementing it now would either duplicate future parser work or invent mock
semantics. Stage 2 should only create the namespace and placeholder settings.
