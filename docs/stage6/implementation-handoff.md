# Stage 6 Implementation Handoff

Stage 6 leaves CLI out intentionally. The next stage should add thin wrappers
over the Python APIs:

- `etcm validate <selector>`: `validate(resolve(selector))`
- `etcm resolve <selector> --format json`: graph JSON
- `etcm inspect <selector>`: graph and field schema summary
- `etcm graph <selector>`: JSON or DOT graph output

Do not move parser, resolver, validation, or conversion logic into CLI code.
