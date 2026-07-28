import argparse
import random
import re
from pathlib import Path

from spacy.tokens import DocBin
from tqdm import tqdm

NON_FOOD_BLOG_SENTENCES = [
    "Click here for more.",
    "Jump to recipe.",
    "Print this recipe.",
    "Leave a comment below.",
    "Read more.",
    "Read the full post.",
    "Subscribe for updates.",
    "Sign up for our newsletter.",
    "Follow me on Instagram.",
    "Watch the full video here.",
    "Pin this for later.",
    "Scroll down for the recipe.",
    "Check out my other recipes.",
    "Rate this recipe below.",
    "Save this recipe.",
    "Share this post.",
    "This post contains affiliate links.",
    "As an Amazon Associate I earn from qualifying purchases.",
]


def parse_conll(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        raw_data = f.read()

    all_sentences = []
    prev_was_newline = False
    sentence = []
    for char in tqdm(raw_data, total=len(raw_data), desc="Reading CoNLL"):
        if char == "\n" and not prev_was_newline:
            prev_was_newline = True
            continue
        if prev_was_newline:
            prev_was_newline = False
            if char == "\n":
                if sentence:
                    all_sentences.append("".join(sentence))
                    sentence = []
                continue
        sentence.append(char)

    examples = []
    for raw_sentence in all_sentences:
        tokens = re.sub(' +', ' ', raw_sentence.replace("\t", "")).split(" ")

        this_sentence = [tokens[i] for i in range(0, len(tokens), 2) if tokens[i] != ""]
        this_sentence = " ".join(this_sentence)

        entities = []
        num_word = 1
        last_start = 0
        for i, ch in enumerate(this_sentence):
            if ch == " ":
                entities.append((last_start, i, tokens[2 * num_word - 1]))
                num_word += 1
                last_start = i + 1
        if last_start < len(this_sentence):
            entities.append((last_start, len(this_sentence), tokens[2 * num_word - 1]))

        normalized = []
        for start, end, tag in entities:
            if tag.startswith("B-"):
                normalized.append([start, end, tag[2:]])
            elif tag.startswith("I-") and normalized and normalized[-1][2] == tag[2:]:
                normalized[-1][1] = end

        examples.append({"text": this_sentence, "entities": normalized})

    return examples


def drop_entities(example, max_drop=3):
    entities = example["entities"]
    if len(entities) <= 1:
        return example

    to_drop = min(random.choices([1, 2, 3], weights=[0.35, 0.35, 0.30], k=1)[0], len(entities) - 1)
    drop_idxs = set(random.sample(range(len(entities)), to_drop))

    text = example["text"]
    spans = sorted(
        [(s, e, lbl, idx) for idx, (s, e, lbl) in enumerate(entities)],
        key=lambda x: x[0], reverse=True,
    )

    for s, e, lbl, idx in spans:
        if idx not in drop_idxs:
            continue
        text = text[:s] + text[e:]
        length_removed = e - s
        spans = [
            (s2 - length_removed, e2 - length_removed, lbl2, idx2) if s2 > s else (s2, e2, lbl2, idx2)
            for (s2, e2, lbl2, idx2) in spans if idx2 != idx
        ]

    new_entities = [[s, e, lbl] for (s, e, lbl, _) in sorted(spans, key=lambda x: x[0])]
    return {"text": text, "entities": new_entities}


def shuffle_entities(example):
    entities = example["entities"]
    if not entities:
        return example

    text = example["text"]
    spans = sorted(entities, key=lambda x: x[0])

    segments = []
    prev = 0
    for s, e, _ in spans:
        segments.append(text[prev:s])
        segments.append(text[s:e])
        prev = e
    segments.append(text[prev:])

    entity_segs = segments[1::2]
    labels = [lbl for _, _, lbl in spans]
    combined = list(zip(entity_segs, labels))
    random.shuffle(combined)
    new_segs, new_labels = zip(*combined)

    new_segments = list(segments)
    for i in range(1, len(segments), 2):
        new_segments[i] = new_segs[(i - 1) // 2]
    new_text = "".join(new_segments)

    new_entities = []
    offset = 0
    for i, seg in enumerate(new_segments):
        if i % 2 == 1:
            new_entities.append([offset, offset + len(seg), new_labels[(i - 1) // 2]])
        offset += len(seg)

    return {"text": new_text, "entities": new_entities}


def augment(examples):
    augmented = []
    for example in tqdm(examples, desc="Augmenting (drop/shuffle)"):
        if random.random() < 0.5:
            augmented.append(drop_entities(dict(example)))
        else:
            augmented.append(shuffle_entities(dict(example)))

    i = 0
    n = len(examples)
    while i < n:
        k = random.randint(2, 10)
        if i + k > n:
            break
        group = examples[i:i + k]
        new_text = "".join(g["text"] for g in group)
        new_entities = []
        offset = 0
        for g in group:
            for s, e, lbl in g["entities"]:
                new_entities.append([s + offset, e + offset, lbl])
            offset += len(g["text"])
        augmented.append({"text": new_text, "entities": new_entities})
        i += k

    return examples + augmented


def add_negative_examples(examples):
    for sentence in NON_FOOD_BLOG_SENTENCES:
        for clause in re.split(r'[!.?]', sentence):
            if clause.strip():
                examples.append({"text": clause.strip(), "entities": []})
    return examples


def create_docbin(examples, output_path):
    import spacy

    nlp = spacy.blank("en")
    doc_bin = DocBin()
    for example in tqdm(examples, desc=f"Building {output_path.name}"):
        doc = nlp.make_doc(example["text"])
        ents = []
        for start, end, label in example["entities"]:
            span = doc.char_span(start, end, label=label)
            if span is not None:
                ents.append(span)
        doc.ents = ents
        doc_bin.add(doc)
    doc_bin.to_disk(output_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--conll", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--test-split", type=float, default=0.2)
    parser.add_argument("--augment", action="store_true")
    parser.add_argument("--add-negatives", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    examples = parse_conll(args.conll)
    if args.augment:
        examples = augment(examples)
    if args.add_negatives:
        examples = add_negative_examples(examples)

    random.shuffle(examples)
    split_idx = int(len(examples) * (1 - args.test_split))
    train_set, test_set = examples[:split_idx], examples[split_idx:]

    create_docbin(train_set, output_dir / "train.spacy")
    create_docbin(test_set, output_dir / "test.spacy")


if __name__ == "__main__":
    main()
