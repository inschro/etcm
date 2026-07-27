# Stage 5 Graph Contract

The resolver returns a `ResolvedGraph`.

Required properties:

- canonical absolute `root_selector` in `path.etcm#Spec:implementation` form
- deterministic `nodes`
- deterministic `edges`
- normalized `sources`
- materialized `values`
- path resolution metadata

Node ids are based on graph paths:

- root implementation: `root`
- referenced child: `root.model`
- nested child reference: `root.model.tokenizer`

Edges use these kinds:

- `spec_parent`
- `impl_parent`
- `ref`

Graph JSON is provided by `ResolvedGraph.to_dict(path_base=...)` for tests and
future CLI use.
