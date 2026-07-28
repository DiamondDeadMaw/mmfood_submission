import argparse
import ast
import json
import os
import random
import re
from typing import Dict, List, Tuple

import pandas as pd


def clean_text(text: str, remove_punct: bool = False) -> str:
    if remove_punct:
        text = re.sub(r'[(),;:]', '', text)
    return text


def parse_tasteset_row(entities_json: str) -> List[Dict]:
    try:
        entities = ast.literal_eval(entities_json)
    except (ValueError, SyntaxError):
        return []

    parsed_entities = []
    for ent in entities:
        spans = re.findall(r'\((\d+),\s*(\d+)\)', ent.get('span', '[]'))
        if spans:
            start, end = int(spans[0][0]), int(spans[0][1])
            parsed_entities.append({'start': start, 'end': end, 'type': ent.get('type'), 'text': ent.get('entity')})

    parsed_entities.sort(key=lambda x: x['start'])
    return parsed_entities


def extract_true_pairs(entities: List[Dict]) -> List[Tuple[Dict, Dict]]:
    pairs = []
    current_qty, current_unit = None, None

    for ent in entities:
        if ent['type'] == 'QUANTITY':
            current_qty = ent
        elif ent['type'] == 'UNIT':
            current_unit = ent
        elif ent['type'] == 'FOOD' and (current_qty or current_unit):
            measure_text = [e['text'] for e in (current_qty, current_unit) if e]
            pairs.append(({'type': 'MEASURE', 'text': " ".join(measure_text)}, ent))
            current_qty, current_unit = None, None

    return pairs


def generate_sentence_pairs(text, true_pairs, all_foods, all_measures, augment=False) -> List[Dict]:
    samples = []
    if not all_foods or not all_measures:
        return samples

    if augment and random.random() < 0.3:
        for measure, food in true_pairs:
            sep = ", " if random.choice([True, False]) else " "
            samples.append({"text": f"[E2]{food['text']}[/E2]{sep}[E1]{measure['text']}[/E1]", "label": 1})

            neg_foods = [f for f in all_foods if f['text'] != food['text']]
            if neg_foods:
                neg_food = random.choice(neg_foods)
                samples.append({"text": f"[E2]{neg_food['text']}[/E2]{sep}[E1]{measure['text']}[/E1]", "label": 0})
        return samples

    for measure in all_measures:
        true_food = next((tp_f for tp_m, tp_f in true_pairs if tp_m['text'] == measure['text']), None)

        for food in all_foods:
            if measure['text'] not in text or food['text'] not in text:
                continue

            m_escaped, f_escaped = re.escape(measure['text']), re.escape(food['text'])
            marked_text = re.sub(rf"\b{m_escaped}\b", f"[E1]{measure['text']}[/E1]", text, count=1)
            marked_text = re.sub(rf"\b{f_escaped}\b", f"[E2]{food['text']}[/E2]", marked_text, count=1)

            if "[E1]" not in marked_text:
                marked_text = text.replace(measure['text'], f"[E1]{measure['text']}[/E1]", 1)
            if "[E2]" not in marked_text:
                marked_text = marked_text.replace(food['text'], f"[E2]{food['text']}[/E2]", 1)

            label = 1 if (true_food and food['text'] == true_food['text']) else 0
            samples.append({"text": marked_text, "label": label})

    return samples


def process_tasteset(csv_path: str, output_path: str, num_mashed: int = 2000, seed: int = 42):
    random.seed(seed)
    df = pd.read_csv(csv_path)

    clean_recipes = []
    all_samples = []

    for _, row in df.iterrows():
        text = " ".join(str(row['ingredients']).replace("\n", " ").replace("\r", " ").split())
        text = clean_text(text, remove_punct=random.random() < 0.2)

        entities = parse_tasteset_row(str(row['ingredients_entities']))
        foods = [e for e in entities if e['type'] == 'FOOD']
        true_pairs = extract_true_pairs(entities)
        measures = [m for m, _ in true_pairs]

        clean_recipes.append({'text': text, 'true_pairs': true_pairs, 'foods': foods, 'measures': measures})
        all_samples.extend(generate_sentence_pairs(text, true_pairs, foods, measures, augment=True))

    for _ in range(num_mashed):
        selected = random.sample(clean_recipes, random.randint(2, 4))
        candidates = [r for r in selected if r['true_pairs']]
        if not candidates:
            continue

        mashed_text = " ".join(r['text'].strip() for r in selected)
        target_recipe = random.choice(candidates)
        true_m, true_f = random.choice(target_recipe['true_pairs'])

        pos_text = mashed_text.replace(true_m['text'], f"[E1]{true_m['text']}[/E1]", 1)
        pos_text = pos_text.replace(true_f['text'], f"[E2]{true_f['text']}[/E2]", 1)
        all_samples.append({"text": pos_text, "label": 1})

        other_recipes = [r for r in selected if r != target_recipe and r['foods']]
        if other_recipes:
            distractor_food = random.choice(random.choice(other_recipes)['foods'])
            neg_text = mashed_text.replace(true_m['text'], f"[E1]{true_m['text']}[/E1]", 1)
            neg_text = neg_text.replace(distractor_food['text'], f"[E2]{distractor_food['text']}[/E2]", 1)
            all_samples.append({"text": neg_text, "label": 0})

    random.shuffle(all_samples)
    valid_samples = [s for s in all_samples if "[E1]" in s['text'] and "[E2]" in s['text']]

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        for sample in valid_samples:
            f.write(json.dumps(sample) + '\n')

    print(f"Wrote {len(valid_samples)} training pairs to {output_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasteset-csv", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--num-mashed", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    process_tasteset(args.tasteset_csv, args.output, args.num_mashed, args.seed)


if __name__ == "__main__":
    main()
