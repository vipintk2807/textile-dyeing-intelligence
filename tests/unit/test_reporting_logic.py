from decimal import Decimal

import pytest

from textile_dyeing_intelligence.errors import ValidationFailure
from textile_dyeing_intelligence.filters import ReportFilters, Where, batch_conditions, like_pattern
from textile_dyeing_intelligence.reporting.export import export_filename, rows_to_csv, safe_cell


def test_filter_validation_rejects_bad_ranges_and_dates():
    with pytest.raises(ValidationFailure):
        ReportFilters(start_date="2026-03-10", end_date="2026-03-01").validated()
    with pytest.raises(ValidationFailure):
        ReportFilters(start_date="10/03/2026").validated()
    assert ReportFilters(search="  ").validated().search is None


def test_like_pattern_escapes_wildcards():
    assert like_pattern("a%b_c") == "%a\\%b\\_c%"


def test_batch_conditions_use_bound_parameters():
    where = Where()
    batch_conditions(
        ReportFilters(search="x'; DROP TABLE batches;--", status="completed", start_date="2026-01-01").validated(),
        where,
    )
    assert "DROP" not in where.sql()
    assert len(where.params) == 4


@pytest.mark.parametrize("text", ["=1+1", "+SUM(A1)", "-2+3", "@cmd", " =1", "\t=1", "\r=1", "\n=1"])
def test_formula_text_is_neutralised(text):
    assert safe_cell(text).startswith("'")


def test_numbers_and_normal_text_untouched():
    assert safe_cell(Decimal("-2.50")) == "-2.50"
    assert safe_cell(-3) == "-3"
    assert safe_cell("Hello - world") == "Hello - world"
    assert safe_cell(None) == ""
    assert safe_cell("Café ✓") == "Café ✓"


def test_csv_header_order_and_empty_result():
    data = rows_to_csv(["B", "A"], [])
    assert data.decode("utf-8-sig") == "B,A\r\n"
    data = rows_to_csv(["B", "A"], [{"A": "x", "B": None}])
    assert data.decode("utf-8-sig").splitlines() == ["B,A", ",x"]


def test_export_filename():
    assert export_filename("quality") == "quality.csv"
    assert export_filename("quality", "2026-01-01", None) == "quality_2026-01-01_to_end.csv"
