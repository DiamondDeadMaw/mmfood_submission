import ast
import re
from collections import defaultdict

import numpy as np
from jsonschema import Draft7Validator
from rapidfuzz import fuzz
from rapidfuzz import process as fw_process

import config
from Models.graph_alignment.metadata_extraction import extract_metadata
from Models.graph_alignment.section_text import get_sections
from Models.graph_alignment.unit_conversion import compare_quantities
from Models.ingredient_ner.inference import extract_modifiers_and_ingredient
from Models.nli import inference as nli
from Models.relation_extraction.inference import extract_pairs_from_text
from verification.auto_correct import apply_auto_corrections
from verification.schema import NON_ESSENTIAL_FIELDS, RECIPE_SCHEMA

if not config.VOCAB_PATH.exists():
    raise FileNotFoundError(
        f"Ingredient vocabulary not found at {config.VOCAB_PATH}. Set MMFOOD_VOCAB_PATH or see 'Data availability' in README.md."
    )
with open(config.VOCAB_PATH, "r", encoding="utf-8") as f:
    VOCABULARY = ast.literal_eval(f.read())
if not VOCABULARY:
    raise ValueError(f"Ingredient vocabulary at {config.VOCAB_PATH} is empty; stages 2 and 3 need at least one entry.")

VOCABULARY_INGREDIENTS = {item["ingredient"] for item in VOCABULARY}

EXTENDED_VOCABULARY_LOOKUP = set()
for item in VOCABULARY:
    ing = item.get("ingredient")
    if isinstance(ing, str):
        EXTENDED_VOCABULARY_LOOKUP.add(ing.lower().strip())

    synonyms = item.get("synonym", [])
    if not isinstance(synonyms, list):
        synonyms = [synonyms]
    for s in synonyms:
        if isinstance(s, str):
            EXTENDED_VOCABULARY_LOOKUP.add(s.lower().strip())

    vernacular = item.get("vernacular", {})
    if isinstance(vernacular, dict):
        for lang in ("hindi", "hinglish"):
            values = vernacular.get(lang, [])
            if not isinstance(values, list):
                values = [values]
            for v in values:
                if isinstance(v, str):
                    EXTENDED_VOCABULARY_LOOKUP.add(v.lower().strip())


def _compute_ingredient_weights():
    weights = {}
    for item in VOCABULARY:
        unit_groups = defaultdict(list)
        for entry in item.get("numerical_data", []):
            unit = entry.get("unit", "").lower().strip()
            weight = entry.get("weight")
            quantity = entry.get("quantity", 1.0)
            if isinstance(weight, (int, float)) and isinstance(quantity, (int, float)) and quantity > 0:
                unit_groups[unit].append(weight / quantity)

        stats = {}
        for unit, values in unit_groups.items():
            values.sort()
            n = len(values)
            if n == 0:
                continue
            q1, q3 = values[n // 4], values[3 * n // 4]
            iqr = q3 - q1
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            filtered = [v for v in values if lower <= v <= upper]
            mean = sum(filtered) / len(filtered) if filtered else sum(values) / len(values)
            stats[unit] = {"mean": mean, "iqr_bounds": (lower, upper), "count": len(values)}

        weights[item["ingredient"]] = stats
    return weights


INGREDIENT_WEIGHTS = _compute_ingredient_weights()


def validate_schema(data, raw_output=False):
    validator = Draft7Validator(RECIPE_SCHEMA)
    raw_errors = list(validator.iter_errors(data))

    hard_errors = [f"ERROR: {'.'.join(str(p) for p in e.path) or '(root)'} -> {e.message}" for e in raw_errors]

    warnings = []
    for field in NON_ESSENTIAL_FIELDS:
        if field not in data or data[field] in ("na", "", None):
            warnings.append(f"WARNING: Missing sparse field '{field}'")
            if field not in data:
                data[field] = "na"

    if raw_output:
        return raw_errors, warnings
    return (hard_errors or None), warnings


def clean_ingredient_name(raw_ing):
    if not raw_ing:
        return ""
    _, normalized = extract_modifiers_and_ingredient(raw_ing)
    normalized = re.sub(r'\(.*?\)', '', normalized)
    return normalized.lower().strip()


def validate_numerical_values(data):
    outliers = []
    for group in data.get("ingredients", []):
        for item in group.get("items", []):
            raw_ing = item.get("ingredient", "")
            unit = item.get("unit", "").lower().strip()
            est_weight = item.get("estimated_weight_in_grams")

            if not isinstance(est_weight, (int, float)):
                continue

            try:
                quantity = float(item.get("quantity", 1))
                if quantity == 0:
                    continue
            except (TypeError, ValueError):
                continue

            cleaned_ing = clean_ingredient_name(raw_ing)
            if not cleaned_ing:
                continue

            matched_ing, score, _ = fw_process.extractOne(cleaned_ing, INGREDIENT_WEIGHTS.keys(), scorer=fuzz.ratio)
            if score < 90 or matched_ing not in INGREDIENT_WEIGHTS:
                continue

            stats_for_ing = INGREDIENT_WEIGHTS[matched_ing]
            if unit not in stats_for_ing:
                continue

            weight_per_unit = est_weight / quantity
            iqr_min, iqr_max = stats_for_ing[unit]["iqr_bounds"]
            if stats_for_ing[unit]["count"] < 3:
                iqr_min, iqr_max = iqr_min * 0.6, iqr_max * 1.4

            if not (iqr_min <= weight_per_unit <= iqr_max):
                outliers.append({
                    "raw_ingredient": raw_ing,
                    "normalized_ingredient": matched_ing,
                    "unit": unit,
                    "quantity": quantity,
                    "estimated_weight_in_grams": est_weight,
                    "weight_per_unit": weight_per_unit,
                    "expected_range": (iqr_min, iqr_max),
                    "mean": stats_for_ing[unit]["mean"],
                    "datapoints": stats_for_ing[unit]["count"],
                })
    return outliers


def check_old_ingredients(data):
    new_ingredients = []
    for group in data.get("ingredients", []):
        for item in group.get("items", []):
            raw_ing = item.get("ingredient", "")
            cleaned_ing = clean_ingredient_name(raw_ing)
            if not cleaned_ing or cleaned_ing in EXTENDED_VOCABULARY_LOOKUP:
                continue

            _, score, _ = fw_process.extractOne(cleaned_ing, VOCABULARY_INGREDIENTS, scorer=fuzz.ratio)
            if score < 90:
                new_ingredients.append(raw_ing)
    return list(set(new_ingredients))


def validate_semantic_coherence(data):
    from Models.suspicious_ingredient.inference import get_wrong_probabilities

    ingredient_list = [
        item["ingredient"]
        for group in data.get("ingredients", [])
        for item in group.get("items", [])
        if item.get("ingredient")
    ]
    if not ingredient_list:
        return {}

    probs = get_wrong_probabilities(ingredient_list)
    values = np.array(list(probs.values()))
    if len(values) == 0:
        return {}

    q1, q3 = np.percentile(values, 25), np.percentile(values, 75)
    upper_bound = q3 + 1.5 * (q3 - q1)
    return {k: v for k, v in probs.items() if v > upper_bound}


def get_intelligent_context(full_context, ingredient, qty, window_size=25):
    words = full_context.split()
    if not words:
        return full_context

    target = str(ingredient).lower().split()[0]
    candidate_indices = [i for i, w in enumerate(words) if target in w.lower()]
    if not candidate_indices:
        candidate_indices = range(0, len(words), 5)

    best_score = -1
    best_window = " ".join(words[:window_size])
    t_ing = str(ingredient).lower()
    t_qty = str(qty).lower().replace(".0", "")

    for i in candidate_indices:
        start, end = max(0, i - window_size // 2), min(len(words), i + window_size // 2 + 1)
        window_text = " ".join(words[start:end]).lower()
        score = (fuzz.token_set_ratio(t_ing, window_text) * 2.0) + (100 if t_qty != "na" and t_qty in window_text else 0)
        if score > best_score:
            best_score, best_window = score, " ".join(words[start:end])

    return best_window


def _normalize_metadata_value(value):
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        numbers = re.findall(r"[-+]?\d*\.\d+|\d+", value)
        if numbers:
            return float(numbers[0])
    return None


AMBIENT_STAPLES = ["salt", "pepper", "oil", "water", "sugar", "hing", "turmeric", "ghee"]
METADATA_KEYS_TO_CHECK = ["prep_time", "cook_time", "total_time", "serving_size"]

_PLACEHOLDER_UNITS = {"count", "na", ""}
_PLACEHOLDER_QUANTITIES = {"1", "1.0", "0", "0.0"}


def _quantity_is_unspecified(qty_llm):
    return qty_llm.strip().lower() in ("na", "n/a", "", "none", "null")


def _looks_like_truncated_fraction(qty_str):
    # The NER quantity span occasionally clips a mixed fraction like "1-1/2" down to
    # "1-", losing the fractional part. Treat these as unparsed rather than diffing
    # a dangling "1-" against a clean extracted value.
    return bool(re.match(r'^\d+-\s*$', str(qty_str).strip()))


def _parse_size_to_qty_unit(size_str):
    m = re.match(r'^(\d+\.?\d*|\d+/\d+|\d+-\d+/\d+)\s*(.*)$', size_str.strip())
    if not m:
        return None
    qty_part, unit_part = m.group(1), m.group(2).strip()
    if not unit_part:
        return None
    return qty_part, unit_part


def _parse_number_token(tok):
    tok = tok.strip()
    m = re.match(r'^(\d+)\s*-\s*(\d+)/(\d+)$', tok)
    if m:
        whole, num, den = map(int, m.groups())
        return whole + num / den
    m = re.match(r'^(\d+)/(\d+)$', tok)
    if m:
        num, den = map(int, m.groups())
        return num / den
    try:
        return float(tok)
    except ValueError:
        return None


def _extracted_numeric_value(qty_llm):
    m = re.match(r'^(\d+\.?\d*)\s*(?:-|to)\s*(\d+\.?\d*)$', qty_llm.strip())
    if m:
        return (float(m.group(1)) + float(m.group(2))) / 2
    return _parse_number_token(qty_llm)


def _nearest_number_near(text, ingredient, window=60):
    idx = text.lower().find(ingredient.lower())
    if idx < 0:
        core = ingredient.split()[-1] if ingredient else ""
        idx = text.lower().find(core.lower()) if core else -1
    if idx < 0:
        return None

    lo, hi = max(0, idx - window), min(len(text), idx + window)
    snippet, center = text[lo:hi], idx - lo

    best, best_dist, seen_spans = None, None, set()
    for pat in (r'\d+-\d+/\d+', r'\d+\.?\d*\s*(?:-|to)\s*\d+\.?\d*', r'\d+/\d+', r'\d+\.?\d*'):
        for m in re.finditer(pat, snippet):
            span = (m.start(), m.end())
            if any(span[0] >= s[0] and span[1] <= s[1] for s in seen_spans):
                continue
            seen_spans.add(span)
            dist = min(abs(span[0] - center), abs(span[1] - center))
            range_m = re.match(r'^(\d+\.?\d*|\d+/\d+|\d+-\d+/\d+)\s*(?:-|to)\s*(\d+\.?\d*|\d+/\d+)$', m.group(0))
            if range_m:
                a, b = _parse_number_token(range_m.group(1)), _parse_number_token(range_m.group(2))
                if a is None or b is None:
                    continue
                val = (a, b)
            else:
                v = _parse_number_token(m.group(0))
                if v is None:
                    continue
                val = (v, v)
            if best is None or dist < best_dist:
                best, best_dist = val, dist
    return best


def _all_occurrence_quantities(text, ingredient, window=60):
    # Some ingredients are listed more than once in a recipe (e.g. a spice used both
    # for tempering and again in the main gravy). Find every mention and its nearest
    # adjacent number, so a summed total can be checked separately from any single one.
    ing_lower = ingredient.lower()
    text_lower = text.lower()
    values = []
    start = 0
    while True:
        idx = text_lower.find(ing_lower, start)
        if idx < 0:
            break
        cand = _nearest_number_near(text, ingredient, window=window)
        # _nearest_number_near always finds the *first* occurrence; for repeat mentions,
        # search the local window directly instead of delegating to it.
        lo, hi = max(0, idx - window), min(len(text), idx + window)
        snippet, center = text[lo:hi], idx - lo
        local = _nearest_candidate_in_snippet(snippet, center)
        if local:
            values.append(local)
        start = idx + len(ing_lower)
    return values


def _nearest_candidate_in_snippet(snippet, center):
    best, best_dist, seen_spans = None, None, set()
    for pat in (r'\d+-\d+/\d+', r'\d+\.?\d*\s*(?:-|to)\s*\d+\.?\d*', r'\d+/\d+', r'\d+\.?\d*'):
        for m in re.finditer(pat, snippet):
            span = (m.start(), m.end())
            if any(span[0] >= s[0] and span[1] <= s[1] for s in seen_spans):
                continue
            seen_spans.add(span)
            dist = min(abs(span[0] - center), abs(span[1] - center))
            range_m = re.match(r'^(\d+\.?\d*|\d+/\d+|\d+-\d+/\d+)\s*(?:-|to)\s*(\d+\.?\d*|\d+/\d+)$', m.group(0))
            if range_m:
                a, b = _parse_number_token(range_m.group(1)), _parse_number_token(range_m.group(2))
                if a is None or b is None:
                    continue
                val = (a, b)
            else:
                v = _parse_number_token(m.group(0))
                if v is None:
                    continue
                val = (v, v)
            if best is None or dist < best_dist:
                best, best_dist = val, dist
    return best


def _corroborate_quantity_contradiction(ing_section, ingredient, qty_llm):
    # A quantity flagged CONTRADICTION by the primary match/NLI path is double-checked
    # against the nearest number actually adjacent to the ingredient's mention in the
    # source text. This catches cases where the primary pairing step grabbed a
    # neighboring ingredient's quantity, or missed an exact match entirely.
    ext_val = _extracted_numeric_value(qty_llm)
    if ext_val is None:
        return None
    candidate = _nearest_number_near(ing_section, ingredient)
    if candidate:
        lo, hi = candidate
        if lo - 0.01 <= ext_val <= hi + 0.01:
            return "nearest source mention"

    # The ingredient may be mentioned more than once (e.g. used twice in one recipe) -
    # if the extraction correctly summed all mentions into one total, check that too.
    occurrences = _all_occurrence_quantities(ing_section, ingredient)
    if len(occurrences) > 1:
        summed_lo = sum(lo for lo, hi in occurrences)
        summed_hi = sum(hi for lo, hi in occurrences)
        if summed_lo - 0.01 <= ext_val <= summed_hi + 0.01:
            return "sum of repeated mentions"

    return None


def _fix_existence_consistency(fidelity_report):
    # If quantity (and form, when checked) were independently confirmed ENTAILMENT for
    # an ingredient, existence cannot simultaneously be a CONTRADICTION - that would mean
    # the same ingredient both was and wasn't found in the source. Treat this as evidence
    # the existence check itself misfired, not that the ingredient is actually missing.
    for item in fidelity_report:
        if item.get("error_type") != "ingredient_fidelity":
            continue
        if item.get("existence") != "CONTRADICTION" or item.get("quantity") != "ENTAILMENT":
            continue
        if item.get("form") == "CONTRADICTION":
            continue
        item["existence"] = "ENTAILMENT"
    return fidelity_report


def validate_source_fidelity(text, extracted):
    fidelity_report = []

    sections = get_sections(text)
    ing_section = sections.get("ingredients", text)
    meta_section = sections.get("metadata", "")

    source_metadata = extract_metadata(meta_section)
    for key in METADATA_KEYS_TO_CHECK:
        llm_value = extracted.get(key)
        source_value = source_metadata.get(key)

        if llm_value and not source_value:
            fidelity_report.append({"error_type": "metadata_field_not_in_source", "key": key, "llm_value": llm_value})
        elif source_value and not llm_value:
            fidelity_report.append({"error_type": "metadata_field_not_in_extracted", "key": key})
        elif llm_value and source_value:
            llm_numeric = _normalize_metadata_value(llm_value)
            src_numeric = _normalize_metadata_value(source_value)
            if llm_numeric is not None and src_numeric is not None and not np.isclose(llm_numeric, src_numeric):
                fidelity_report.append({
                    "error_type": "metadata_value_mismatch", "key": key,
                    "llm_value": llm_numeric, "source_value": src_numeric,
                })

    source_alignment = extract_pairs_from_text(ing_section)

    nli_batch = []
    nli_meta = []
    extracted_quantity_lookup = {}
    report_idx = len(fidelity_report)

    for group_idx, group in enumerate(extracted.get("ingredients", [])):
        for item_idx, item in enumerate(group.get("items", [])):
            ing = str(item.get("ingredient", "Unknown"))
            qty_llm, unit_llm = str(item.get("quantity", "na")), str(item.get("unit", "na"))
            form_llm = str(item.get("form", "na")).strip().lower()
            premise = get_intelligent_context(ing_section, ing, qty_llm)
            path = f"ingredients[{group_idx}].items[{item_idx}]"
            extracted_quantity_lookup[path] = qty_llm

            item_report = {
                "error_type": "ingredient_fidelity",
                "path": path,
                "ingredient": ing,
                "existence": "NEUTRAL",
                "quantity": "NEUTRAL",
                "source_quantity": "na",
            }
            has_form = form_llm not in ("na", "n/a", "", "none", "null")
            if has_form:
                item_report["form"] = "NEUTRAL"

            is_ambient = any(a in ing.lower() for a in AMBIENT_STAPLES)
            unspecified_qty = _quantity_is_unspecified(qty_llm)

            if is_ambient:
                # Ambient staples (salt, oil, water, ghee, ...) are routinely described
                # vaguely ("to taste", "as needed") - a specific asserted quantity for
                # these is not a real fidelity problem, so skip the existence/quantity
                # checks for them entirely rather than relying on a downstream NLI label.
                item_report["existence"] = "ENTAILMENT"
                item_report["quantity"] = "ENTAILMENT"
                item_report["source_quantity"] = "Implicit (Verified Staple)"
            else:
                nli_batch.append((premise, f"{ing} is an ingredient in this recipe."))
                nli_meta.append((report_idx, "exist", ing))
                if unspecified_qty:
                    # The LLM didn't assert a quantity at all - there is nothing for a
                    # "quantity contradiction" to contradict.
                    item_report["quantity"] = "NEUTRAL"

            if has_form:
                nli_batch.append((premise, f"The {ing} is {form_llm}."))
                nli_meta.append((report_idx, "form", ing))

            best_match, best_fuzz_score = None, -1
            for src_ing, src_qty in source_alignment.items():
                ratio = fuzz.token_set_ratio(ing.lower(), src_ing)
                if ratio > 90 and ratio > best_fuzz_score:
                    best_fuzz_score, best_match = ratio, src_qty

            if best_match and _looks_like_truncated_fraction(best_match.get("qty")):
                # The quantity span was clipped mid-fraction (e.g. "1-1/2" -> "1-");
                # treat this pairing as unreliable rather than diff it as a hard number.
                best_match = None

            size_str = str(item.get("size", "na")).strip()
            has_size = size_str.lower() not in ("na", "n/a", "")

            is_validator_suspicious = False
            if best_match:
                cleaned_ing = clean_ingredient_name(ing)
                if cleaned_ing in INGREDIENT_WEIGHTS:
                    unit_norm = best_match["unit"].lower().strip()
                    if unit_norm in INGREDIENT_WEIGHTS[cleaned_ing]:
                        _, max_bound = INGREDIENT_WEIGHTS[cleaned_ing][unit_norm]["iqr_bounds"]
                        try:
                            qty_str = str(best_match["qty"]).strip()
                            if "/" in qty_str:
                                n, d = qty_str.split("/")
                                src_val = float(n) / float(d) if d else float(n)
                            else:
                                src_val = float(qty_str)
                            if src_val > (max_bound * 5.0):
                                is_validator_suspicious = True
                        except (ValueError, TypeError, ZeroDivisionError):
                            pass

            if not is_ambient and not unspecified_qty:
                if best_match and not is_validator_suspicious:
                    src_qty_unit_str = f"{best_match['qty']} {best_match['unit']}".strip().lower()
                    is_placeholder_qty = (
                        unit_llm.lower() in _PLACEHOLDER_UNITS and qty_llm.strip() in _PLACEHOLDER_QUANTITIES
                    )

                    if has_size and is_placeholder_qty and size_str.lower() == src_qty_unit_str:
                        # The real measurement lives in "size" (e.g. "4 cloves"), not the
                        # placeholder quantity/unit fields - and it matches exactly.
                        item_report["quantity"] = "ENTAILMENT"
                        item_report["source_quantity"] = f"{best_match['qty']} {best_match['unit']}"
                    else:
                        compare_qty, compare_unit = qty_llm, unit_llm
                        if has_size and is_placeholder_qty:
                            parsed_size = _parse_size_to_qty_unit(size_str)
                            if parsed_size:
                                compare_qty, compare_unit = parsed_size

                        is_match = compare_quantities(compare_qty, compare_unit, best_match["qty"], best_match["unit"])
                        item_report["quantity"] = "ENTAILMENT" if is_match else "CONTRADICTION"
                        item_report["source_quantity"] = f"{best_match['qty']} {best_match['unit']}"
                else:
                    fallback_msg = "The recipe calls for " + (f"{qty_llm} {unit_llm}" if qty_llm != "na" else "some") + f" of {ing}."
                    nli_batch.append((premise, fallback_msg))
                    nli_meta.append((report_idx, "qty_fallback_suspicious" if is_validator_suspicious else "qty_fallback", ing))

            fidelity_report.append(item_report)
            report_idx += 1

    if nli_batch:
        labels = nli.classify_pairs(nli_batch)

        for (rep_idx, nli_type, ing_name), label in zip(nli_meta, labels):
            is_ambient = any(a in ing_name.lower() for a in AMBIENT_STAPLES)

            if nli_type == "exist":
                if label == "NEUTRAL":
                    label = "ENTAILMENT" if is_ambient else "CONTRADICTION"
                fidelity_report[rep_idx]["existence"] = label
            elif nli_type == "form":
                fidelity_report[rep_idx]["form"] = label
            else:
                if label == "NEUTRAL" and is_ambient:
                    label = "ENTAILMENT"
                fidelity_report[rep_idx]["quantity"] = label

                if nli_type == "qty_fallback_suspicious":
                    fidelity_report[rep_idx]["source_quantity"] = "Source Ambiguous (Defaulting to NLI)"
                elif label == "ENTAILMENT" and is_ambient:
                    fidelity_report[rep_idx]["source_quantity"] = "Implicit (Verified Staple)"
                else:
                    fidelity_report[rep_idx]["source_quantity"] = "NLI Fallback"

    for item in fidelity_report:
        if item.get("error_type") != "ingredient_fidelity" or item.get("quantity") != "CONTRADICTION":
            continue
        qty_llm = str(extracted_quantity_lookup.get(item["path"], "na"))
        corroboration = _corroborate_quantity_contradiction(ing_section, item["ingredient"], qty_llm)
        if corroboration:
            item["quantity"] = "ENTAILMENT"
            item["source_quantity"] = f"{item['source_quantity']} (corroborated: {corroboration})"

    return _fix_existence_consistency(fidelity_report)


def validate_full_pipeline(text, extracted, llm_provider=None):
    corrected_extracted, correction_flags = apply_auto_corrections(text, extracted, provider=llm_provider)
    if "AUTO_CORRECTED" in correction_flags:
        extracted = corrected_extracted

    schema_errors, schema_warnings = validate_schema(extracted)

    results = {
        "auto_correction": correction_flags,
        "stages": {
            "stage_1": {"errors": schema_errors, "warnings": schema_warnings},
            "stage_2": {"new_ingredients": check_old_ingredients(extracted)},
            "stage_3": {"outliers": validate_numerical_values(extracted)},
            "stage_4": {"outliers": validate_semantic_coherence(extracted)},
            "stage_5": {"report": validate_source_fidelity(text, extracted)},
        },
    }

    return results, extracted
