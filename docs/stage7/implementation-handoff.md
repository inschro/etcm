# Stage 7 Implementation Handoff

Stage 7 completes the first usable CLI wrapper over the Python API.

The next stage should focus on standalone package installability rather than
expanding the CLI command surface by default:

- package metadata for wheel, local checkout, and Git URL installs
- installation smoke tests from a built wheel
- real example configs outside the test fixture tree
- install docs that make the current non-PyPI distribution path clear

Defer JSON Schema export, migration examples, publishing automation, and graph
visualization until the standalone install path is proven.

Keep the CLI thin. Parser, resolver, validation, conversion, and serialization
contracts should remain owned by package APIs.
