# Stage 3 References

## Internal References

- [Manifest](../manifest.md): product thesis and use case direction.
- [Product Spec](../product_spec.md): v0 language semantics and examples.
- [Roadmap](../roadmap.md): Stage 3 and Stage 4 boundaries.
- [Stage 1 Tooling Decisions](../stage1/tooling-decisions.md): parser,
  validation, CLI, and test tooling choices.
- [Stage 1 Parser Hardening](../stage1/parser-decision-hardening.md): evidence
  level for Lark indentation, alternatives, and CLI policy.
- [Stage 2 API Contract](../stage2/api-contract.md): public Python API shape.
- [Stage 2 IR Contract](../stage2/ir-contract.md): parser-independent IR shell.
- [Stage 2 Fixture Contract](../stage2/fixture-contract.md): first fixture
  tree and initial examples.

## External References

- Lark documentation: <https://lark-parser.readthedocs.io/>
- Lark grammar reference: <https://lark-parser.readthedocs.io/en/stable/grammar.html>
- Lark visitors and transformers: <https://lark-parser.readthedocs.io/en/stable/visitors.html>
- Pydantic dynamic model documentation: <https://docs.pydantic.dev/latest/concepts/models/#dynamic-model-creation>
- Python `argparse` documentation: <https://docs.python.org/3/library/argparse.html>

These sources explain the selected tools. Stage 3 itself is primarily grounded
in local project decisions and fixture design, not new tool research.
