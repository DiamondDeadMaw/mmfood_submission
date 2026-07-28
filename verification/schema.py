FOUNDATIONAL_FIELDS = [
    "recipe_name", "recipe_category", "recipe_description",
    "ingredients", "serving_size", "total_time", "cook_time",
    "prep_time", "recipe_id", "recipe_url"
]

NON_ESSENTIAL_FIELDS = [
    "recipe_etymology", "place_of_origin", "cuisine", "suitable_for_course",
    "mealtime", "dietary_practice", "dish_subcategory", "recipe_difficulty",
    "ferment_time", "cooking_techniques", "cooking_vessels", "kitchen_tools",
    "knife_cuts", "flavor", "texture", "taste", "recipe_notes",
    "additional_trivia", "related_recipes", "additional_tips",
    "ingredient_substitution", "serving_pattern"
]

RECIPE_SCHEMA = {
    "type": "object",
    "properties": {
        "recipe_name": {"type": "string"},
        "recipe_etymology": {"type": "string"},
        "recipe_category": {"type": "string"},
        "recipe_description": {"type": "string"},
        "ingredient_substitution": {
            "type": "object",
            "additionalProperties": {
                "type": "array",
                "items": {"type": "string"}
            }
        },
        "serving_pattern": {"type": "string"},
        "place_of_origin": {"type": "string"},
        "cuisine": {"type": "string"},
        "suitable_for_course": {"type": "string"},
        "mealtime": {"type": "string"},
        "dietary_practice": {"type": "string"},
        "dish_subcategory": {"type": "string"},
        "ingredients": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "ingredient": {"type": "string"},
                                "description": {"type": "string"},
                                "form": {"type": "string"},
                                "size": {"type": "string"},
                                "quantity": {"anyOf": [{"type": "number"}, {"type": "string"}]},
                                "unit": {"type": "string"},
                                "estimated_weight_in_grams": {"anyOf": [{"type": "number"}, {"type": "string"}]}
                            },
                            "required": ["ingredient", "description", "form", "size", "quantity", "unit",
                                         "estimated_weight_in_grams"],
                            "additionalProperties": False
                        }
                    }
                },
                "required": ["heading", "items"],
                "additionalProperties": False
            }
        },
        "serving_size": {"type": "string"},
        "recipe_difficulty": {"type": "string"},
        "total_time": {"type": "string"},
        "cook_time": {"type": "string"},
        "prep_time": {"type": "string"},
        "ferment_time": {"type": "string"},
        "cooking_techniques": {"type": "array", "items": {"type": "string"}},
        "cooking_vessels": {"type": "array", "items": {"type": "string"}},
        "kitchen_tools": {"type": "array", "items": {"type": "string"}},
        "knife_cuts": {"type": "string"},
        "flavor": {"type": "string"},
        "texture": {"type": "string"},
        "taste": {"type": "string"},
        "recipe_notes": {"type": "string"},
        "additional_trivia": {"type": "string"},
        "related_recipes": {"type": "string"},
        "additional_tips": {"type": "string"},
        "recipe_id": {"type": "string"},
        "recipe_url": {"type": "string", "format": "uri"}
    },
    "required": FOUNDATIONAL_FIELDS,
    "additionalProperties": False
}
