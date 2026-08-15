"""Tests for atomic, network-free CMS v2 and SVI input assembly."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request

import duckdb
import pytest

from kidney_care_mart.extract.cdc_svi_county_2022 import (
    extract_cdc_svi_county_2022,
)
from kidney_care_mart.extract.http import RetryPolicy
from kidney_care_mart.extract.manifest import canonical_json_bytes
from kidney_care_mart.stage.build_inputs import (
    BuildInputConflictError,
    BuildInputError,
    build_input_database,
)

CMS_FIXTURE_DIR = Path(__file__).parents[2] / "fixtures" / "cms_om_gv"
SVI_FIXTURE_DIR = Path(__file__).parents[2] / "fixtures" / "cdc_svi_county_2022"


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self._stream = io.BytesIO(content)
        self.headers = {"Content-Length": str(len(content))}

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)


class SviFixtureOpener:
    def __call__(self, request: Request, _timeout: float) -> FakeResponse:
        parsed = urlparse(request.full_url)
        query = parse_qs(parsed.query)
        if parsed.path.endswith("/1"):
            path = SVI_FIXTURE_DIR / "layer.json"
        elif query.get("returnCountOnly") == ["true"]:
            path = SVI_FIXTURE_DIR / "count.json"
        else:
            offset = int(query["resultOffset"][0])
            path = SVI_FIXTURE_DIR / "pages" / f"page-{offset:06d}.json"
        return FakeResponse(path.read_bytes())


def fixed_now() -> datetime:
    return datetime(2026, 8, 14, 20, 0, tzinfo=UTC)


def materialize_source_manifests(tmp_path: Path) -> tuple[Path, Path, Path]:
    raw_root = tmp_path / "raw"
    cms_payload = json.loads((CMS_FIXTURE_DIR / "staging-manifest.json").read_bytes())
    cms_blob = raw_root.joinpath(*cms_payload["storage"]["blob_path"].split("/"))
    cms_blob.parent.mkdir(parents=True)
    cms_blob.write_bytes((CMS_FIXTURE_DIR / "staging.csv").read_bytes())
    cms_manifest = (
        raw_root
        / "manifests"
        / "cms_om_gv"
        / f"{cms_payload['pipeline']['run_id']}.json"
    )
    cms_manifest.parent.mkdir(parents=True)
    cms_manifest.write_bytes(canonical_json_bytes(cms_payload))

    svi = extract_cdc_svi_county_2022(
        run_id="cdc-svi-build-input-fixture-001",
        output_root=raw_root,
        opener=SviFixtureOpener(),
        sleep=lambda _seconds: None,
        jitter=lambda: 0.0,
        now=fixed_now,
        page_size=2,
        retry_policy=RetryPolicy(max_attempts=1),
    )
    return raw_root, cms_manifest, svi.manifest_path


def test_two_verified_manifests_publish_one_reconciled_database(
    tmp_path: Path,
) -> None:
    raw_root, cms_manifest, svi_manifest = materialize_source_manifests(tmp_path)
    database_path = tmp_path / "combined.duckdb"

    result = build_input_database(
        build_id="plan-006-fixture-build-001",
        cms_manifest_path=cms_manifest,
        svi_manifest_path=svi_manifest,
        raw_root=raw_root,
        database_path=database_path,
    )

    assert result.status == "loaded"
    assert not result.database_noop
    assert result.cms_row_count == 11
    assert result.svi_row_count == 3
    assert len(result.input_set_sha256) == 64
    with duckdb.connect(str(database_path), read_only=True) as connection:
        counts = connection.execute(
            """
            select
                (select count(*) from raw.cms_om_gv),
                (select count(*) from raw.cdc_svi_county_2022),
                (select count(*) from raw.cms_om_gv_load_audit),
                (select count(*) from raw.cdc_svi_county_2022_load_audit),
                (select count(*) from raw.build_input_audit)
            """
        ).fetchone()
        audit = connection.execute(
            """
            select build_id,
                   input_set_sha256,
                   cms_contract_version,
                   cms_row_count,
                   svi_contract_version,
                   svi_page_count,
                   svi_row_count
            from raw.build_input_audit
            """
        ).fetchone()
    assert counts == (11, 3, 1, 1, 1)
    assert audit == (
        "plan-006-fixture-build-001",
        result.input_set_sha256,
        "cms_om_gv.raw.v2",
        11,
        "cdc_svi_county_2022.raw.v1",
        2,
        3,
    )


def test_same_build_and_inputs_are_an_idempotent_noop(tmp_path: Path) -> None:
    raw_root, cms_manifest, svi_manifest = materialize_source_manifests(tmp_path)
    database_path = tmp_path / "combined.duckdb"
    arguments = {
        "build_id": "plan-006-fixture-build-001",
        "cms_manifest_path": cms_manifest,
        "svi_manifest_path": svi_manifest,
        "raw_root": raw_root,
        "database_path": database_path,
    }

    first = build_input_database(**arguments)
    second = build_input_database(**arguments)

    assert not first.database_noop
    assert second.status == "database_noop"
    assert second.database_noop
    assert second.input_set_sha256 == first.input_set_sha256


def test_v1_cms_manifest_requires_an_explicit_contract_upgrade(
    tmp_path: Path,
) -> None:
    raw_root, cms_manifest, svi_manifest = materialize_source_manifests(tmp_path)
    payload = json.loads(cms_manifest.read_bytes())
    payload["schema"]["contract_version"] = "cms_om_gv.raw.v1"
    cms_manifest.write_bytes(canonical_json_bytes(payload))

    with pytest.raises(BuildInputError, match="cms_contract_upgrade_required"):
        build_input_database(
            build_id="plan-006-fixture-build-001",
            cms_manifest_path=cms_manifest,
            svi_manifest_path=svi_manifest,
            raw_root=raw_root,
            database_path=tmp_path / "combined.duckdb",
        )

    assert not (tmp_path / "combined.duckdb").exists()


def test_corrupt_source_cannot_publish_a_partial_combined_database(
    tmp_path: Path,
) -> None:
    raw_root, cms_manifest, svi_manifest = materialize_source_manifests(tmp_path)
    payload = json.loads(cms_manifest.read_bytes())
    cms_blob = raw_root.joinpath(*payload["storage"]["blob_path"].split("/"))
    cms_blob.write_bytes(b"corrupt")
    database_path = tmp_path / "combined.duckdb"

    with pytest.raises(BuildInputError, match="CMS input verification failed"):
        build_input_database(
            build_id="plan-006-fixture-build-001",
            cms_manifest_path=cms_manifest,
            svi_manifest_path=svi_manifest,
            raw_root=raw_root,
            database_path=database_path,
        )

    assert not database_path.exists()


def test_corrupt_svi_page_cannot_publish_a_partial_combined_database(
    tmp_path: Path,
) -> None:
    raw_root, cms_manifest, svi_manifest = materialize_source_manifests(tmp_path)
    payload = json.loads(svi_manifest.read_bytes())
    svi_page = raw_root.joinpath(*payload["pages"][0]["blob_path"].split("/"))
    svi_page.write_bytes(b"corrupt")
    database_path = tmp_path / "combined.duckdb"

    with pytest.raises(BuildInputError, match="SVI input verification failed"):
        build_input_database(
            build_id="plan-006-fixture-build-001",
            cms_manifest_path=cms_manifest,
            svi_manifest_path=svi_manifest,
            raw_root=raw_root,
            database_path=database_path,
        )

    assert not database_path.exists()


def test_missing_svi_manifest_cannot_publish_a_partial_combined_database(
    tmp_path: Path,
) -> None:
    raw_root, cms_manifest, svi_manifest = materialize_source_manifests(tmp_path)
    svi_manifest.unlink()
    database_path = tmp_path / "combined.duckdb"

    with pytest.raises(BuildInputError, match="SVI input verification failed"):
        build_input_database(
            build_id="plan-006-fixture-build-001",
            cms_manifest_path=cms_manifest,
            svi_manifest_path=svi_manifest,
            raw_root=raw_root,
            database_path=database_path,
        )

    assert not database_path.exists()


def test_wrong_svi_source_manifest_cannot_publish_a_combined_database(
    tmp_path: Path,
) -> None:
    raw_root, cms_manifest, svi_manifest = materialize_source_manifests(tmp_path)
    payload = json.loads(svi_manifest.read_bytes())
    payload["source"]["logical_source_id"] = "other_source"
    svi_manifest.write_bytes(canonical_json_bytes(payload))
    database_path = tmp_path / "combined.duckdb"

    with pytest.raises(
        BuildInputError, match=r"SVI input verification failed:.*source"
    ):
        build_input_database(
            build_id="plan-006-fixture-build-001",
            cms_manifest_path=cms_manifest,
            svi_manifest_path=svi_manifest,
            raw_root=raw_root,
            database_path=database_path,
        )

    assert not database_path.exists()


@pytest.mark.parametrize("staging_kind", ["inputs", "partial"])
def test_preexisting_staging_path_blocks_the_combined_build(
    tmp_path: Path, staging_kind: str
) -> None:
    raw_root, cms_manifest, svi_manifest = materialize_source_manifests(tmp_path)
    database_path = tmp_path / "combined.duckdb"
    staging_path = tmp_path / (
        f".combined.duckdb.plan-006-fixture-build-001.{staging_kind}"
    )
    if staging_kind == "inputs":
        staging_path.mkdir()
    else:
        staging_path.write_bytes(b"partial")

    with pytest.raises(BuildInputConflictError, match="staging path already exists"):
        build_input_database(
            build_id="plan-006-fixture-build-001",
            cms_manifest_path=cms_manifest,
            svi_manifest_path=svi_manifest,
            raw_root=raw_root,
            database_path=database_path,
        )

    assert not database_path.exists()


def test_different_inputs_cannot_overwrite_an_existing_database(
    tmp_path: Path,
) -> None:
    raw_root, cms_manifest, svi_manifest = materialize_source_manifests(tmp_path)
    database_path = tmp_path / "combined.duckdb"
    build_input_database(
        build_id="plan-006-fixture-build-001",
        cms_manifest_path=cms_manifest,
        svi_manifest_path=svi_manifest,
        raw_root=raw_root,
        database_path=database_path,
    )
    original_bytes = database_path.read_bytes()

    with pytest.raises(BuildInputConflictError, match="different build or inputs"):
        build_input_database(
            build_id="plan-006-fixture-build-002",
            cms_manifest_path=cms_manifest,
            svi_manifest_path=svi_manifest,
            raw_root=raw_root,
            database_path=database_path,
        )

    assert database_path.read_bytes() == original_bytes
