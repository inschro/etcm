# Stage 5 Reasoning

Stage 5 makes the parser output useful without committing to a generated runtime
view too early. The resolver therefore returns a small graph contract first.
That graph is the semantic source of truth for Stage 6 materializers, CLI
wrappers, schema export, and visualization.

## Why Resolve To A Graph

Config-driven ML projects frequently need more than a final object tree. Users
need to answer where a value came from, which implementation selected which
dependency, which files were loaded, and whether a path was resolved relative to
the intended source file. A graph preserves those answers while still exposing
materialized node values.

The graph also keeps Stage 5 independent from Pydantic or dataclass choices.
Generated views can change in Stage 6 without moving selector, inheritance,
reference, or path-validation logic into view code.

## Selector Resolution

Root selectors resolve relative to the process working directory because they
represent the caller boundary. Nested selectors resolve relative to the file
that declared them because reusable config packages should remain relocatable.
Omitted implementation names normalize to `default`.

Bare implementation names are accepted for local implementation inheritance and
local references. This keeps inheritance syntax concise while preserving `#` for
cross-file implementation selection.

## Type Checking

Stage 5 checks primitives, containers, unions, named references, and `Path`.
Named non-primitive fields require reference assignments so object identity and
dependency edges remain explicit in the graph.

`Path` is intentionally a first-class type. It resolves relative to the file
where the value was declared and records resolution metadata. Field metadata can
force existing paths, allow missing paths, delegate existence policy to the
resolver, and constrain expected path kind.

## Override Policy

Implementation inheritance applies parent values before local assignments.
Inherited values then follow field override policy:

- `allow` replaces the parent value
- `deny` rejects the override
- `force_only` rejects in Stage 5 because no force API exists yet
- `append` combines list values
- `merge` combines mapping values

This keeps policy enforcement near semantic resolution instead of deferring it
to generated runtime views.
