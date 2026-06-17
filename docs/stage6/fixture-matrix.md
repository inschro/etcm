# Stage 6 Fixture Matrix

Stage 6 extends the fixture contract with:

- graph goldens that include `validated`, field schemas, and value provenance
- resolver diagnostics for `E_CONSTRAINT`
- Pydantic schema summary goldens
- generated-view tests for dict, dataclass, and Pydantic materialization

New invalid fixtures cover:

- failed `choices`
- failed numeric bound
- failed length bound
- failed regex
- malformed constraint metadata

Generated-view tests cover:

- nested refs
- immutable dataclass objects
- immutable Pydantic objects
- path serialization differences between dict and object views
- `convert()` validation guard and `force=True`
