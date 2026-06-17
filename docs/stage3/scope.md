# Stage 3 Scope

## Goal

Define the fixture, golden-output, and diagnostic contract that the parser core
will be measured against. Stage 3 is a design and test-contract stage, not a
syntax implementation stage.

The result should be concrete enough that Stage 4 can implement the parser by
adding grammar, transformers, and tests without reopening package boundaries,
selector semantics, diagnostic shape, or fixture categories.

## Included

Stage 3 includes:

- complete fixture matrix for v0 language behavior
- fixture naming conventions
- deterministic golden-output format rules
- diagnostic taxonomy and required diagnostic fields
- parser entry gates and Stage 4 acceptance criteria
- decisions about indentation, comments, blank lines, selector syntax, and path
  validation boundaries
- documentation updates that correct Stage 2 handoff language

## Excluded

Stage 3 excludes:

- production Lark grammar expansion
- transformer implementation from syntax tree to IR
- resolver graph loading
- filesystem path validation
- Pydantic view generation
- CLI implementation beyond preserving the "thin wrapper" rule

## Boundary Rule

If a question can be answered by fixture examples, golden-output structure, or
diagnostic shape, answer it in Stage 3. If answering it requires executable
parser, resolver, or generated-view behavior, defer it to Stage 4 or later and
record the gate that must be satisfied.

This keeps Stage 3 grounded without pretending that documentation is executable
evidence.
