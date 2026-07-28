import re
from typing import Any, Dict

METADATA_PATTERNS = {
    'prep_time': re.compile(r'(?:Prep(?:aration)?(?: in| Time)?)\s*[:\-]?\s*(\d+)\s*(M|min(?:ute)?s?)', re.IGNORECASE),
    'cook_time': re.compile(r'(?:Cook(?:s in| Time)?)\s*[:\-]?\s*(\d+)\s*(M|min(?:ute)?s?)', re.IGNORECASE),
    'total_time': re.compile(r'(?:Total(?: in| Time)?)\s*[:\-]?\s*(\d+)\s*(M|min(?:ute)?s?)', re.IGNORECASE),
    'serving_size': re.compile(r'(?:Servings|Makes|Yield|Serves)\s*[:\-]?\s*(\d+)', re.IGNORECASE),
    'author': re.compile(r'(?:Author|By)\s*[:\-]?\s*([a-zA-Z\s,.]+)', re.IGNORECASE),
    'cuisine': re.compile(r'Cuisine\s*[:\-]?\s*(\w+)', re.IGNORECASE),
    'course': re.compile(r'Course\s*[:\-]?\s*(\w+)', re.IGNORECASE),
    'diet': re.compile(r'Diet\s*[:\-]?\s*(\w+)', re.IGNORECASE),
}

DEFAULT_METADATA_KEYWORDS = ['Prep', 'Cook', 'Total', 'Makes', 'Servings', 'Author', 'By']


def extract_recipe_name(text: str, metadata_keywords=None) -> str:
    if metadata_keywords is None:
        metadata_keywords = DEFAULT_METADATA_KEYWORDS

    words = text.strip().split()
    recipe_name_words = []

    for word in words:
        if any(kw.lower() in word.lower() for kw in metadata_keywords):
            break
        recipe_name_words.append(word)

    recipe_name = " ".join(recipe_name_words).replace("In association with", "").strip()
    return recipe_name or "Unknown Recipe"


def extract_metadata(text: str) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {'recipe_name': extract_recipe_name(text)}

    for key, pattern in METADATA_PATTERNS.items():
        match = pattern.search(text)
        if not match:
            continue

        value = match.group(1).strip()
        if key in ('prep_time', 'cook_time', 'total_time'):
            metadata[key] = float(value)
            metadata[f"{key}_unit"] = 'minutes' if match.group(2).lower().startswith('m') else 'hours'
        elif key == 'serving_size':
            metadata[key] = float(value)
            metadata[f"{key}_unit"] = 'serving_size'
        else:
            metadata[key] = value.strip(',').strip()

    return metadata
