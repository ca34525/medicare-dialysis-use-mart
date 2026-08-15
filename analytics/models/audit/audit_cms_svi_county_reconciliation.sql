{{ config(contract={"enforced": true}) }}

with cms_latest_year as (
    select max(year) as year
    from {{ ref('fct_medicare_county_year') }}
),

cms_keys as (
    select
        fact.county_fips,
        count(*) as cms_row_count
    from {{ ref('fct_medicare_county_year') }} as fact
    inner join cms_latest_year on fact.year = cms_latest_year.year
    group by fact.county_fips
),

svi_keys as (
    select
        county_fips,
        count(*) as svi_row_count
    from {{ ref('fct_svi_county') }}
    group by county_fips
),

source_lineage as (
    select
        cms.year as cms_latest_year,
        cms.source_manifest_run_id as cms_source_manifest_run_id,
        cms.source_content_sha256 as cms_source_content_sha256,
        cms.source_modified_at as cms_source_modified_at,
        svi.svi_vintage as svi_vintage,
        svi.source_manifest_run_id as svi_source_manifest_run_id,
        svi.source_snapshot_sha256 as svi_source_snapshot_sha256,
        svi.source_modified_at as svi_source_modified_at
    from (
        select distinct
            fact.year,
            fact.source_manifest_run_id,
            fact.source_content_sha256,
            fact.source_modified_at
        from {{ ref('fct_medicare_county_year') }} as fact
        inner join cms_latest_year on fact.year = cms_latest_year.year
    ) as cms
    cross join (
        select distinct
            svi_vintage,
            source_manifest_run_id,
            source_snapshot_sha256,
            source_modified_at
        from {{ ref('fct_svi_county') }}
    ) as svi
),

reconciled as (
    select
        coalesce(cms.county_fips, svi.county_fips) as county_fips,
        case
            when cms.cms_row_count is null then 'svi_only'
            when svi.svi_row_count is null then 'cms_only'
            when cms.cms_row_count > 1 and svi.svi_row_count > 1
                then 'duplicate_both'
            when cms.cms_row_count > 1 then 'cms_duplicate'
            when svi.svi_row_count > 1 then 'svi_duplicate'
            else 'matched'
        end as reconciliation_status,
        cms.cms_row_count is not null as cms_present,
        svi.svi_row_count is not null as svi_present,
        coalesce(cms.cms_row_count, 0) as cms_row_count,
        coalesce(svi.svi_row_count, 0) as svi_row_count
    from cms_keys as cms
    full outer join svi_keys as svi using (county_fips)
)

select
    reconciled.*,
    source_lineage.*
from reconciled
cross join source_lineage
