# ETCM Architecture Roadmap

This roadmap is intentionally front-loaded with software architecture decisions.
Before implementing the first parser core, ETCM needs a clear toolchain,
module boundary, intermediate representation, resolver strategy, and test
contract. The goal is a small but durable package that config-heavy Python
projects can try quickly without locking the project into a brittle parser or
runtime design.

## Phase 0: Product Contract And Examples

Deliverables:

- manifest, product spec, and realistic examples for ML, runtime, paths,
  sweeps, service settings, and batch jobs
- v0 semantics for specs, implementations, selectors, refs, inheritance,
  validation, override policy, `Path`, generated bindings, and graph export
- example corpus that can become parser and resolver fixtures

Acceptance:

- docs explain why ETCM differs from Hydra, OmegaConf, Pydantic, CUE, Gin,
  Lightning CLI, W&B sweeps, and Accelerate
- examples are concrete enough to become golden tests
- non-goals are explicit

## Phase 1: Architecture And Tool Selection

Decide and document the implementation strategy before writing parser code.
Record decisions as short ADR-style docs so future changes are intentional.
The completed Stage 1 notes live in [stage1/](stage1/).

Tool decisions:

- Packaging: use `pyproject.toml` with `hatchling` and `uv` for repeatable local
  development, matching the reference ANF repo style.
- Python target: use Python 3.12+ for modern typing, `pathlib`, and stable
  dataclass behavior.
- Parser: evaluate Lark, ANTLR, tree-sitter, and a hand-written recursive
  descent parser; default to Lark for v0 unless a spike proves source spans,
  grammar ergonomics, or packaging are poor.
- Validation/runtime: generate Pydantic v2 models first; keep dataclass and dict
  views as adapters over the same resolved graph.
- CLI: use `typer` or `argparse`; default to `typer` only if dependency weight
  is acceptable, otherwise keep `argparse`.
- Formatting/lint/type checks: use Ruff and basedpyright from the start.
- Testing: use pytest with golden fixtures and snapshot-like resolved JSON
  outputs stored as ordinary text files.

Architecture decisions:

- Source parsing must produce syntax nodes with file, line, column, and raw text
  spans; semantic resolution must not depend on parser-specific node classes.
- The core IR must be immutable after construction and separate from generated
  Pydantic/dataclass views.
- Resolver output is a typed graph with node identity, source identity, parent
  edges, reference edges, applied overrides, and materialized values.
- `Path` values resolve relative to the source file that declared the value,
  not relative to the process working directory or root selector.
- Resolver settings, including `path_exists`, must be explicit configuration,
  not global process state.
- CLI commands are thin wrappers over public Python APIs.

Acceptance:

- ADRs or roadmap notes choose parser, package tooling, CLI framework, test
  strategy, and public module boundaries.
- The chosen parser has a spike proving comments, source spans, basic blocks,
  nested literals, and useful error messages.
- The chosen validation path proves one generated Pydantic model with field
  constraints and one `Path` field.

## Phase 2: Public API And Module Boundaries

Define the package surface before implementing behavior.
The Stage 2 scaffold notes live in [stage2/](stage2/).

Planned modules:

- `etcm.syntax`: parser-facing AST, source locations, syntax diagnostics
- `etcm.ir`: spec, implementation, field, selector, literal, and type IR
- `etcm.resolve`: resolver, graph builder, override policy, path policy
- `etcm.codegen`: Pydantic/dataclass/dict view generation
- `etcm.cli`: command entrypoints only
- `etcm.errors`: stable exception and diagnostic types

Public API:

```python
from etcm import Resolver, convert, load, resolve, validate

cfg = load("configs/train.etcm#smoke", target="pydantic")
graph = resolve("configs/train.etcm#smoke")
graph = validate(graph)
cfg = convert(graph, target="pydantic")

resolver = Resolver(path_exists="must_exist")
cfg = resolver.load("configs/train.etcm#smoke", target="pydantic")
```

Core data contracts:

- `Selector`: normalized path plus optional implementation fragment
- `SpecDef`: name, optional parent spec path, fields, source span
- `SpecRef`: top-level immutable `$spec` reference
- `ImplDef`: name, optional parent selector, assignments, refs, source span
- `FieldDef`: name, type expression, default, validation metadata, override
  policy
- `ResolvedGraph`: immutable nodes and typed edges

Acceptance:

- public API signatures and exception types are documented before implementation
- internal modules do not expose parser-library node types
- graph/export structures are serializable without generated Pydantic objects

## Phase 3: Fixtures And Test Contract

Create the test corpus before the parser implementation.
The Stage 3 fixture contract notes live in [stage3/](stage3/).

Fixture groups:

- valid inline spec files
- implementation-only files with top-level `$spec`
- spec inheritance without fragments
- implementation inheritance with `#impl`
- typed refs across files
- `Path` fields with `must_exist`, `allow_missing`, and resolver-controlled
  policy
- malformed files for duplicate specs, duplicate fields, invalid literals,
  missing selectors, cycles, bad refs, bad overrides, and bad paths

Golden outputs:

- parsed AST summary
- normalized IR summary
- resolved graph JSON
- generated Pydantic schema summary
- diagnostic text for expected failures

Acceptance:

- fixtures encode every v0 behavior before parser work begins
- each expected failure has a stable diagnostic requirement
- golden resolved JSON includes source files and graph paths

## Phase 4: Parser Core

Implement the parser only after the architecture decisions and fixtures exist.
The Stage 4 parser core notes live in [stage4/](stage4/).

Parser requirements:

- parse `spec`, top-level `$spec`, `impl`, field declarations, refs, inheritance,
  literals, type expressions, and `Field(...)` metadata
- preserve source location for every definition, assignment, ref, and literal
- support YAML-style `#` comments and trailing commas where specified by the
  grammar decision
- keep attached selector fragments such as `path.etcm#impl` distinct from
  comments
- reject files that define both inline `spec` and top-level `$spec`
- reject multiple specs in one file
- reject duplicate field names and duplicate implementation names
- parse `Path` type annotations and path metadata without performing filesystem
  checks

Acceptance:

- parser passes all AST/IR fixture tests
- parse errors include file, line, column, and expected construct
- parser module has no resolver, filesystem, or Pydantic dependency

## Phase 5: Resolver And Type Checker

Implement deterministic semantic resolution.

Resolver behavior:

- load selectors relative to the importing file
- apply spec inheritance or top-level `$spec` reuse before implementation
  validation
- apply implementation inheritance before local assignments
- resolve `$field` references into typed child nodes
- detect cycles in spec inheritance, implementation inheritance, and refs
- enforce assignability for referenced implementations
- enforce override policies for inherited and CLI overrides
- resolve `Path` values relative to the source file that declared the value
- enforce field-level path existence and kind policies, with resolver-level
  defaults for delegated fields

Diagnostics:

- include selector, source file, field path, graph path, and source span
- distinguish parse errors, missing selectors, type errors, validation errors,
  path validation errors, override-policy errors, and cycles
- path errors show the original path text, resolved absolute path, source file,
  existence policy, and expected kind

Acceptance:

- bad refs fail before runtime materialization
- denied overrides fail with the field policy in the message
- reference cycles show the full selector chain
- resolved graph preserves implementation identity and source locations

## Phase 6: Orthogonal API And Generated Views

Build generated user-facing surfaces over the resolved graph. CLI remains a
later thin wrapper over the same Python APIs.

Pipeline:

- `resolve(selector)` builds an unvalidated graph object
- `validate(graph)` returns a graph with `validated=True`
- `convert(graph, target="pydantic")` returns generated views
- `load(selector, target="pydantic")` orchestrates the full pipeline

Generated views:

- `target="pydantic"` returns generated Pydantic models
- `target="dataclass"` returns generated dataclasses
- `target="dict"` returns a JSON-compatible payload

CLI:

```bash
etcm validate configs/train.etcm#smoke
etcm resolve configs/train.etcm#smoke --format json
etcm inspect configs/train.etcm#smoke
etcm graph configs/train.etcm#smoke --format dot
```

CLI behavior:

- `validate` checks parse, resolution, type compatibility, path policy, override
  policy, and constraints
- `resolve` prints the fully materialized payload or graph
- `inspect` prints spec fields, defaults, refs, parents, and source paths
- `graph` emits DOT or JSON graph output for external tools

Acceptance:

- generated Pydantic models enforce ETCM constraints
- generated objects are immutable by default
- resolved JSON export is stable under repeated runs
- conversion refuses unvalidated graphs unless `force=True`

## Phase 7: Bridges And Adoption

Only after the core is credible:

- import a subset of YAML registry files like the ANF builder uses
- generate `.etcm` skeletons from Pydantic models
- export JSON Schema from ETCM specs
- add a migration guide for Hydra/OmegaConf users
- add a sweep spec extension without sweep execution

Acceptance:

- a simple ANF-style YAML registry can be translated into ETCM
- generated Pydantic bindings are compatible with existing Python consumers
- docs include a migration path that does not require a full rewrite

## Test Matrix

Architecture:

- parser spike proves source spans and actionable errors
- Pydantic spike proves generated constraints and `Path` fields
- public APIs do not expose parser-library node classes

Core parser:

- valid one-spec file
- implementation-only file with top-level `$spec`
- no implementation file
- duplicate spec, field, and implementation errors
- invalid literals and incomplete blocks

Resolver:

- relative and absolute selectors
- omitted fragment defaults to `#default`
- spec inheritance and `$spec` references without fragments
- YAML-style comments do not consume attached selector fragments
- `Path` values resolved relative to the declaring config file
- `Path` fields with resolver default `allow_missing`
- `Path` fields with resolver default `must_exist`
- implementation inheritance in-file and cross-file
- spec inheritance in-file and cross-file
- missing file, missing spec, missing implementation
- spec, implementation, and ref cycles

Type checking:

- primitive mismatch
- container mismatch
- path value accepts strings and materializes as a typed path
- path kind rejects file where directory is required and directory where file is
  required
- missing path succeeds with `path_exists="allow_missing"`
- missing path fails with `path_exists="must_exist"`
- `path_exists="resolver"` follows the resolver setting
- reference assignability success through spec inheritance
- reference assignability failure for unrelated specs
- nullable refs and fields

Override policy:

- `allow` replacement
- `deny` failure
- `force_only` failure without force and success with force
- `append` for lists
- `merge` for mappings
- dot-path CLI override validation

Generated bindings:

- Pydantic generation for primitives, containers, nested refs, defaults, choices,
  numeric bounds, paths, and nullability
- dataclass generation for the same subset
- dict export stable ordering

CLI:

- successful validate
- failed validate with source path
- JSON resolve
- inspect output includes spec, implementation, parents, and refs
- graph output includes typed edges
