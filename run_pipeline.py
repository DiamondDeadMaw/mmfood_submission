import argparse
import json
import sys

from verification.validator import validate_full_pipeline


def run_one(doc):
    results, extracted = validate_full_pipeline(doc["text"], doc["extracted"])
    return {"results": results, "extracted": extracted}


def main():
    parser = argparse.ArgumentParser(description="Run the MMFood recipe-extraction verification pipeline.")
    parser.add_argument("--input", required=True, help="Path to a JSON file: {text, extracted} or a list of such objects.")
    parser.add_argument("--output", help="Path to write the report JSON. Defaults to stdout.")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        payload = json.load(f)

    if isinstance(payload, list):
        output = [run_one(doc) for doc in payload]
    else:
        output = run_one(payload)

    serialized = json.dumps(output, indent=2, default=str)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(serialized)
    else:
        sys.stdout.write(serialized + "\n")


if __name__ == "__main__":
    main()
