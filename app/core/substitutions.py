"""Simple, honest ingredient swaps for when something is missing."""
from __future__ import annotations

SUBSTITUTIONS: dict[str, list[str]] = {
    "egg": ["1/4 cup (60 g) mashed banana per egg works in sweet dishes", "1 tbsp ground flax + 3 tbsp water per egg in baking"],
    "milk": ["Equal amount of plain yogurt thinned with water", "Any plant milk (oat, soy, almond) 1:1"],
    "butter": ["Olive oil, about 3/4 of the amount", "Ghee or margarine 1:1"],
    "yogurt": ["Equal amount of sour cream", "Milk + 1 tsp lemon juice per 1/4 cup, left 10 minutes"],
    "cheddar cheese": ["Any melting cheese (mozzarella, gouda) 1:1", "Paneer, crumbled, in wraps and omelettes"],
    "paneer": ["Firm tofu, pressed and cubed, 1:1", "Halloumi or feta for a saltier result"],
    "chicken breast": ["Firm tofu or paneer 1:1 (vegetarian)", "Chickpeas, 1 can per 300 g chicken"],
    "tofu": ["Paneer 1:1", "Chickpeas or boiled eggs for protein"],
    "spinach": ["Any leafy green: kale, chard, or fenugreek leaves", "Frozen spinach, half the weight"],
    "onion": ["Spring onions or leeks 1:1", "1 tsp onion powder per medium onion"],
    "garlic": ["1/4 tsp garlic powder per clove"],
    "lemon": ["1 tbsp vinegar per 1/2 lemon (juice only)", "Lime 1:1"],
    "tomato": ["Canned tomatoes, 100 g per fresh tomato", "1 tbsp tomato paste + 50 ml water"],
    "canned tomatoes": ["Fresh tomatoes, chopped and cooked down for 10 extra minutes"],
    "rice": ["Quinoa, couscous or any pasta 1:1 by dry weight"],
    "pasta": ["Rice noodles or spaghetti-style noodles 1:1", "Cooked rice as a base"],
    "tortilla": ["Chapati/roti or pita bread 1:1", "Two slices of bread for a sandwich version"],
    "bread": ["Tortilla, roti or pita 1:1"],
    "honey": ["Maple syrup or jaggery syrup 1:1", "Sugar, 3/4 of the amount"],
    "peanut butter": ["Any nut or seed butter 1:1"],
    "soy sauce": ["Tamari 1:1 (gluten free)", "Worcestershire sauce, half the amount, plus a pinch of salt"],
    "bell pepper": ["Zucchini, carrot sticks or green beans 1:1"],
    "mushroom": ["Zucchini or aubergine, cubed 1:1"],
    "potato": ["Sweet potato 1:1", "Parsnip or turnip 1:1"],
    "carrot": ["Sweet potato or pumpkin 1:1"],
    "broccoli": ["Cauliflower or green beans 1:1"],
    "canned tuna": ["Canned chickpeas, mashed with a little extra lemon"],
    "red lentils": ["Yellow split lentils (moong dal) 1:1"],
    "chickpeas": ["White beans or kidney beans 1:1"],
}


def suggest_substitutions(names: list[str]) -> dict[str, list[str]]:
    return {n: SUBSTITUTIONS[n.lower()] for n in names if n.lower() in SUBSTITUTIONS}
