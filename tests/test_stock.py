from datetime import date

from app.core.stock import Batch, available, clone, consume

D = date(2026, 10, 25)


def test_uses_earliest_expiry_first():
    stock = {1: [Batch(100, date(2026, 11, 5), 10), Batch(100, date(2026, 10, 27), 11), Batch(100, None, 12)]}
    result = consume(stock, {1: 150}, D)
    assert result.shortfall == {}
    assert result.deductions == [(11, 100), (10, 50)]  # soonest first, undated batch untouched
    assert stock[1][2].qty == 100


def test_expired_batches_are_ignored():
    stock = {1: [Batch(500, date(2026, 10, 20)), Batch(50)]}
    assert available(stock, 1, D) == 50
    result = consume(stock, {1: 80}, D)
    assert result.shortfall == {1: 30}


def test_batch_usable_on_its_last_day_but_not_after():
    stock = {1: [Batch(10, D)]}
    assert available(stock, 1, D) == 10
    assert available(stock, 1, date(2026, 10, 26)) == 0


def test_unknown_ingredient_is_full_shortfall():
    assert consume({}, {7: 25}, D).shortfall == {7: 25}


def test_clone_is_independent():
    stock = {1: [Batch(100)]}
    copy = clone(stock)
    consume(copy, {1: 60}, D)
    assert stock[1][0].qty == 100 and copy[1][0].qty == 40
