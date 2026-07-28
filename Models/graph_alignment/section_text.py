import unicodedata

METADATA_KEYWORDS = [
    "servings", "serving", "makes", "cook", "prep", "preparation", "time",
    "m", "minutes", "mins", "author", "authour"
]

INGREDIENTS_KEYWORDS = [
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "1/4", "1/2", "1/3", "3/4",
    "tsp", "tbsp", "teaspoon", "tablespoon", "cup", "cups",
    "ml", "litre", "litres", "l",
    "g", "gm", "gms", "gram", "grams",
    "kg", "kgs", "kilogram", "kilograms",
    "oz", "ounce", "ounces",
    "lb", "pound", "pounds",
    "pinch", "dash", "taste", "handful", "garnish", "finely", "chopped",
    "water", "fresh"
]

CHUNK_SIZE = 8


def score_chunk(keywords, chunk):
    score = 0
    num_redundant = 0

    for word in chunk:
        cleaned_word = word.replace(".", "").lower().replace(":", "")
        if cleaned_word in keywords:
            score += 2
        else:
            num_redundant += 1
            score -= num_redundant / len(chunk)
    return score


def find_section(keywords, full_text, start, end, step, visited):
    chunk = full_text[start:end]
    score = score_chunk(keywords, chunk)
    state = (start, end)

    if state in visited:
        return chunk, score
    visited.add(state)

    if end > len(full_text) or start < 0:
        return full_text[start:end], score_chunk(keywords, full_text[start:end])

    chunk_forward, score_forward = find_section(keywords, full_text, start + step, end + step, step, visited)
    chunk_expanded_forward, score_expanded_forward = find_section(keywords, full_text, start - step, end + step, step, visited)
    chunk_backward, score_backward = find_section(keywords, full_text, start - step, end - step, step, visited)

    return max(
        (chunk, score),
        (chunk_expanded_forward, score_expanded_forward),
        (chunk_forward, score_forward),
        (chunk_backward, score_backward),
        key=lambda x: x[1]
    )


def find_seed_chunk(full_text, keywords, step):
    max_score = 0
    best_chunk = ""
    best_chunk_start = 0
    for i in range(0, len(full_text) - step, step):
        score = score_chunk(keywords, full_text[i:i + step])
        if score > max_score:
            max_score = score
            best_chunk = full_text[i:i + step]
            best_chunk_start = i
    return best_chunk, best_chunk_start


def refine_chunk(keywords, text, chunk, max_expand=CHUNK_SIZE):
    if not chunk:
        return chunk, None, None, 0

    start = None
    for i in range(len(text) - len(chunk) + 1):
        if text[i:i + len(chunk)] == chunk:
            start = i
            break
    if start is None:
        return chunk, None, None, score_chunk(keywords, chunk)

    end = start + len(chunk)
    best_start, best_end = start, end
    best_score = score_chunk(keywords, text[best_start:best_end])
    left_expanded, right_expanded = 0, 0

    improved = True
    while improved and (left_expanded < max_expand or right_expanded < max_expand):
        improved = False
        candidates = []

        if best_start > 0 and left_expanded < max_expand:
            cand_score = score_chunk(keywords, text[best_start - 1:best_end])
            candidates.append(('L', best_start - 1, best_end, cand_score))

        if best_end < len(text) and right_expanded < max_expand:
            cand_score = score_chunk(keywords, text[best_start:best_end + 1])
            candidates.append(('R', best_start, best_end + 1, cand_score))

        if candidates:
            best_candidate = max(candidates, key=lambda x: x[3])
            if best_candidate[3] > best_score:
                direction, bs, be, bscore = best_candidate
                best_start, best_end, best_score = bs, be, bscore
                if direction == 'L':
                    left_expanded += 1
                else:
                    right_expanded += 1
                improved = True
                continue

        if best_start > 0 and best_end < len(text) and left_expanded < max_expand and right_expanded < max_expand:
            cand_score = score_chunk(keywords, text[best_start - 1:best_end + 1])
            if cand_score > best_score:
                best_start -= 1
                best_end += 1
                best_score = cand_score
                left_expanded += 1
                right_expanded += 1
                improved = True
                continue

    shrink_improved = True
    while shrink_improved:
        shrink_improved = False
        removals = []
        if best_end - best_start > 1:
            removals.append(('L', best_start + 1, best_end, score_chunk(keywords, text[best_start + 1:best_end])))
            removals.append(('R', best_start, best_end - 1, score_chunk(keywords, text[best_start:best_end - 1])))

        if removals:
            best_removal = max(removals, key=lambda x: x[3])
            if best_removal[3] >= best_score:
                direction, bs, be, bscore = best_removal
                best_start, best_end, best_score = bs, be, bscore
                shrink_improved = True
                continue

    return text[best_start:best_end], best_start, best_end, best_score


def find_sublist_index(haystack, needle):
    needle_len = len(needle)
    for i in range(len(haystack) - needle_len + 1):
        if haystack[i:i + needle_len] == needle:
            return i
    return -1


def clean_text(text):
    cleaned_text = text.replace('▢', '')
    return unicodedata.normalize('NFKC', cleaned_text).replace("⁄", "/")


def get_sections(full_text):
    text = clean_text(full_text).replace("\n", "").split(" ")
    step_size = CHUNK_SIZE
    visited = set()

    metadata_seed, metadata_seed_start = find_seed_chunk(text, METADATA_KEYWORDS, step_size)
    metadata_chunk, _ = find_section(METADATA_KEYWORDS, text, metadata_seed_start, metadata_seed_start + step_size, step_size, visited)
    metadata_chunk_start = find_sublist_index(text, metadata_chunk)
    if metadata_chunk_start == -1:
        metadata_text = " ".join(metadata_chunk)
    else:
        start_index = max(0, metadata_chunk_start - 6)
        metadata_text = " ".join(text[start_index: metadata_chunk_start] + metadata_chunk)

    visited.clear()

    seed_ing, seed_start_ing = find_seed_chunk(text, INGREDIENTS_KEYWORDS, step_size)
    ing_chunk_raw, _ = find_section(INGREDIENTS_KEYWORDS, text, seed_start_ing, seed_start_ing + step_size, step_size, visited)
    refined_ing_chunk, refined_ing_start, refined_ing_end, _ = refine_chunk(INGREDIENTS_KEYWORDS, text, ing_chunk_raw, CHUNK_SIZE)

    if refined_ing_start is None:
        raw_start = find_sublist_index(text, ing_chunk_raw)
        if raw_start != -1:
            s_pad = max(0, raw_start - 10)
            e_pad = min(len(text), raw_start + len(ing_chunk_raw) + 10)
            ingredients_section = " ".join(text[s_pad:e_pad])
        else:
            ingredients_section = " ".join(ing_chunk_raw)
    else:
        s_pad = max(0, refined_ing_start - 10)
        e_pad = min(len(text), refined_ing_end + 10)
        ingredients_section = " ".join(text[s_pad:e_pad])

    prose_section = " ".join(text[0: metadata_seed_start + CHUNK_SIZE])

    return {
        "prose": prose_section,
        "metadata": metadata_text,
        "ingredients": ingredients_section
    }
