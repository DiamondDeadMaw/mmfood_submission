import spacy

import config

spacy.prefer_gpu()
nlp = spacy.load(config.NER_MODEL_DIR)


def annotate_ingredients(text: str):
    doc = nlp(text)
    if not doc.ents:
        return None
    return [
        {"text": ent.text, "label": ent.label_, "start": ent.start_char, "end": ent.end_char}
        for ent in doc.ents
    ]


def _extract_from_ents(text, ents):
    qty_ent = next((e for e in ents if e["label"] == "QUANTITY"), None)
    unit_ent = next((e for e in ents if e["label"] == "UNIT"), None)
    state_ent = next((e for e in ents if e["label"] == "STATE"), None)
    ing_ents = [e for e in ents if e["label"] == "ING"]

    modifiers = []
    if qty_ent and unit_ent and qty_ent["start"] < unit_ent["start"]:
        modifiers.append(text[qty_ent["start"]:unit_ent["end"]])
    elif qty_ent:
        modifiers.append(qty_ent["text"])
    if state_ent:
        modifiers.append(state_ent["text"])

    if ing_ents:
        ingredient = " ".join(e["text"] for e in sorted(ing_ents, key=lambda x: x["start"]))
    else:
        spans_to_remove = []
        if qty_ent and unit_ent:
            spans_to_remove.append((qty_ent["start"], unit_ent["end"]))
        elif qty_ent:
            spans_to_remove.append((qty_ent["start"], qty_ent["end"]))
        if state_ent:
            spans_to_remove.append((state_ent["start"], state_ent["end"]))

        chars = list(text)
        for st, en in sorted(spans_to_remove, reverse=True):
            for i in range(st, en):
                chars[i] = ""
        ingredient = "".join(chars).strip(" ,;:").strip()
        if ingredient.lower().startswith("of "):
            ingredient = ingredient[3:]

    return modifiers, ingredient


def extract_modifiers_and_ingredient(text: str):
    ents = annotate_ingredients(text) or []
    return _extract_from_ents(text, ents)


def extract_modifiers_and_ingredient_batch(texts, batch_size=64):
    results = []
    for doc in nlp.pipe(texts, batch_size=batch_size):
        ents = [
            {"text": ent.text, "label": ent.label_, "start": ent.start_char, "end": ent.end_char}
            for ent in doc.ents
        ]
        results.append(_extract_from_ents(doc.text, ents))
    return results
