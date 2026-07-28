import argparse
import random
from pathlib import Path

import spacy
from spacy.training import Example
from spacy.tokens import DocBin
from spacy.util import minibatch
from tqdm import tqdm

LABELS = ["ING", "QUANTITY", "STATE", "UNIT", "PRODUCT"]


def load_examples(nlp, path):
    docbin = DocBin().from_disk(path)
    docs = list(docbin.get_docs(nlp.vocab))
    return [
        Example.from_dict(doc, {"entities": [(ent.start_char, ent.end_char, ent.label_) for ent in doc.ents]})
        for doc in docs
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--n-iter", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    nlp = spacy.blank("en")

    train_examples = load_examples(nlp, data_dir / "train.spacy")
    test_examples = load_examples(nlp, data_dir / "test.spacy")

    ner = nlp.add_pipe("ner")
    for label in LABELS:
        ner.add_label(label)
    nlp.initialize(get_examples=lambda: train_examples)

    optimizer = nlp.create_optimizer()
    for i in range(args.n_iter):
        random.shuffle(train_examples)
        losses = {}
        for batch in tqdm(list(minibatch(train_examples, size=args.batch_size)), desc=f"Epoch {i + 1}/{args.n_iter}"):
            nlp.update(batch, sgd=optimizer, losses=losses)
        print(f"Epoch {i + 1}: {losses}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    nlp.to_disk(output_dir)
    print(f"Saved model to {output_dir}")

    scorer = nlp.evaluate(test_examples)
    print(scorer)


if __name__ == "__main__":
    main()
