from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retrain predictor and update model registry metadata")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--train-script", default="services/predictor/train_lstm.py")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--output", default="services/predictor/checkpoints/rps_lstm.pt")
    parser.add_argument("--registry", default="services/predictor/checkpoints/model_registry.json")
    parser.add_argument("--window-size", type=int, default=24)
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--max-rows", type=int, default=120000)
    parser.add_argument("--model-name", default="lstm-rps-cpu")
    return parser.parse_args()


def run_training(args: argparse.Namespace) -> None:
    cmd = [
        args.python,
        args.train_script,
        "--dsn",
        args.dsn,
        "--output",
        args.output,
        "--window-size",
        str(args.window_size),
        "--epochs",
        str(args.epochs),
        "--batch-size",
        str(args.batch_size),
        "--lr",
        str(args.lr),
        "--max-rows",
        str(args.max_rows),
    ]
    print("running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def update_registry(args: argparse.Namespace) -> None:
    output_path = Path(args.output)
    if not output_path.exists():
        raise RuntimeError(f"checkpoint not found: {output_path}")

    registry_path = Path(args.registry)
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    if registry_path.exists():
        data = json.loads(registry_path.read_text(encoding="utf-8"))
    else:
        data = {"active_model": None, "models": []}

    version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    model_entry = {
        "version": version,
        "name": args.model_name,
        "path": str(output_path).replace("\\", "/"),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training_config": {
            "window_size": args.window_size,
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "lr": args.lr,
            "max_rows": args.max_rows,
        },
        "status": "active",
    }

    data["active_model"] = version
    data.setdefault("models", []).append(model_entry)
    registry_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"updated registry: {registry_path}")
    print(f"active_model_version: {version}")


def main() -> None:
    args = parse_args()
    run_training(args)
    update_registry(args)


if __name__ == "__main__":
    main()
