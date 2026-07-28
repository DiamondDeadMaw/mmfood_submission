import json
import re

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

import config
from verification.llm_providers import LLMProvider, get_llm_provider

_context_embedder = None


def _get_embedder() -> SentenceTransformer:
    global _context_embedder
    if _context_embedder is None:
        _context_embedder = SentenceTransformer("thenlper/gte-large")
    return _context_embedder


def _build_prompt(source_text: str, current_json: dict, candidate_fixes: list[dict]) -> str:
    return f"""
    You are a Culinary Data Alignment Expert.
    A recipe extraction pipeline found errors in this recipe:
    {json.dumps(current_json, indent=2)}

    Source Text Context: "{source_text[:500]}..."

    I found several similar historical human corrections for this error pattern:
    {json.dumps([{"text": f['source_text_snippet'], "patch": f['patch']} for f in candidate_fixes], indent=2)}

    TASK:
    1. Determine if any of these historical patches logically apply to the CURRENT recipe based on the source text.
    2. If yes, generate the CORRECTED JSON for the whole recipe.
    3. If no, or if you are unsure, return exactly "NO_APPLICABLE_CORRECTION".

    Return ONLY the corrected JSON block or the string "NO_APPLICABLE_CORRECTION".
    """


def apply_auto_corrections(
    source_text: str,
    current_json: dict,
    provider: LLMProvider | None = None,
    similarity_threshold: float = 0.85,
):
    if not config.AUTO_CORRECT_ENABLED or not config.CORRECTIONS_DB_PATH.exists():
        return current_json, []

    fixes = []
    with open(config.CORRECTIONS_DB_PATH, "r", encoding="utf-8") as f:
        for line in f:
            fixes.append(json.loads(line))

    if not fixes:
        return current_json, []

    current_emb = _get_embedder().encode(source_text).reshape(1, -1)
    fix_embs = np.array([f["context_embedding"] for f in fixes])
    similarities = cosine_similarity(current_emb, fix_embs)[0]

    top_indices = np.where(similarities > similarity_threshold)[0]
    if len(top_indices) == 0:
        return current_json, []

    candidate_fixes = [fixes[i] for i in top_indices]
    provider = provider or get_llm_provider()

    try:
        response_text = provider.complete(_build_prompt(source_text, current_json, candidate_fixes))

        if "NO_APPLICABLE_CORRECTION" in response_text:
            return current_json, []

        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group()), ["AUTO_CORRECTED"]
    except Exception:
        pass

    return current_json, []
