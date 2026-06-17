# Stage 2 Scope

## Goal

Create enough structure that Stage 3 can complete the fixture and golden-output
contract, and that Stage 4 can add parser behavior against that contract instead
of inventing package layout, public APIs, and data contracts at the same time.

## Included

Stage 2 includes:

- package scaffold and project metadata
- public API placeholders
- module namespace layout
- immutable IR dataclass shell
- syntax module shell
- shared diagnostic shell
- fixture directories and first fixture files
- tests for importability, placeholders, frozen dataclasses, selector parsing,
  and fixture presence
- documentation for the handoff into the fixture contract and later parser
  implementation

## Excluded

Stage 2 excludes:

- production parser behavior
- resolver behavior
- graph construction
- generated Pydantic model generation except for a small test-backed spike
- CLI behavior beyond an optional namespace
- source distribution or publishing setup beyond local package metadata

## Boundary Rule

If a change requires deciding ETCM language semantics beyond the current docs,
it belongs in Stage 3 or later. Stage 2 may name the data structure where that
semantic result will live, but should not implement the semantic behavior.
