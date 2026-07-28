UNIT_MAP = {
    "ml": 1.0, "milliliter": 1.0, "milliliters": 1.0,
    "l": 1000.0, "liter": 1000.0, "liters": 1000.0,
    "tsp": 4.92, "teaspoon": 4.92, "teaspoons": 4.92,
    "tbsp": 14.78, "tablespoon": 14.78, "tablespoons": 14.78,
    "cup": 236.58, "cups": 236.58,
    "oz": 29.57, "ounce": 29.57, "ounces": 29.57,
    "g": 1.0, "gram": 1.0, "grams": 1.0,
    "kg": 1000.0, "kilogram": 1000.0, "kilograms": 1000.0,
    "lb": 453.59, "pound": 453.59, "pounds": 453.59,
    "mg": 0.001,
    "clove": 1.0, "cloves": 1.0,
    "stalk": 1.0, "stalks": 1.0,
    "sprig": 1.0, "sprigs": 1.0,
    "pinch": 1.0, "pinches": 1.0,
    "inch": 1.0, "inches": 1.0,
    "count": 1.0, "piece": 1.0, "pieces": 1.0, "whole": 1.0,
}

VOLUME_UNITS = {"ml", "milliliter", "tsp", "teaspoon", "tbsp", "tablespoon", "cup", "oz", "l", "liter"}
WEIGHT_UNITS = {"g", "gram", "kg", "kilogram", "lb", "pound", "mg"}
COUNT_UNITS = {"clove", "stalk", "sprig", "pinch", "inch", "count", "piece", "whole", "pod", "bulb"}


def normalize_quantity(qty_str):
    if not qty_str:
        return 0.0
    qty_str = str(qty_str).strip().lower()

    if " " in qty_str:
        parts = qty_str.split()
        try:
            total = 0.0
            for part in parts:
                if "/" in part:
                    n, d = part.split("/")
                    total += float(n) / float(d)
                else:
                    total += float(part)
            return total
        except ValueError:
            pass

    if "/" in qty_str:
        try:
            n, d = qty_str.split("/")
            return float(n) / float(d)
        except ValueError:
            pass

    try:
        return float(qty_str)
    except ValueError:
        return 0.0


def convert_to_base(qty, unit):
    q = normalize_quantity(qty)

    u = str(unit).lower().strip().rstrip('.')
    if u.endswith('s') and u not in ('glass', 'mass', 'molass'):
        u = u[:-1]

    factor = UNIT_MAP.get(u)
    if factor is None:
        factor = UNIT_MAP.get(u + 's', 1.0)

    if u in VOLUME_UNITS:
        return q * factor, "volume_ml"
    if u in WEIGHT_UNITS:
        return q * factor, "weight_g"
    return q * factor, "count"


def compare_quantities(q1, u1, q2, u2, tolerance=0.1):
    val1, type1 = convert_to_base(q1, u1)
    val2, type2 = convert_to_base(q2, u2)

    if type1 != type2:
        return False
    if val1 == 0 or val2 == 0:
        return False

    diff = abs(val1 - val2) / max(val1, val2)
    return diff <= tolerance
