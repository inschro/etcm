# Stage 2 IR Contract

Stage 2 introduces immutable dataclasses that describe the shape of ETCM data
without implementing semantic resolution.

## Required Types

`SourceSpan`

- `source_path: Path`
- `line: int`
- `column: int`
- `end_line: int`
- `end_column: int`
- `start_pos: int | None`
- `end_pos: int | None`

`Selector`

- `path: Path`
- `implementation: str | None`
- `raw: str | None`

`Document`

- `source_path: Path`
- `spec: SpecDef | None`
- `spec_ref: SpecRef | None`
- `implementations: tuple[ImplDef, ...]`

`SpecDef`

- `name: str`
- `parent: Path | None`
- `fields: tuple[FieldDef, ...]`
- `span: SourceSpan | None`

`SpecRef`

- `path: Path`
- `span: SourceSpan | None`

`FieldDef`

- `name: str`
- `type_expr: TypeExpr`
- `default: LiteralValue | None`
- `metadata: Mapping[str, LiteralValue]`
- `override: str`
- `span: SourceSpan | None`

`ImplDef`

- `name: str`
- `parent: Selector | None`
- `assignments: tuple[Assignment | RefAssignment, ...]`
- `span: SourceSpan | None`

## Literal And Type Shells

Stage 2 can keep literal and type shells simple:

- `TypeExpr` as a frozen dataclass with `kind`, `name`, and `args`
- `LiteralValue` as a frozen dataclass with `kind` and `value`
- `Assignment` with a field path and literal value
- `RefAssignment` with a field name and selector

## Rules

- All IR dataclasses are frozen.
- Collections are tuples or mappings treated as immutable by convention.
- IR does not normalize cross-file semantics.
- IR stores unresolved values and source spans for later resolver stages.
- Duplicate checks may be deferred unless local construction makes them trivial.

