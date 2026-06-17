# Stage 3 Reasoning

## Why A Formal Stage 3 Exists

The roadmap puts parser implementation in Stage 4, but the project still needs a
Stage 3 because parser behavior is where language projects often harden too
early around accidental implementation choices.

The fixture contract is the cheapest place to make semantics concrete:

- examples show which user workflows matter
- invalid fixtures make error quality testable
- golden formats force deterministic serialization early
- parser gates separate syntax responsibilities from resolver responsibilities

This is documentation work, but it is not ceremonial. It defines what future
code has to prove.

## Why Not Implement Parser Here

The parser is important enough to deserve a clean start against a complete
corpus. Starting it while still naming fixture groups would make the first
grammar shape the fixture contract by accident.

Stage 3 therefore stops at:

- planned fixture files
- expected diagnostic categories
- golden-output shapes
- parser entry and exit gates

Stage 4 can then implement Lark grammar and IR transformation with a clear
target.

## Why CLI Remains Unimportant

The CLI is a wrapper, not an architecture driver. It should call the same Python
API that library users call:

```python
from etcm import Resolver, load, resolve, validate
```

Adding CLI behavior before parser and resolver behavior would mostly test
argument parsing. That does not reduce the core project risk. Stage 3 keeps CLI
work limited to the rule that command code must not own parser, resolver,
graph, or codegen logic.

## Why Diagnostics Are First-Class

ETCM is meant for config-driven systems where errors often appear far from the
Python code that eventually consumes the config. Poor diagnostics would make the
language feel unreliable even if type checking is technically correct.

The diagnostic contract exists early so fixtures can test not only that a file
fails, but how it fails:

- stable error code
- source span
- selector when applicable
- graph path when applicable
- path policy details for `Path`

## Why Path Policy Is In The Fixture Contract

`Path` is a v0 feature because real ML and data projects need reproducible
artifact, dataset, checkpoint, and output paths. The resolver must know whether
a field allows missing paths or requires existing paths, and field metadata may
override or delegate to resolver settings.

The parser should only preserve the syntax and metadata. The resolver owns
existence and kind validation.

## Evidence Level

Stage 3 is grounded in:

- Stage 1 parser and Pydantic spikes
- Stage 1 alternative parser review
- Stage 2 package and IR scaffold
- documented use cases from the manifest and product spec
- stable fixture and golden-output practices common to parser projects

Stage 3 is not executable evidence for parser correctness. That evidence begins
in Stage 4.
