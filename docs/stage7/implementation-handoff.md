# Stage 7 Implementation Handoff

Stage 7 completes the first usable CLI wrapper over the Python API.

The next stage should focus on adoption-oriented capabilities rather than
expanding the CLI command surface by default:

- publish or installation smoke tests from a built wheel
- real example configs outside the test fixture tree
- JSON Schema export from ETCM specs
- migration examples for existing YAML/Pydantic projects
- optional graph visualization only if a concrete workflow needs it

Keep the CLI thin. Parser, resolver, validation, conversion, and serialization
contracts should remain owned by package APIs.
