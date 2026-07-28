import argparse
import ast
import json
import random
from collections import defaultdict
from pathlib import Path

import torch
from sentence_transformers import SentenceTransformer
from torch.nn.functional import cosine_similarity
from tqdm import tqdm

from Models.ingredient_ner.inference import extract_modifiers_and_ingredient

MAX_EASY_NEG = 2
MAX_CROSS_CUISINE_NEG = 1
MAX_HARD_NEG = 2


def load_recipe_cards(recipe_dir: Path, cache_path: Path):
    if cache_path.exists():
        with open(cache_path, "r", encoding="utf-8") as f:
            return ast.literal_eval(f.read())

    all_ingredient_lists = []
    for filename in [f for f in recipe_dir.iterdir() if f.suffix == ".json"]:
        with open(filename, "r", encoding="utf-8") as f:
            try:
                recipes = json.load(f)["recipes"]
            except Exception:
                continue

        for recipe in tqdm(recipes, desc=f"Processing {filename.name}"):
            try:
                ingredients = list(recipe["ingredients"][0]["items"].keys())
                cleaned = [extract_modifiers_and_ingredient(ing.strip().lower())[1] for ing in ingredients]
                categories = [item["category"] for item in recipe["ingredients"][0]["items"].values()]
                all_ingredient_lists.append({
                    "ingredients": ingredients,
                    "cleaned_ingredients": cleaned,
                    "categories": categories,
                    "cuisine": recipe.get("cuisine", "NA"),
                    "name": recipe.get("recipeItem", "Unnamed"),
                })
            except (KeyError, IndexError, AttributeError, TypeError):
                continue

    with open(cache_path, "w", encoding="utf-8") as f:
        f.write(str(all_ingredient_lists))
    return all_ingredient_lists


def build_embeddings(all_ingredient_lists, embedding_path: Path):
    unique_ingredients = sorted({ing for rec in all_ingredient_lists for ing in rec["cleaned_ingredients"] if ing})
    model = SentenceTransformer("thenlper/gte-large")
    embeddings = model.encode(unique_ingredients, show_progress_bar=True, convert_to_tensor=True)
    ingredient_to_emb = {ing: embeddings[i].cpu() for i, ing in enumerate(unique_ingredients)}
    torch.save(ingredient_to_emb, embedding_path)
    return ingredient_to_emb


def sample_negatives(all_ingredient_lists, ingredient_to_emb):
    category_to_ings = defaultdict(set)
    cuisine_to_recs = defaultdict(list)
    for rec in all_ingredient_lists:
        cuisine_to_recs[rec.get("cuisine", "NA")].append(rec)
        for ing, cat in zip(rec["cleaned_ingredients"], rec["categories"]):
            if ing and cat:
                category_to_ings[cat].add(ing)
    category_to_ings = {k: list(v) for k, v in category_to_ings.items()}

    recipe_to_data = defaultdict(lambda: {"positives": set(), "negatives": set()})

    for rec in tqdm(all_ingredient_lists, desc="Sampling negatives"):
        positives = {ing for ing in rec["cleaned_ingredients"] if ing}
        if not positives:
            continue

        recipe_to_data[rec["name"]]["positives"].update(positives)
        current_negs = set()

        used_cats = set(rec["categories"])
        easy_pool = [ing for cat, ings in category_to_ings.items() if cat not in used_cats for ing in ings]
        if easy_pool:
            current_negs.update(random.sample(easy_pool, min(random.randint(1, MAX_EASY_NEG), len(easy_pool))))

        this_cuisine = rec.get("cuisine", "NA")
        other_cuisines = [c for c in cuisine_to_recs if c != this_cuisine and c != "NA"]
        if other_cuisines:
            other_rec = random.choice(cuisine_to_recs[random.choice(other_cuisines)])
            cross_pool = [ing for ing in other_rec["cleaned_ingredients"] if ing]
            if cross_pool:
                current_negs.add(random.choice(cross_pool))

        recipe_embs = torch.stack([ingredient_to_emb[p] for p in positives if p in ingredient_to_emb])
        if recipe_embs.size(0) > 0:
            centroid = recipe_embs.mean(dim=0, keepdim=True)
            all_ings = list(ingredient_to_emb.keys())
            all_embs = torch.stack([ingredient_to_emb[ing] for ing in all_ings])
            sims = cosine_similarity(centroid, all_embs, dim=1)

            k_val = min(50, len(all_ings))
            if k_val > 0:
                top_indices = torch.topk(sims, k=k_val).indices.tolist()
                hard_pool = [all_ings[idx] for idx in top_indices if all_ings[idx] not in positives]
                if hard_pool:
                    current_negs.update(random.sample(hard_pool, min(MAX_HARD_NEG, len(hard_pool))))

        recipe_to_data[rec["name"]]["negatives"].update(current_negs)

    all_labeled = []
    for data in recipe_to_data.values():
        data["negatives"] -= data["positives"]
        pos = [(ing, 1) for ing in data["positives"]]
        neg = [(ing, 0) for ing in data["negatives"]]
        if pos and neg:
            all_labeled.append(pos + neg)

    random.shuffle(all_labeled)
    return all_labeled


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipe-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cache_path = output_dir / "training_data.txt"
    embedding_path = output_dir / "ingredient_embeddings.pt"
    dataset_path = output_dir / "training_data_with_negatives.json"

    all_ingredient_lists = load_recipe_cards(Path(args.recipe_dir), cache_path)
    ingredient_to_emb = build_embeddings(all_ingredient_lists, embedding_path)
    all_labeled = sample_negatives(all_ingredient_lists, ingredient_to_emb)

    with open(dataset_path, "w", encoding="utf-8") as f:
        json.dump(all_labeled, f, ensure_ascii=False)
    print(f"Wrote {len(all_labeled)} examples to {dataset_path}")


if __name__ == "__main__":
    main()
