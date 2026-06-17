# Stage 5 Implementation Handoff

Stage 5 handed Stage 6 a resolved graph that could be validated during
resolution. Stage 6 splits this into orthogonal pipeline stages.

Stage 6 should consume `ResolvedGraph` and implement:

- `load(..., target="pydantic")`
- `convert(graph, target=...)`
- dataclass and dict materialization
- generated schema summaries
- CLI wrappers over public Python APIs

Do not move resolver logic into generated views or CLI code.
