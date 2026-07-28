import torch
import torch.nn.functional as F
from rapidfuzz import fuzz
from transformers import AutoModelForSequenceClassification, AutoTokenizer

import config
from Models.ingredient_ner.inference import annotate_ingredients

_MODEL = None
_TOKENIZER = None


def _load():
    global _MODEL, _TOKENIZER
    if _MODEL is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _TOKENIZER = AutoTokenizer.from_pretrained(config.RE_MODEL_DIR)
        _MODEL = AutoModelForSequenceClassification.from_pretrained(config.RE_MODEL_DIR).to(device)
        _MODEL.eval()


def _pair_measures(text, qty_ents, unit_ents, max_distance=15):
    measures = []
    used_units = set()
    for qty in qty_ents:
        best_unit, best_dist = None, max_distance + 1
        for unit in unit_ents:
            if unit['start'] in used_units:
                continue
            dist = abs(unit['start'] - qty['end'])
            if dist < max_distance and dist < best_dist:
                best_dist, best_unit = dist, unit

        if best_unit:
            used_units.add(best_unit['start'])
            measures.append({'qty': qty['text'], 'unit': best_unit['text'], 'full_text': text[qty['start']:best_unit['end']]})
        else:
            measures.append({'qty': qty['text'], 'unit': 'count', 'full_text': qty['text']})
    return measures


def extract_pairs_from_text(text: str, batch_size: int = 32, score_threshold: float = 0.30):
    ents = annotate_ingredients(text)
    if not ents:
        return {}

    ingredients = [e for e in ents if e['label'] == 'ING']
    qty_ents = [e for e in ents if e['label'] == 'QUANTITY']
    unit_ents = [e for e in ents if e['label'] == 'UNIT']

    measures = _pair_measures(text, qty_ents, unit_ents)
    if not measures or not ingredients:
        return {}

    _load()
    device = next(_MODEL.parameters()).device

    candidates = []
    meta = []
    for ing in ingredients:
        for measure in measures:
            marked = text.replace(measure['full_text'], f"[E1]{measure['full_text']}[/E1]", 1)
            marked = marked.replace(ing['text'], f"[E2]{ing['text']}[/E2]", 1)
            candidates.append(marked)
            meta.append((ing['text'], measure))

    scores = []
    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i + batch_size]
        inputs = _TOKENIZER(batch, return_tensors="pt", padding=True, truncation=True, max_length=256).to(device)
        with torch.no_grad():
            logits = _MODEL(**inputs).logits
            scores.extend(F.softmax(logits, dim=-1)[:, 1].tolist())

    all_candidates = [
        {'score': scores[idx], 'ing': ing_text, 'measure': measure, 'measure_id': id(measure)}
        for idx, (ing_text, measure) in enumerate(meta)
    ]
    all_candidates.sort(key=lambda x: x['score'], reverse=True)

    final_pairs = {}
    used_ings, used_measures = set(), set()
    for cand in all_candidates:
        if cand['score'] < score_threshold:
            continue
        ing_key = cand['ing'].lower()
        if ing_key not in used_ings and cand['measure_id'] not in used_measures:
            final_pairs[ing_key] = cand['measure']
            used_ings.add(ing_key)
            used_measures.add(cand['measure_id'])

    return final_pairs
