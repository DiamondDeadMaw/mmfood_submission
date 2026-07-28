from typing import List, Tuple

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

import config

LABELS = {0: "ENTAILMENT", 1: "NEUTRAL", 2: "CONTRADICTION"}

_MODEL = None
_TOKENIZER = None


def _load():
    global _MODEL, _TOKENIZER
    if _MODEL is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _TOKENIZER = AutoTokenizer.from_pretrained(config.NLI_MODEL_NAME)
        _MODEL = AutoModelForSequenceClassification.from_pretrained(config.NLI_MODEL_NAME).to(device)
        _MODEL.eval()


def classify_pairs(pairs: List[Tuple[str, str]], batch_size: int = 64, max_length: int = 256) -> List[str]:
    if not pairs:
        return []

    _load()
    device = next(_MODEL.parameters()).device

    all_labels = []
    for i in range(0, len(pairs), batch_size):
        chunk = pairs[i:i + batch_size]
        premises, hypotheses = zip(*chunk)
        inputs = _TOKENIZER(
            list(premises), list(hypotheses),
            return_tensors="pt", padding=True, truncation=True, max_length=max_length,
        ).to(device)
        with torch.no_grad():
            logits = _MODEL(**inputs).logits
            all_labels.extend(torch.argmax(logits, dim=1).tolist())

    return [LABELS[label_id] for label_id in all_labels]
