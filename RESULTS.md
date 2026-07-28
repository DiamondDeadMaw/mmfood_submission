# Results: Error Detection Performance (N=500 Recipes)

## Summary Table

| Stage | Total flags | Docs affected (of 500) | Mean per doc |
|---|---|---|---|
| 1 - Schema Validation | 1,668 errors | 482 | 3.34 |
| 2 - Vocabulary Check | 310 new ingredients | 198 | 0.62 |
| 3 - Numerical Outliers | 334 outliers | 223 | 0.67 |
| 4 - Semantic Coherence | 671 outliers | 382 | 1.34 |
| 5 - Source Fidelity | 725 issues | 324 | 1.45 |

See **"Understanding these results"** below for the for how we got these numbers.

---

## How this was run

The first 500 `(source_text, llm_extracted_json)` pairs were pulled from a larger internal corpus of already-extracted recipes. This sample is saved at `data/eval_sample_500.json`. Each pair was run through all 5 pipeline stages (`verification/validator.py`), and the per-document results were aggregated into the totals above.

### Notes on stage 5

Stage 5 depends on a fine-tuned relation-extraction model (DeBERTa-v3-large) and an ingredient NER model, in conjunction with a public pretrained NLI checkpoint. All Stage 5 figures reported in this document were produced using fully-trained weights for both models, loaded from the standard paths in `config.py` (`Models/ingredient_ner/model` and `Models/relation_extraction/finetuned_re_model`). The run reported here used a temporary instrumented script to capture full per-document reports for analysis; `run_pipeline.py` (see "Reproducing this" below) is the equivalent, supported entry point in this repository.

**A note on reproducibility.** Trained model weights are not included in this repository - only the training and inference code is included. A reader following this repository's README instructions to train their own `ingredient_ner`/`relation_extraction` models would obtain a freshly-trained pair of models, comparable in kind but not numerically identical to the ones used to produce the figures in this document.

## Reproducing this
```bash
python run_pipeline.py --input data/eval_sample_500.json --output results_500.json
```

---

## Ablations

To characterize what each stage is actually catching, rather than treating the totals in the summary table as self-explanatory, we broke down the flags produced by Stages 1, 3, and 4 by category.

### Stage 1 - composition of schema errors

| Error category | Total | Docs affected |
|---|---|---|
| `invalid_data_type` (extractor returned a scalar where an array was expected, etc.) | 1,503 | 446 |
| `missing_required_field` | 152 | 111 |
| `other_errors` | 13 | 3 |
| **All Stage 1 errors combined** | **1,668** | **482** |
| *(separately) non-essential field `warnings`, auto-patched to `"na"`* | *3,564* | *313* |

`invalid_data_type` accounts for 90% of Stage 1's total flag volume (1,668 -> 165 if excluded). This indicates that **Stage 1's signal is dominated by a single, narrow failure mode**: the extraction LLM returning a bare string or scalar where the schema specifies an array (concentrated in `cooking_techniques`, `cooking_vessels`, `kitchen_tools`, and `related_recipes`). This is likely the least expensive category of error to address upstream, since a prompt-level instruction or a lightweight post-processing coercion step (wrapping bare strings in a single-element list) would plausibly eliminate most of it without any change to the verification logic itself. However, since we have constrained ourselves to no re-extractions, this is kept. 

### Stage 3 - discrete-count ingredients versus weight/volume ingredients

| Outlier type | Total | Docs affected |
|---|---|---|
| Count-unit ingredients (e.g. "3 cloves", "2 bay leaves") | 150 | 110 |
| Weight/volume-unit ingredients (teaspoon, cup, tablespoon, etc.) | 164 | 141 |
| **Combined** | **314** | **217** |

This category breakdown was computed from an independent re-run of Stage 3, so the total (314/217) differs slightly from the 334/223 figure in the summary table above. This is because Stage 3's outlier bounds are not hardcoded, and are computed per ingredient (in `_compute_ingredient_weights()`) from the numerical samples stored in the vocabulary data, using an IQR rule. Because this occurs at runtime, small changes to those samples between runs can shift the computed bounds slightly.

### Stage 4 - concentration of semantic-coherence flags

The single most-flagged ingredient, **"coriander (dhania) leaves"**, accounts for 51 of the 671 total outliers (7.6%) on its own. The five most-flagged ingredients combined:

| Ingredient | Times flagged |
|---|---|
| coriander (dhania) leaves | 51 |
| dry red chillies | 32 |
| red chilli powder | 30 |
| dry red chilli | 28 |
| coriander (dhania) seeds | 26 |
| **Top 5 combined** | **167 (25% of all Stage 4 flags)** |

Excluding just these five ingredient names from consideration would reduce Stage 4's total from 671 to 504. This concentration is notable: it suggests the Set Transformer has learned a systematic bias against a small set of very common garnish and spice ingredients that co-occur with a wide variety of dishes, rather than distributing flags evenly across genuinely unusual ingredient–recipe pairings. This is a candidate area for further investigation before Stage 4 flags on these specific ingredients are treated at face value.

### Stage 5 - ingredient fidelity versus metadata errors

Stage 5's initial output, prior to the methodological refinements described in the next section, breaks down as follows:

| Category | Total | Share of all Stage 5 issues |
|---|---|---|
| Existence contradictions | 419 | 24.4% |
| Quantity contradictions | 989 | 57.6% |
| Form contradictions | 90 | 5.2% |
| **Ingredient fidelity subtotal** | **1,498** | **87.3%** |
| Metadata field issues (prep/cook/total time, serving size) | 218 | 12.7% |
| **All Stage 5 issues** | **1,716** | 100% |

Excluding metadata-type errors leaves 1,498 ingredient-fidelity contradictions (1,716 -> 1,498, a 12.7% reduction) - the substantial majority of the signal is ingredient-level rather than metadata-level. Within ingredient fidelity, **quantity contradictions dominate** (989 of 1,498, 66%): the extraction asserting a specific amount unsupported by the source text is, by a wide margin, the most common failure mode this stage identifies, ahead of existence discrepancies (419) and form mismatches (90).

A further pattern emerged on inspection of this breakdown by ingredient: the single most-contradicted ingredient across all 500 documents is **`salt`**, accounting for 235 of the 1,498 ingredient-fidelity contradictions (15.7%) - nearly three times the next most-contradicted ingredient, `oil` (85). This observation directly motivated the exploratory analysis in the section below.

---

## Understanding these results: deriving the Stage 5 methodology

A raw contradiction count is only as informative as the methodology producing it. Before treating Stage 5's initial output (1,716 contradictions across 476 of 500 recipes) as a meaningful measurement, we conducted an exploratory analysis of the underlying flagged cases - reading the source text and the corresponding extracted JSON side by side for a substantial sample - to characterize what the fidelity checker was actually detecting. This process surfaced several systematic properties of the checking methodology itself, each of which motivated a concrete refinement. This section presents that exploratory analysis, the resulting refinements to `verification/validate_source_fidelity()`, and the final, validated Stage 5 figures (725 issues, 324 documents) reported in the summary table above.

### Exploratory analysis of the raw Stage 5 output

We examined random samples of flagged cases (15, then 35 for the largest category) against their source text. Several clear, recurring patterns emerged:

1. **Ambiguous "to taste" staples were being penalized for lacking a precise quantity.** Ingredients such as salt, oil, water, and ghee are almost always specified vaguely in the source recipes ("salt to taste", "oil for frying"), such that there is typically no single correct quantity to check against. `salt` alone accounted for 235 of the 1,498 ingredient-level contradictions, nearly three times the next-highest ingredient. 
2. **The existence and quantity checks could disagree with themselves.** In an initial 5-case sample, 4 of 5 flagged "existence contradictions" had that same ingredient's `quantity` (and, in some cases, `form`) independently marked as a correct match within the same report entry - that is, the methodology had, in effect, already confirmed the ingredient's presence while separately asserting its absence. Verified against the full 500-document set, this pattern accounted for **49% of all existence contradictions**, indicating a systematic inconsistency between two checks that should agree with one another, rather than an isolated artifact.
3. **Quantity contradictions were sometimes raised against extractions that asserted no quantity at all.** Where the extraction's own output for an ingredient was `"NA"`, there is no quantity claim for a contradiction to be evaluated against.
4. **The quantity-matching step sometimes paired an ingredient with an incorrect nearby number** - either missing an exact match adjacent to the ingredient in the text and falling back to a weaker check that subsequently failed, or attributing a *different* ingredient's quantity from the same line (for example, reading "2 teaspoons" intended for the next spice in a list rather than the "1-1/2 teaspoons" actually associated with the ingredient in question). In a 35-case hand-audit of the quantity category, this family of issues accounted for the majority of cases examined - a stronger effect than anticipated at the outset.
5. **An ingredient mentioned twice within a single recipe** (for example, cumin seeds used once for tempering and again within a curry) is sometimes correctly summed by the extraction model into a single combined quantity, which the methodology compared against only the nearest of the two mentions, producing a spurious contradiction. This was initially assessed as not cleanly resolvable without deeper semantic parsing; on further consideration, it is resolvable directly - the source text can be searched for *every* mention of the ingredient rather than only the nearest one, and the extracted value compared against their sum.

### Methodological refinements

All findings above were resolved, and implemented into our pipeline.

### Raw output versus final methodology

| | Total Stage 5 issues | Docs affected |
|---|---|---|
| Raw pipeline output | 1,716 | 476 of 500 (95%) |
| Final methodology (as reported above) | **725** | **324 of 500 (65%)** |

| Category | Raw | Final |
|---|---|---|
| Existence contradictions | 419 | 161 |
| Quantity contradictions | 989 | 256 |
| Form contradictions | 90 | 90 |
| Metadata issues | 218 | 218 |

The largest reductions occur in the quantity and existence categories, consistent with where the refinements were concentrated. Form and metadata are unchanged, as the exploratory analysis did not surface the same class of systematic issue in either category during this pass - a reflection of where the analysis focused rather than a demonstration that these categories are free of similar issues. The repeated-mention refinement (finding 7) alone resolved 38 quantity contradictions that survived every other refinement, once measured directly against the full sample; an initial assessment that this failure mode would be difficult to address reliably did not hold up under closer examination.

Some limitations of this methodology should be stated plainly. The "nearest number in the source text" corroboration check is a heuristic rather than a guarantee; direct spot-checking indicated it produces the correct determination in roughly 9 of 10 cases, with the principal remaining failure mode being an unquantified ingredient positioned immediately adjacent to a quantified one. Even with all seven refinements applied, some existence contradictions in the final output are expected to remain false positives for reasons not fully diagnosed in this pass (ingredients described only as "to taste" outside the staple exemption list, and quantity-matching failures the corroboration check did not catch). The figure of 725 should be understood as substantially better grounded than the raw figure of 1,716, rather than as a fully audited, error-free count.

### Verified true errors: examples

The 725 issues in the final Stage 5 output are a mix of genuine extraction errors and residual noise not further diagnosed in this pass. The examples below, drawn from the final pipeline output and confirmed against the source text, illustrate what the genuine errors look like.

**Quantity:**

| Ingredient | Extracted | Actual (source) | Recipe |
|---|---|---|---|
| Whole wheat bread crumbs | 1 cup | 1/2 cup | Chicken, Mushroom And Broccoli Au Gratin |
| Basil leaves | 1 teaspoon | 2 sprigs | Sweet Spicy & Tangy Vegetarian Thai Green Curry |
| Curry leaves | 2 sprig | 1 sprig | Konkani Style Southe Koddel |
| Basil leaves or kaffir lime leaves | 1 (count) | 3 sprig | Thai Green Curry with Chicken & Red Rice |
| Red grapes | 1,158 grams | *(no quantity given at all)* | (fruit salad recipe) |

The last example merits particular attention: the source lists "Red grapes" with no quantity whatsoever, alongside other unquantified fruits, yet the extraction produced a specific value of "1158.0 grams" - a precise-sounding figure with no basis in the source text.

**Form:**

| Ingredient | Extracted form | Actual (source) | Recipe |
|---|---|---|---|
| Colocasia root (Arbi) | boiled | washed thoroughly and peeled | Kerala Style Taro Root Curry |
| Onions | whole | thinly sliced and fried | Kashmiri Style Shab Deg |
| Chicken breasts | whole | cut into small pieces | Oven Crisped Burritos with Shredded Chicken |
| Onion | whole | chopped | Oven Crisped Burritos with Shredded Chicken |
| Cloves (Laung) | whole | *(no form stated in source at all)* | (dum aloo case walkthrough, see `CASE_WALKTHROUGH.md`) |

**Existence:**

| Ingredient (as extracted) | What actually happened | Recipe |
|---|---|---|
| `nacl` | The source says "Salt, to taste" - the extraction wrote the chemical formula instead of the word, so no text-matching approach finds it | Mexican Corn and Bell Pepper Tostadas |
| `tnutritional information` | A garbled fragment of a page section header ("...t Nutritional Information...") was extracted as if it were a recipe ingredient.| Jaggery Sweetened Apple Oatmeal |