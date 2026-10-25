from __future__ import annotations

import re
from typing import Any


ALIASES = {
    "banana": ("bananas", "banana"),
    "milk": ("milk",),
    "rice": ("cooked rice", "rice"),
    "chapati": ("chapati", "roti"),
    "dal": ("dal", "lentils"),
    "egg": ("eggs", "egg"),
    "oats": ("oats", "oatmeal"),
    "paneer": ("paneer",),
    "idli": ("idli", "idlis"),
    "dosa": ("dosa", "dosas"),
    "curd": ("curd", "yogurt", "yoghurt"),
    "poha": ("poha",),
    "chicken": ("chicken breast", "chicken"),
    "fish": ("fish",),
    "peanut butter": ("peanut butter",),
    "chickpeas": ("chickpeas", "chickpea", "chana"),
    "rajma": ("rajma", "kidney beans"),
    "soya chunks": ("soya chunks", "soy chunks"),
    "mixed vegetables": ("mixed vegetables", "vegetables"),
    "samosa": ("samosa", "samosas"),
}
NUMBER_WORDS = {
    "a": 1.0, "an": 1.0, "one": 1.0, "two": 2.0, "three": 3.0,
    "four": 4.0, "five": 5.0, "half": 0.5,
}
SEGMENT = re.compile(
    r"^\s*(?P<amount>\d+(?:\.\d+)?|a|an|one|two|three|four|five|half)?\s*"
    r"(?P<unit>milliliters?|ml|grams?|g|cups?|tablespoons?|tbsp|pieces?|pcs)?\s*"
    r"(?:of\s+)?(?P<food>.+?)\s*$",
    re.IGNORECASE,
)


def _serving_amount(food: Any, requested_unit: str = "") -> tuple[float, str] | None:
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*(g|ml|cup|cups|tbsp|tablespoon|piece|pieces)", food.serving.casefold())
    normalized = [
        (
            float(amount),
            "cup" if unit == "cups" else "tbsp" if unit == "tablespoon" else "piece" if unit == "pieces" else unit,
        )
        for amount, unit in matches
    ]
    if requested_unit:
        return next((item for item in normalized if item[1] == requested_unit), None)
    if normalized:
        return normalized[0]
    if food.name.casefold().startswith(("banana", "egg")):
        return 1.0, "piece"
    return None


def parse_food_description(description: str, foods: list[Any]) -> dict:
    """Parse a deliberately small, transparent food vocabulary; unsupported phrases need clarification."""
    pieces = re.split(r"\s*(?:,|;|\band\b|\+)\s*", description.strip(), flags=re.IGNORECASE)
    if not description.strip() or not pieces or len(pieces) > 12:
        return {"items": [], "clarification": "Please describe one to twelve foods, with a quantity for each."}

    parsed = []
    for phrase in pieces:
        match = SEGMENT.fullmatch(phrase)
        if not match:
            return {"items": [], "clarification": f"I couldn't parse “{phrase}”. Add a quantity, such as “2 bananas”."}
        amount_text = (match.group("amount") or "").casefold()
        if amount_text in NUMBER_WORDS:
            amount = NUMBER_WORDS[amount_text]
        elif amount_text:
            amount = float(amount_text)
        else:
            return {"items": [], "clarification": f"How much {match.group('food').strip()} did you have?"}
        if amount <= 0 or amount > 1000:
            return {"items": [], "clarification": "Please use a positive quantity no greater than 1,000."}

        food_text = re.sub(r"^(?:of\s+)", "", match.group("food").strip(), flags=re.IGNORECASE).casefold()
        candidates = []
        for canonical, aliases in ALIASES.items():
            if any(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", food_text) for alias in aliases):
                candidates.extend(food for food in foods if canonical in food.name.casefold() or any(alias in food.name.casefold() for alias in aliases))
        candidates = list({food.id: food for food in candidates}.values())
        if len(candidates) != 1:
            if candidates:
                return {"items": [], "clarification": f"Which {food_text} did you mean? Choose a specific food in the nutrition journal."}
            return {"items": [], "clarification": f"I don't have “{food_text}” in the local food catalogue yet. Please log it manually with nutrition values."}

        food = candidates[0]
        given_unit = (match.group("unit") or "").casefold()
        given_unit = {"milliliter": "ml", "milliliters": "ml", "gram": "g", "grams": "g", "cup": "cup", "cups": "cup", "tablespoon": "tbsp", "tablespoons": "tbsp", "piece": "piece", "pieces": "piece", "pcs": "piece"}.get(given_unit, given_unit)
        if given_unit:
            serving = _serving_amount(food, given_unit)
            if not serving or given_unit != serving[1]:
                return {"items": [], "clarification": f"The catalogue serving for {food.name} is “{food.serving}”; I can't reliably convert {given_unit} to that serving."}
            quantity = amount / serving[0]
        else:
            serving = _serving_amount(food)
            quantity = amount / serving[0] if serving and serving[1] == "piece" else amount

        parsed.append({
            "food_id": food.id,
            "food_name": food.name,
            "quantity": round(quantity, 4),
            "serving_unit": food.serving,
            "calories": food.calories,
            "protein_g": food.protein_g,
            "carbs_g": food.carbs_g,
            "fat_g": food.fat_g,
            "meal": "Breakfast",
            "notes": "Estimated from the local food catalogue.",
            "assumption": f"{amount:g} {given_unit or 'serving(s)'} converted to {quantity:g} × {food.serving}.",
            "estimated": food.estimated,
        })

    totals = {key: round(sum(item[key] * item["quantity"] for item in parsed), 1) for key in ("calories", "protein_g", "carbs_g", "fat_g")}
    return {"items": parsed, "totals": totals, "clarification": None}
