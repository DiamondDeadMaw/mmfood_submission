import argparse
from pathlib import Path

from spacy.cli.train import train

DEFAULT_CONFIG = Path(__file__).resolve().parent / "config.cfg"


def main():
    parser = argparse.ArgumentParser(description="Train the roberta-base spaCy NER model via `spacy train`.")
    parser.add_argument("--data-dir", required=True, help="Directory holding train.spacy and test.spacy (from prepare_dataset.py).")
    parser.add_argument("--output-dir", required=True, help="spaCy writes model-best/ and model-last/ here.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--gpu-id", type=int, default=0, help="-1 for CPU (very slow with a transformer).")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    train(
        args.config,
        output_path=args.output_dir,
        use_gpu=args.gpu_id,
        overrides={
            "paths.train": str(data_dir / "train.spacy"),
            "paths.dev": str(data_dir / "test.spacy"),
        },
    )


if __name__ == "__main__":
    main()
