"""ISO 14224 canonical data model — hierarchy, taxonomy, and failure events

Revision ID: 007_iso14224_canonical_model
Revises: 006_repair_plan_and_parts
Create Date: 2026-03-22 00:00:00.000000

Adds:
  - Asset hierarchy tables (L1–L8): industries, business_units, sites,
    facilities, systems, equipment_units, subunits, components
  - ISO 14224 taxonomy reference tables: iso_failure_modes,
    iso_failure_mechanisms, iso_failure_causes, iso_maintenance_actions,
    iso_detection_methods
  - Canonical failure_events table with ISO-coded classification
  - CMMS code mapping tables: sap_failure_code_map, maximo_failure_code_map
  - Seed data for all taxonomy tables from ISO 14224 Annex B
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "007_iso14224_canonical_model"
down_revision: Union[str, None] = "006_repair_plan_and_parts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── L1: Industries ──
    op.create_table(
        "industries",
        sa.Column("industry_code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("industry_code"),
    )

    # ── L2: Business Units ──
    op.create_table(
        "business_units",
        sa.Column("bu_code", sa.Text(), nullable=False),
        sa.Column("industry_code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("bu_code"),
        sa.ForeignKeyConstraint(["industry_code"], ["industries.industry_code"]),
    )

    # ── L3: Sites ──
    op.create_table(
        "sites",
        sa.Column("site_id", sa.Text(), nullable=False),
        sa.Column("bu_code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("basin_region", sa.Text()),
        sa.Column("onshore_offshore", sa.Text()),
        sa.Column("country", sa.Text()),
        sa.Column("geo_latitude", sa.Float()),
        sa.Column("geo_longitude", sa.Float()),
        sa.Column("tenant_id", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("site_id"),
        sa.ForeignKeyConstraint(["bu_code"], ["business_units.bu_code"]),
    )
    op.create_index("idx_sites_tenant", "sites", ["tenant_id"])

    # ── L4: Facilities ──
    op.create_table(
        "facilities",
        sa.Column("facility_id", sa.Text(), nullable=False),
        sa.Column("site_id", sa.Text(), nullable=False),
        sa.Column("facility_type", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("facility_id"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.site_id"]),
    )

    # ── L5: Systems ──
    op.create_table(
        "systems",
        sa.Column("system_id", sa.Text(), nullable=False),
        sa.Column("facility_id", sa.Text(), nullable=False),
        sa.Column("system_type", sa.Text(), nullable=False),
        sa.Column("system_group", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("system_id"),
        sa.ForeignKeyConstraint(["facility_id"], ["facilities.facility_id"]),
    )

    # ── L6: Equipment Units ──
    op.create_table(
        "equipment_units",
        sa.Column("equipment_unit_id", sa.Text(), nullable=False),
        sa.Column("system_id", sa.Text(), nullable=False),
        sa.Column("tag", sa.Text(), nullable=False),
        sa.Column("iso_equipment_class", sa.Text(), nullable=False),
        sa.Column("equipment_family", sa.Text()),
        sa.Column("oem_name", sa.Text()),
        sa.Column("oem_model", sa.Text()),
        sa.Column("criticality", sa.Text()),
        sa.Column("service_medium", sa.Text()),
        sa.Column("duty_type", sa.Text()),
        sa.Column("safety_critical", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("install_date", sa.Date()),
        sa.Column("design_pressure_bar", sa.Float()),
        sa.Column("design_temperature_c", sa.Float()),
        sa.Column("rated_power_kw", sa.Float()),
        sa.Column("rated_speed_rpm", sa.Float()),
        sa.Column("tenant_id", sa.Text()),
        sa.Column("hierarchy_path", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("equipment_unit_id"),
        sa.ForeignKeyConstraint(["system_id"], ["systems.system_id"]),
    )
    op.create_index("idx_equip_tag", "equipment_units", ["tag"])
    op.create_index("idx_equip_class", "equipment_units", ["iso_equipment_class"])
    op.create_index("idx_equip_tenant", "equipment_units", ["tenant_id"])
    op.create_index("idx_equip_family", "equipment_units", ["equipment_family"])

    # ── L7: Sub-units ──
    op.create_table(
        "subunits",
        sa.Column("subunit_id", sa.Text(), nullable=False),
        sa.Column("equipment_unit_id", sa.Text(), nullable=False),
        sa.Column("subunit_type_code", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("subunit_id"),
        sa.ForeignKeyConstraint(["equipment_unit_id"], ["equipment_units.equipment_unit_id"]),
    )

    # ── L8: Components ──
    op.create_table(
        "components",
        sa.Column("component_id", sa.Text(), nullable=False),
        sa.Column("subunit_id", sa.Text(), nullable=False),
        sa.Column("component_type_code", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("component_id"),
        sa.ForeignKeyConstraint(["subunit_id"], ["subunits.subunit_id"]),
    )

    # ── ISO 14224 taxonomy reference tables ──

    op.create_table(
        "iso_failure_modes",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("applicable_equipment_families", sa.Text()),
        sa.PrimaryKeyConstraint("code"),
    )

    op.create_table(
        "iso_failure_mechanisms",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.PrimaryKeyConstraint("code"),
    )

    op.create_table(
        "iso_failure_causes",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.PrimaryKeyConstraint("code"),
    )

    op.create_table(
        "iso_maintenance_actions",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("maintenance_category", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.PrimaryKeyConstraint("code"),
    )

    op.create_table(
        "iso_detection_methods",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.PrimaryKeyConstraint("code"),
    )

    # ── Canonical failure_events table ──
    op.create_table(
        "failure_events",
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.Text()),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("equipment_unit_id", sa.Text()),
        sa.Column("component_id", sa.Text()),
        sa.Column("asset_id", sa.Text()),
        sa.Column("failure_mode_code", sa.Text()),
        sa.Column("failure_mechanism_code", sa.Text()),
        sa.Column("failure_cause_code", sa.Text()),
        sa.Column("maintenance_action_code", sa.Text()),
        sa.Column("detection_method_code", sa.Text()),
        sa.Column("consequence_code", sa.Text()),
        sa.Column("impact_level", sa.Text()),
        sa.Column("severity", sa.Text()),
        sa.Column("kind", sa.Text()),
        sa.Column("summary", sa.Text()),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("lineage", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("raw_source_ids", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("failure_start_ts", sa.DateTime(timezone=True)),
        sa.Column("restoration_ts", sa.DateTime(timezone=True)),
        sa.Column("downtime_hours", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("idx_failure_events_equipment", "failure_events", ["equipment_unit_id"])
    op.create_index("idx_failure_events_component", "failure_events", ["component_id"])
    op.create_index("idx_failure_events_asset", "failure_events", ["asset_id"])
    op.create_index("idx_failure_events_tenant", "failure_events", ["tenant_id"])
    op.create_index("idx_failure_events_mode", "failure_events", ["failure_mode_code"])
    op.create_index("idx_failure_events_start", "failure_events", ["failure_start_ts"])

    # ── CMMS code mapping tables ──
    op.create_table(
        "sap_failure_code_map",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_domain", sa.Text(), nullable=False),
        sa.Column("source_code", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("iso_concept", sa.Text(), nullable=False),
        sa.Column("iso_standard_code", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_sap_map_lookup", "sap_failure_code_map", ["source_domain", "source_code"])

    op.create_table(
        "maximo_failure_code_map",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_domain", sa.Text(), nullable=False),
        sa.Column("source_code", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("iso_concept", sa.Text(), nullable=False),
        sa.Column("iso_standard_code", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_maximo_map_lookup", "maximo_failure_code_map", ["source_domain", "source_code"])

    # ── Seed ISO taxonomy data ──
    _seed_taxonomy()


def _seed_taxonomy() -> None:
    from maintenance_intelligence.core.taxonomy.failure_codes import (
        FAILURE_MODES,
        FAILURE_MECHANISMS,
        FAILURE_CAUSES,
        MAINTENANCE_ACTIONS,
        DETECTION_METHODS,
    )

    conn = op.get_bind()

    for code, name, desc in FAILURE_MODES:
        conn.execute(
            sa.text("INSERT INTO iso_failure_modes (code, name, description) VALUES (:c, :n, :d) ON CONFLICT (code) DO NOTHING"),
            {"c": code, "n": name, "d": desc},
        )

    for code, name, desc in FAILURE_MECHANISMS:
        conn.execute(
            sa.text("INSERT INTO iso_failure_mechanisms (code, name, description) VALUES (:c, :n, :d) ON CONFLICT (code) DO NOTHING"),
            {"c": code, "n": name, "d": desc},
        )

    for code, name, category, desc in FAILURE_CAUSES:
        conn.execute(
            sa.text("INSERT INTO iso_failure_causes (code, name, category, description) VALUES (:c, :n, :cat, :d) ON CONFLICT (code) DO NOTHING"),
            {"c": code, "n": name, "cat": category, "d": desc},
        )

    for code, name, maint_cat, desc in MAINTENANCE_ACTIONS:
        conn.execute(
            sa.text("INSERT INTO iso_maintenance_actions (code, name, maintenance_category, description) VALUES (:c, :n, :mc, :d) ON CONFLICT (code) DO NOTHING"),
            {"c": code, "n": name, "mc": maint_cat, "d": desc},
        )

    for code, name, desc in DETECTION_METHODS:
        conn.execute(
            sa.text("INSERT INTO iso_detection_methods (code, name, description) VALUES (:c, :n, :d) ON CONFLICT (code) DO NOTHING"),
            {"c": code, "n": name, "d": desc},
        )

    # Seed Oil & Gas industry and upstream business unit
    conn.execute(
        sa.text("INSERT INTO industries (industry_code, name) VALUES (:c, :n) ON CONFLICT (industry_code) DO NOTHING"),
        {"c": "OILGAS", "n": "Oil and Gas"},
    )
    conn.execute(
        sa.text("INSERT INTO business_units (bu_code, industry_code, name) VALUES (:c, :i, :n) ON CONFLICT (bu_code) DO NOTHING"),
        {"c": "UP", "i": "OILGAS", "n": "Upstream"},
    )
    conn.execute(
        sa.text("INSERT INTO business_units (bu_code, industry_code, name) VALUES (:c, :i, :n) ON CONFLICT (bu_code) DO NOTHING"),
        {"c": "MS", "i": "OILGAS", "n": "Midstream"},
    )
    conn.execute(
        sa.text("INSERT INTO business_units (bu_code, industry_code, name) VALUES (:c, :i, :n) ON CONFLICT (bu_code) DO NOTHING"),
        {"c": "DS", "i": "OILGAS", "n": "Downstream"},
    )


def downgrade() -> None:
    op.drop_table("maximo_failure_code_map")
    op.drop_table("sap_failure_code_map")
    op.drop_table("failure_events")
    op.drop_table("iso_detection_methods")
    op.drop_table("iso_maintenance_actions")
    op.drop_table("iso_failure_causes")
    op.drop_table("iso_failure_mechanisms")
    op.drop_table("iso_failure_modes")
    op.drop_table("components")
    op.drop_table("subunits")
    op.drop_table("equipment_units")
    op.drop_table("systems")
    op.drop_table("facilities")
    op.drop_table("sites")
    op.drop_table("business_units")
    op.drop_table("industries")
