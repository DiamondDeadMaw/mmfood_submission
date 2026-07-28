from typing import Dict, List

import torch
from sentence_transformers import SentenceTransformer

import config
from Models.ingredient_ner.inference import extract_modifiers_and_ingredient
from Models.suspicious_ingredient.model import SetTransformerForClassification

_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
_embedder = None
_embeddings = None
_model = None


def _load_embeddings(path):
    if not path.exists():
        return {}
    raw = torch.load(path, map_location="cpu")
    return {k: v.float().cpu() if isinstance(v, torch.Tensor) else torch.tensor(v, dtype=torch.float32) for k, v in raw.items()}


def _initialize():
    global _embedder, _embeddings, _model
    if _embedder is None:
        _embedder = SentenceTransformer("thenlper/gte-large")
    if _embeddings is None:
        _embeddings = _load_embeddings(config.SUSPICIOUS_EMBEDDINGS_PATH)
    if _model is None:
        _model = SetTransformerForClassification()
        if config.SUSPICIOUS_MODEL_PATH.exists():
            _model.load_state_dict(torch.load(config.SUSPICIOUS_MODEL_PATH, map_location=_DEVICE))
        _model.to(_DEVICE).eval()


def get_wrong_probabilities(ingredients: List[str]) -> Dict[str, float]:
    _initialize()

    cleaned_embeddings = []
    valid_keys = []

    for orig in ingredients:
        _, ing = extract_modifiers_and_ingredient(orig.strip().lower())
        ing = ing.strip().lower()
        if not ing:
            continue

        if ing not in _embeddings:
            _embeddings[ing] = _embedder.encode(ing, convert_to_tensor=True).cpu().float()

        cleaned_embeddings.append(_embeddings[ing])
        valid_keys.append(orig)

    if not cleaned_embeddings:
        return {}

    length = len(cleaned_embeddings)
    x = torch.stack(cleaned_embeddings, dim=0).unsqueeze(0).to(_DEVICE)
    padding_mask = torch.zeros(1, length, dtype=torch.bool).to(_DEVICE)

    with torch.no_grad():
        logits = _model(x, padding_mask).squeeze(0).squeeze(-1)
        if logits.dim() == 0:
            logits = logits.unsqueeze(0)
        probs = torch.sigmoid(logits).cpu().tolist()

    return {orig: 1.0 - p for orig, p in zip(valid_keys, probs)}
