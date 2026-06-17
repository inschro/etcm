# ETCM Product Spec

## Positioning

ETCM should become the boring default for projects where configuration is part
of the system architecture.

The first adoption promise:

```bash
pip install etcm
```

Then:

```bash
etcm validate configs/train.etcm#smoke
etcm resolve configs/train.etcm#smoke
python -c 'from etcm import load; print(load("configs/train.etcm#smoke"))'
```

The product should feel obvious for any Python project that currently has:

- many YAML files with fragile `$ref` or include conventions
- Pydantic models duplicated beside config files
- CLI overrides that can silently change critical fields
- ML experiments whose resolved config must be captured for replay
- runtime graphs made from optimizers, schedulers, datasets, launchers, and
  callbacks

ETCM is a typed config core first. ML is the primary proving ground because the
pain is concentrated there, but the language should not be ML-specific.

## Reference Project: ANF Config Builder

The initial idea came from the config builder in
`/home/ingo/code_stuff/attentive_neural_fabric`.

Useful behavior to generalize:

- registry files declare one Python schema and many named artifacts
- selectors use `path#artifact`, with `#default` when omitted
- `$ref` composes artifacts across files
- refs resolve relative to the current config file
- sibling keys beside `$ref` override the referenced payload
- dot-path overrides support CLI-style changes
- resolution detects cycles and excessive depth
- final payloads validate through Pydantic
- resolved configs are written beside runtime outputs

Important limitations to fix:

- schema lives in Python, so the config file is not the source of truth
- refs are resolved as dictionaries before assignability is type-checked
- override policy is implicit and controlled by the resolver
- source identity is mostly lost after Pydantic materialization
- syntax is YAML-shaped, so spec declarations and implementation declarations
  are not visually distinct

ETCM should keep the operational lessons and remove the duplication.

## Landscape

| Tool | What it proves | ETCM response |
| --- | --- | --- |
| [Hydra](https://hydra.cc/docs/intro/) | Config composition, CLI overrides, multirun, remote launchers, and research workflow ergonomics matter. | Keep composition and override ergonomics, but make typed graph references and spec-owned override policy core. |
| [OmegaConf structured configs](https://omegaconf.readthedocs.io/en/latest/structured_config.html) | Runtime type safety and static-checker-friendly schemas are valuable in Python config. | Generate Python views from ETCM instead of requiring users to define schema in Python first. |
| [Pydantic](https://docs.pydantic.dev/latest/concepts/json_schema/) | Python users expect strong validation and JSON Schema export. | Make Pydantic the first generated binding target. |
| [CUE](https://cuelang.org/docs/introduction/) | Configuration and validation benefit from a constraint-oriented language with strong semantics. | Adopt explicit constraints, but keep v0 smaller than CUE's full unification model. |
| [Gin Config](https://github.com/google/gin-config/blob/master/README.md) | ML users want concise wiring of nested callables and experiment parameters. | Support graph composition without arbitrary Python execution in core. |
| [Lightning CLI](https://lightning.ai/docs/pytorch/stable/cli/lightning_cli.html) | Training stacks need CLI-configurable classes and reproducible hyperparameters. | Offer typed config objects and resolved graph capture independent of a training framework. |
| [W&B Sweeps](https://docs.wandb.ai/models/sweeps/define-sweep-configuration) | Sweep specs are configuration artifacts with search methods, metrics, and parameters. | Treat sweeps as a future extension over typed implementations. |
| [Hugging Face Accelerate](https://huggingface.co/docs/accelerate/en/package_reference/cli) | Distributed runtime setup often becomes its own config workflow. | Represent launch/runtime configs as typed graph nodes, not ad hoc side files. |

## Use Cases

### ML Experiment Composition

```etcm
spec TrainRun:
  model: LMConfig
  data: DataStream
  optimizer: Optimizer
  scheduler: LRScheduler | null = Field(default=null)
  runtime: Runtime
  max_steps: int = Field(gt=0)

impl smoke:
  $model: models/lm.etcm#tiny
  $data: data/streams.etcm#smoke
  $optimizer: optimizers/adamw.etcm#fast
  $runtime: runtime/local.etcm#cpu
  max_steps: 2
```

Why ETCM helps:

- refs are type-checked
- config graph can be saved beside checkpoints
- CLI overrides can be forbidden for seed, checkpoint, or account fields
- generated Python objects are ready for training code

### Hyperparameter Sweeps

```etcm
spec Sweep:
  target: TrainRun
  metric: str
  method: str = Field(choices=["grid", "random", "bayes"])
  parameters: dict[str, SweepParameter]

impl lr_search:
  $target: experiments/train.etcm#baseline
  metric: "validation.loss"
  method: "random"
  parameters:
    optimizer.lr:
      values: [1e-4, 3e-4, 1e-3]
```

Sweep support should be layered over the core. The target remains a typed
implementation, and parameter paths must be validated against the target graph.

### Distributed And HPC Runtime

```etcm
spec Runtime:
  launcher: str = Field(choices=["local", "torchrun", "slurm"])
  device: str = Field(choices=["auto", "cpu", "cuda"])
  nodes: int = Field(default=1, gt=0)
  gpus_per_node: int = Field(default=1, ge=0)
  account: str | null = Field(default=null, override="deny")

impl slurm_a100:
  launcher: "slurm"
  device: "cuda"
  nodes: 1
  gpus_per_node: 4
```

Why ETCM helps:

- cluster-specific values are explicit implementations
- forbidden overrides protect billing/account fields
- resolved runtime config can be written into job outputs

### Production Settings

```etcm
spec ServiceSettings:
  environment: str = Field(choices=["dev", "staging", "prod"])
  api_base_url: str
  timeout_seconds: float = Field(default=30.0, gt=0.0)
  credentials_ref: str = Field(override="deny")

impl prod:
  environment: "prod"
  api_base_url: "https://api.example.com"
  credentials_ref: "vault://services/example/prod"
```

ETCM should not manage secrets. It should type-check and protect references to
secret providers.

### Filesystem Paths

```etcm
spec DataConfig:
  train_file: Path = Field(path_exists="must_exist", path_kind="file")
  output_dir: Path = Field(path_exists="allow_missing", path_kind="dir")
  cache_dir: Path = Field(path_exists="resolver", path_kind="dir")
```

Why ETCM helps:

- paths are typed instead of stringly-typed
- path values resolve relative to the file that declares them
- individual fields can require existing paths or allow future-created paths
- the resolver can make delegated path fields permissive locally and strict in
  CI

### Reusable Infrastructure Components

```etcm
spec BatchJob:
  image: str
  command: list[str]
  resources: Resources
  retry: RetryPolicy

impl tokenizer_job:
  image: "registry.example.com/tokenizer:2026-06-17"
  command: ["python", "-m", "jobs.tokenize"]
  $resources: infra/resources.etcm#cpu_large
  $retry: infra/retry.etcm#standard
```

ETCM gives infra-like configs the same graph identity and validation as ML
configs without becoming a scheduler.

## V0 Product Requirements

V0 should include:

- `.etcm` parser for spec and implementation blocks
- selector support: `path#impl`, defaulting to `#default`
- top-level `$spec` reuse for implementation-only files
- fragment-free spec inheritance and `$spec` references because every file has
  one spec source
- primitive types: `str`, `int`, `float`, `bool`, `null`, `Path`
- containers: `list[T]`, `dict[K, V]`
- field-level path validation with `path_exists` and `path_kind`
- resolver-level default path existence policy
- spec references by name and imported selector
- implementation inheritance
- reference resolution with source identity
- spec-owned override policy
- validation errors with source path and graph path
- generated Pydantic models
- `load()`, `validate`, `resolve`, `inspect`, and `graph`
- resolved JSON export for reproducibility

V0 should not include:

- arbitrary Python execution from config
- remote execution or job submission
- sweep execution
- package registries
- plugin systems
- secrets loading
- automatic migration from every existing config format

## Success Criteria

ETCM is useful when a user can:

- write one spec and several implementations in one file
- write implementation-only files with top-level `$spec`
- compose implementations across files with typed refs
- validate path fields with field-level and resolver-level existence policy
- get a precise error for a bad reference or invalid override
- load a Pydantic object without writing a Pydantic schema by hand
- save a resolved graph that explains what actually ran
- inspect graph nodes and source locations from the CLI

The early "no-brain pip install" benchmark is:

> A Python ML project with hand-rolled YAML configs can replace its resolver
> with ETCM in one afternoon and immediately gain typed refs, override policy,
> CLI validation, and resolved graph capture.
