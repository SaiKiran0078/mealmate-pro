import pytest

from app.core.units import UnitError, format_quantity, normalize_unit, to_base, to_grams
from tests.factories import make_ing

OIL = make_ing(1, "olive oil", "ml", density_g_per_ml=0.91)
RICE = make_ing(2, "rice", "g", density_g_per_ml=0.85)
ONION = make_ing(3, "onion", "pcs", grams_per_piece=110)
MILK = make_ing(4, "milk", "ml")


@pytest.mark.parametrize(
    "amount, unit, ing, expected",
    [
        (1, "tbsp", OIL, 15),  # volume -> ml, same family
        (2, "tsp", OIL, 10),
        (1, "l", OIL, 1000),
        (1.5, "kg", RICE, 1500),  # mass -> g
        (1, "cup", RICE, 204),  # volume -> grams through density (240 ml * 0.85)
        (110, "g", ONION, 1),  # mass -> pieces through grams_per_piece
        (3, "cloves", ONION, 3),  # alias, count -> count
        (100, "g", OIL, 100 / 0.91),  # mass -> ml through density
    ],
)
def test_to_base(amount, unit, ing, expected):
    assert to_base(amount, unit, ing) == pytest.approx(expected)


def test_pieces_without_weight_cannot_convert():
    with pytest.raises(UnitError):
        to_base(2, "pcs", MILK)


@pytest.mark.parametrize("bad", ["furlong", "banana"])
def test_unknown_unit(bad):
    with pytest.raises(UnitError):
        normalize_unit(bad)


@pytest.mark.parametrize("amount", [0, -5])
def test_quantity_must_be_positive(amount):
    with pytest.raises(UnitError):
        to_base(amount, "g", RICE)


def test_to_grams():
    assert to_grams(100, RICE) == 100
    assert to_grams(100, OIL) == pytest.approx(91)
    assert to_grams(2, ONION) == 220


@pytest.mark.parametrize(
    "qty, unit, text",
    [(1500, "g", "1.5 kg"), (250, "g", "250 g"), (2000, "ml", "2 l"), (45, "ml", "45 ml"), (3, "pcs", "3 pcs"), (0.5, "pcs", "0.5 pcs")],
)
def test_format_quantity(qty, unit, text):
    assert format_quantity(qty, unit) == text
