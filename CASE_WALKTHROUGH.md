# Case Walkthrough: Inconsistency Detection and Resolution on a Sample Recipe

This walks through the full validation framework — both the **Inconsistency Detection** stages (the 5-stage pipeline in `verification/`) and the **Inconsistency Resolution** loop (auto-correction) — on a single real example.

For this purpose, a random source document (a raw long-form recipe blog text describing *dum aloo*) was picked, and the corresponding LLM-extracted JSON was manually annotated to identify expected failure modes.

## Injected errors

**Incorrect data (factual drift & morphological contradictions):**

1. Baby potatoes: quantity reported as 12.5; actual is 13.5.
2. Baby potatoes: form reported as "whole"; actual is "boiled, peeled, and pricked".
3. Oil: quantity reported as 5; actual is 2.5.
4. Coriander seeds: form reported as "na" (lowercased, cleaned abbreviation for "Not Available"); actual is "crushed".
5. Onion: quantity reported as 3; actual is 1.

**Hallucination (existential):**

6. Serving size reported as 6, but not present in the source.

Two inconsistent ingredients were also manually added to the extracted JSON to demonstrate the semantic coherence stage.

## Phase 1: Inconsistency detection

- **Stage 1 (Schema Validation):** The structure of the extracted JSON is validated against the expected schema. Several required fields were missing from the initial output — `place_of_origin`, `ferment_time`, `knife_cuts`, `flavor`, `texture`, `taste`, and `related_recipes` — and were automatically flagged.

- **Stage 2 (Vocabulary Check):** A controlled vocabulary check ensures all ingredients conform to a predefined list. The manually inserted ingredient *dum aloo* (added for demonstration, representing the dish itself rather than an ingredient) was flagged by this stage — illustrating a failure mode where the LLM incorrectly classifies a recipe name as an ingredient.

- **Stage 3 (Statistical Feasibility):** Statistical analysis identifies ingredient weights that significantly deviate from typical usage patterns. Ginger garlic paste, coriander powder, and cumin powder were flagged as numerical outliers, signaling potential quantity extraction errors.

- **Stage 4 (Semantic Coherence):** The Set Transformer assesses how well each ingredient aligns with the overall context of the recipe. The two manually added ingredients, *dum aloo* and *bread*, were identified as semantic outliers with discard probabilities of 34% and 0.54% respectively. The remaining valid ingredients maintained typical probabilities near 0.1%.

- **Stage 5 (Source Fidelity Verification):** The dual-judge (NLI + relation extraction/graph alignment) system evaluates alignment between the structured output and the source text.
  - It flagged **Error 2** ("whole" vs "boiled, peeled, and pricked") as a *morphological contradiction*.
  - It flagged **Error 6** (serving size: 6) as an *existential hallucination*, since no numerical serving size was anchored in the source.
  - It correctly mapped the extracted ingredient components against the textual bounds, successfully identifying factual drift in the quantitative values (Errors 1, 3, and 5).

## Phase 2: Inconsistency resolution

Once detection flags the inconsistencies, the resolution loop (`verification/auto_correct.py`) processes the flagged nodes in tiers:

- **Stage 1 (Rule-Based Auto-Correction):** Addresses the missing sparse fields flagged in Detection Stage 1 via schema-driven repair — patching missing non-essential fields (e.g. `knife_cuts`, `ferment_time`) with the canonical `"na"` value, ensuring database interoperability without invoking an LLM.

- **Stage 3 (Patch-Based Correction via Retrieval):** To resolve the morphological contradiction in **Error 2** (baby potatoes marked as "whole"), the system embeds the contextual error using a weighted two-tower strategy and performs a K-nearest-neighbor search across a seed database of 42 human corrections.

  It retrieves a highly similar historical patch (cosine similarity ≥ 0.88): *"If the source text dictates specific physical preparation states for an entity, extract them as modifiers to the form/size attribute and replace the LLM's default assumed state."*

  A lightweight secondary model (whichever provider is configured via `LLM_PROVIDER`) applies this retrieved logic to the local extraction, replacing `"whole"` with `"boiled, peeled, and pricked"` without manual intervention.

- **Stage 4 (Source Grounding and Rollback):** To resolve the existential hallucination in **Error 6** (serving size: 6), the system attempts a targeted retrieval pass to locate the span "6" in the source text adjacent to serving-related vocabulary. Upon failing to find a supporting anchor, it executes a deterministic *rollback*, removing the hallucinated `serving_size` key-value pair entirely.

## Outcome

Through this closed-loop architecture, the system safely and autonomously resolves structural omissions, semantic contradictions, and existential hallucinations. Complex numerical range errors (Errors 1 and 3) that fail to meet the strict ≥ 0.88 similarity threshold for autonomous patching are escalated to the Human-in-the-Loop interface (`CorrectionTool/`) for review, ensuring the knowledge graph's integrity remains uncompromised.
