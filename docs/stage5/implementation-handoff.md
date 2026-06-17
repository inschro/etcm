# Stage 5 Implementation Handoff

Stage 5 hands Stage 6 a resolved graph that is already semantically valid.

Stage 6 should consume `ResolvedGraph` and implement:

- `load(..., as_="pydantic")`
- dataclass and dict materialization
- generated schema summaries
- CLI wrappers over public Python APIs

Do not move resolver logic into generated views or CLI code.
