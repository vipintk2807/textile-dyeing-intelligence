from decimal import Decimal as D

import pytest

from textile_dyeing_intelligence.calculations import compute_variance


def v(p, a, pu="kg", au="kg", pb=None, ab=None):
    return compute_variance(
        None if p is None else D(p),
        None if a is None else D(a),
        planned_unit=pu,
        actual_unit=au,
        planned_basis=pb,
        actual_basis=ab,
    )


@pytest.mark.parametrize(
    "p,a,abs_var,pct",
    [
        ("10", "12", "2", "20"),
        ("10", "8", "-2", "-20"),
        ("10", "10", "0", "0"),
    ],
)
def test_variance_cases(p, a, abs_var, pct):
    r = v(p, a)
    assert r.status == "ok" and r.unit == "kg"
    assert r.absolute == D(abs_var) and r.percent == D(pct)


def test_zero_planned_gives_absolute_but_no_percentage():
    r = v("0", "5")
    assert r.status == "ok" and r.absolute == D(5) and r.percent is None
    assert "zero" in r.message


@pytest.mark.parametrize("p,a", [(None, "5"), ("10", None), (None, None)])
def test_missing_is_not_zero(p, a):
    r = v(p, a)
    assert r.status == "incomplete" and r.absolute is None and r.percent is None


def test_incompatible_units_and_basis_are_not_compared():
    assert v("10", "10000", au="g").status == "incompatible"
    assert v("10", "10", pb="per batch", ab="per 100 kg").status == "incompatible"
    assert v("10", "12", pu="KG", au=" kg ").status == "ok"  # case/space-insensitive unit match


def test_decimal_arithmetic_is_exact():
    r = v("0.1", "0.3")
    assert r.absolute == D("0.2")
    assert r.percent == D("200")
    r2 = v("3", "3.3")
    assert r2.percent == D("10")  # float arithmetic would give 10.000000000000009
