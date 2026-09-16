"""Regression test for #21: report PDFs must not share map coordinates.

``build_and_save_pdf`` used to merge its ``geocache_extra`` argument into the
module-level ``GEOCACHE`` dict, so property pages read coordinates from
process-wide shared state (``GEOCACHE.get(d.sale_id)``). Spot checks always
key their entry as ``"SPOT"`` and now run as background jobs (#19), so two
spot-check PDFs can genuinely build at the same time. One build's coordinates
could overwrite another's while the first was still mid-render, and its page
would show the wrong property's map.
"""
from generate_pdf_report import build_and_save_pdf
import generate_pdf_report as gpr
from investment_analyzer import Deal, analyze


def make_deal(**overrides) -> Deal:
    fields = dict(
        sale_id="SPOT",
        case="N/A",
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


def test_a_concurrent_build_does_not_change_another_builds_map(tmp_path, monkeypatch):
    requested = []
    monkeypatch.setattr(gpr, "fetch_map_image",
                        lambda lat, lon: requested.append((lat, lon)) or None)

    deal_a, deal_b = analyze(make_deal()), analyze(make_deal())
    coords_a, coords_b = (40.0, -80.0), (41.0, -81.0)

    def start_build_b_mid_render(_current, _total, phase):
        # Fires right before build A reads its geocache for the property page —
        # the exact point a second, overlapping spot-check job would land in
        # production. Build B doesn't pass its own progress_cb, so this can't
        # recurse.
        if phase == "property":
            build_and_save_pdf([deal_b], tmp_path / "b.pdf",
                               geocache_extra={"SPOT": coords_b}, skip_cover=True)

    build_and_save_pdf([deal_a], tmp_path / "a.pdf", geocache_extra={"SPOT": coords_a},
                       skip_cover=True, progress_cb=start_build_b_mid_render)

    # Build B's own page renders first (triggered from inside A's callback),
    # correctly with B's coordinates; build A's page renders second. Before the
    # fix, A's page read the shared GEOCACHE and got B's coordinates instead of
    # its own.
    assert requested == [coords_b, coords_a]
