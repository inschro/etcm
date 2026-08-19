from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from etcm import load
from etcm.errors import ETCMError

DEFAULT_CONFIG = f"{Path(__file__).with_name('train.etcm')}#TrainRun:smoke"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build PyTorch objects from ETCM config.")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--set", dest="overrides", action="append", default=[])
    parser.add_argument("--force-overrides", action="store_true")
    return parser


def load_config(args: argparse.Namespace) -> Any:
    return load(
        args.config,
        target="dataclass",
        overrides=args.overrides,
        force_overrides=args.force_overrides,
        override_base=Path.cwd(),
    )


def build_objects(config: Any) -> tuple[Any, Any, Any, Any, Path]:
    import torch

    torch.manual_seed(config.seed)
    torch.set_num_threads(config.runtime.num_threads)
    device = torch.device(config.runtime.device)

    inputs = torch.randn(
        config.micro_batch_size,
        config.dataset["input_features"],
        device=device,
    )

    activation = {
        "relu": torch.nn.ReLU,
        "gelu": torch.nn.GELU,
    }[config.model.activation]
    layers: list[Any] = []
    in_features = config.dataset["input_features"]
    for _ in range(config.model.layers):
        layers.append(torch.nn.Linear(in_features, config.model.hidden_size))
        layers.append(activation())
        if config.model.dropout > 0:
            layers.append(torch.nn.Dropout(config.model.dropout))
        in_features = config.model.hidden_size
    layers.append(torch.nn.Linear(in_features, config.dataset["classes"]))

    model = torch.nn.Sequential(*layers).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.optimizer.learning_rate,
        weight_decay=config.optimizer.weight_decay,
    )
    logits = model(inputs)
    checkpoint = config.runtime.output_dir / f"{config.run_name}.pt"
    return inputs, model, optimizer, logits, checkpoint


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        config = load_config(args)
        inputs, model, optimizer, logits, checkpoint = build_objects(config)
    except ETCMError as exc:
        parser.error(f"{exc.diagnostic.code}: {exc.diagnostic.message}")
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))

    print(f"config: {config.run_name}")
    print(f"inputs: {tuple(inputs.shape)}")
    print(f"model: {model.__class__.__name__}")
    print(f"optimizer: {optimizer.__class__.__name__}")
    print(f"logits: {tuple(logits.shape)}")
    print(f"checkpoint: {checkpoint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
