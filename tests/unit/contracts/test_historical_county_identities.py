"""Contract tests for the reviewed CMS-only historical county identities."""

from __future__ import annotations

import csv
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[3]
SEED_PATH = REPOSITORY_ROOT / "analytics" / "seeds" / "historical_county_identities.csv"

EXPECTED_IDENTITIES = {
    "02261": ("AK-Valdez-Cordova", 2014, 2018),
    "02270": ("AK-Wade Hampton", 2014, 2014),
    "09001": ("CT-Fairfield", 2014, 2021),
    "09003": ("CT-Hartford", 2014, 2021),
    "09005": ("CT-Litchfield", 2014, 2021),
    "09007": ("CT-Middlesex", 2014, 2021),
    "09009": ("CT-New Haven", 2014, 2021),
    "09011": ("CT-New London", 2014, 2021),
    "09013": ("CT-Tolland", 2014, 2021),
    "09015": ("CT-Windham", 2014, 2021),
    "46113": ("SD-Shannon", 2014, 2014),
}


def test_historical_identity_seed_is_exact_and_does_not_invent_continuity() -> None:
    with SEED_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = set(reader.fieldnames or ())

    assert "successor_fips" not in fieldnames
    assert "allocation" not in " ".join(fieldnames).lower()
    assert {row["county_fips"] for row in rows} == set(EXPECTED_IDENTITIES)
    assert len(rows) == len(EXPECTED_IDENTITIES)
    for row in rows:
        county_fips = row["county_fips"]
        source_label, start_year, end_year = EXPECTED_IDENTITIES[county_fips]
        assert len(county_fips) == 5 and county_fips.isdigit()
        assert row["source_geography_description"] == source_label
        assert int(row["observed_cms_start_year"]) == start_year
        assert int(row["observed_cms_end_year"]) == end_year
        assert row["geography_status"] == "historical_source_only"
        assert row["is_current_county"] == "false"
        assert row["boundary_discontinuity_warning"]
        assert row["seed_version"] == "plan006.1"
