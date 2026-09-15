"""Smoke tests for the core investment analysis.

``analyze`` is pure (no network or file I/O), so it can be exercised directly.
These tests guard against refactors breaking the analysis pipeline, not the
exact financial numbers.
"""
from investment_analyzer import Deal, analyze

VERDICTS = {"BUY", "CONSIDER", "NO BUY", "WATCH"}
RATINGS = {"PERFECT", "PASS", "MARGINAL", "AVOID", "WATCH"}


def make_deal(**overrides) -> Deal:
    fields = dict(
        sale_id="TEST-1",
        case="GD-00-000001",
        address="123 TEST ST",
        municipality="Pittsburgh",
        parcel="0000-X-00000",
        min_bid=15_000.0,
        tax_bid=None,
        fmv=120_000.0,
        assessed=90_000.0,
        year_built=1950,
        sqft=1_200,
        bedrooms=3,
    )
    fields.update(overrides)
    return Deal(**fields)


def test_analyze_returns_a_classified_deal():
    deal = analyze(make_deal())

    assert isinstance(deal, Deal)
    assert deal.verdict in VERDICTS
    assert deal.perfect_pass_rating in RATINGS
    assert isinstance(deal.red_flags, list)


def test_analyze_computes_financials():
    deal = analyze(make_deal())

    assert deal.arv > 0
    assert deal.total_all_in > 0


def test_analyze_is_deterministic():
    first = analyze(make_deal())
    second = analyze(make_deal())

    assert (first.verdict, first.score, first.flip_net_profit) == (
        second.verdict,
        second.score,
        second.flip_net_profit,
    )
