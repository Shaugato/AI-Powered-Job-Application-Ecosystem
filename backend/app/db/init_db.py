import json

from sqlalchemy import inspect, text

from backend.app.db.base import Base
from backend.app.db.session import engine
from backend.app.models import entities  # noqa: F401


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_lightweight_migrations()
    _backfill_nullable_defaults()


def _ensure_columns(table_name: str, additions: dict[str, str]) -> None:
    inspector = inspect(engine)
    if table_name not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    for column_name, sql in additions.items():
        if column_name in columns:
            continue
        with engine.begin() as connection:
            connection.execute(text(sql))


def _ensure_lightweight_migrations() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    if "ingestion_source_configs" in table_names:
        _ensure_columns(
            "ingestion_source_configs",
            {
                "connection_id": "ALTER TABLE ingestion_source_configs ADD COLUMN connection_id VARCHAR(36)",
            },
        )

    if "base_profiles" in table_names:
        _ensure_columns(
            "base_profiles",
            {
                "skills_json": "ALTER TABLE base_profiles ADD COLUMN skills_json JSON",
                "certifications_json": "ALTER TABLE base_profiles ADD COLUMN certifications_json JSON",
                "experience_json": "ALTER TABLE base_profiles ADD COLUMN experience_json JSON",
                "projects_json": "ALTER TABLE base_profiles ADD COLUMN projects_json JSON",
                "education_json": "ALTER TABLE base_profiles ADD COLUMN education_json JSON",
            },
        )

    if "source_assets" in table_names:
        _ensure_columns(
            "source_assets",
            {
                "page_count": "ALTER TABLE source_assets ADD COLUMN page_count INTEGER",
                "source_metadata_json": "ALTER TABLE source_assets ADD COLUMN source_metadata_json JSON",
            },
        )

    if "structured_sections" in table_names:
        _ensure_columns(
            "structured_sections",
            {
                "evidence_spans_json": "ALTER TABLE structured_sections ADD COLUMN evidence_spans_json JSON",
                "canonical_value_json": "ALTER TABLE structured_sections ADD COLUMN canonical_value_json JSON",
                "provenance_json": "ALTER TABLE structured_sections ADD COLUMN provenance_json JSON",
                "confidence_lineage_json": "ALTER TABLE structured_sections ADD COLUMN confidence_lineage_json JSON",
                "cluster_id": "ALTER TABLE structured_sections ADD COLUMN cluster_id VARCHAR(64)",
            },
        )

    if "opportunity_fits" in table_names:
        _ensure_columns(
            "opportunity_fits",
            {
                "requirement_profile_json": "ALTER TABLE opportunity_fits ADD COLUMN requirement_profile_json JSON",
                "rerank_scores_json": "ALTER TABLE opportunity_fits ADD COLUMN rerank_scores_json JSON",
            },
        )

    if "resume_composition_plans" in table_names:
        _ensure_columns(
            "resume_composition_plans",
            {
                "evidence_pack_json": "ALTER TABLE resume_composition_plans ADD COLUMN evidence_pack_json JSON",
                "layout_blueprint_json": "ALTER TABLE resume_composition_plans ADD COLUMN layout_blueprint_json JSON",
                "rendered_metrics_json": "ALTER TABLE resume_composition_plans ADD COLUMN rendered_metrics_json JSON",
                "verification_json": "ALTER TABLE resume_composition_plans ADD COLUMN verification_json JSON",
                "repair_loop_json": "ALTER TABLE resume_composition_plans ADD COLUMN repair_loop_json JSON",
            },
        )

    if "generation_results" in table_names:
        _ensure_columns(
            "generation_results",
            {
                "composition_plan_id": "ALTER TABLE generation_results ADD COLUMN composition_plan_id VARCHAR(36)",
                "preview_html_path": "ALTER TABLE generation_results ADD COLUMN preview_html_path VARCHAR(500)",
                "preview_pdf_path": "ALTER TABLE generation_results ADD COLUMN preview_pdf_path VARCHAR(500)",
                "selected_section_ids_json": "ALTER TABLE generation_results ADD COLUMN selected_section_ids_json JSON",
                "excluded_section_ids_json": "ALTER TABLE generation_results ADD COLUMN excluded_section_ids_json JSON",
                "fit_score": "ALTER TABLE generation_results ADD COLUMN fit_score FLOAT DEFAULT 0.0",
                "verifier_output_json": "ALTER TABLE generation_results ADD COLUMN verifier_output_json JSON",
                "repair_attempts_json": "ALTER TABLE generation_results ADD COLUMN repair_attempts_json JSON",
                "stage_status_json": "ALTER TABLE generation_results ADD COLUMN stage_status_json JSON",
            },
        )

    if "submission_previews" in table_names:
        _ensure_columns(
            "submission_previews",
            {
                "verification_metadata_json": "ALTER TABLE submission_previews ADD COLUMN verification_metadata_json JSON",
            },
        )

    if "application_plans" in table_names:
        _ensure_columns(
            "application_plans",
            {
                "fit_reasons_json": "ALTER TABLE application_plans ADD COLUMN fit_reasons_json JSON",
                "preview_required": "ALTER TABLE application_plans ADD COLUMN preview_required BOOLEAN DEFAULT TRUE",
                "source_policy": "ALTER TABLE application_plans ADD COLUMN source_policy VARCHAR(80) DEFAULT 'review_before_apply'",
                "fit_score": "ALTER TABLE application_plans ADD COLUMN fit_score FLOAT DEFAULT 0.0",
            },
        )

    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            try:
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            except Exception:
                pass
            try:
                connection.execute(text("ALTER TYPE sourcename ADD VALUE IF NOT EXISTS 'indeed'"))
            except Exception:
                pass


def _json_literal(value: object) -> str:
    payload = json.dumps(value)
    if engine.dialect.name == "postgresql":
        return f"'{payload}'::json"
    return f"'{payload}'"


def _backfill_nullable_defaults() -> None:
    table_names = set(inspect(engine).get_table_names())
    updates: list[str] = []

    if "generation_results" in table_names:
        updates.extend(
            [
                f"UPDATE generation_results SET resume_json = {_json_literal({})} WHERE resume_json IS NULL",
                f"UPDATE generation_results SET cover_letter_json = {_json_literal({})} WHERE cover_letter_json IS NULL",
                f"UPDATE generation_results SET qa_scores_json = {_json_literal({})} WHERE qa_scores_json IS NULL",
                f"UPDATE generation_results SET selected_section_ids_json = {_json_literal([])} WHERE selected_section_ids_json IS NULL",
                f"UPDATE generation_results SET excluded_section_ids_json = {_json_literal([])} WHERE excluded_section_ids_json IS NULL",
                f"UPDATE generation_results SET verifier_output_json = {_json_literal({})} WHERE verifier_output_json IS NULL",
                f"UPDATE generation_results SET repair_attempts_json = {_json_literal([])} WHERE repair_attempts_json IS NULL",
                f"UPDATE generation_results SET stage_status_json = {_json_literal({})} WHERE stage_status_json IS NULL",
                "UPDATE generation_results SET fit_score = 0.0 WHERE fit_score IS NULL",
            ]
        )

    if "application_plans" in table_names:
        preview_required_literal = "TRUE" if engine.dialect.name == "postgresql" else "1"
        updates.extend(
            [
                f"UPDATE application_plans SET field_map_json = {_json_literal({})} WHERE field_map_json IS NULL",
                f"UPDATE application_plans SET risk_reasons_json = {_json_literal([])} WHERE risk_reasons_json IS NULL",
                f"UPDATE application_plans SET fit_reasons_json = {_json_literal([])} WHERE fit_reasons_json IS NULL",
                f"UPDATE application_plans SET preview_required = {preview_required_literal} WHERE preview_required IS NULL",
                "UPDATE application_plans SET source_policy = 'review_before_apply' WHERE source_policy IS NULL",
                "UPDATE application_plans SET fit_score = 0.0 WHERE fit_score IS NULL",
            ]
        )

    if "submission_previews" in table_names:
        updates.append(f"UPDATE submission_previews SET verification_metadata_json = {_json_literal({})} WHERE verification_metadata_json IS NULL")

    if "application_runs" in table_names:
        updates.extend(
            [
                f"UPDATE application_runs SET execution_log_json = {_json_literal([])} WHERE execution_log_json IS NULL",
                f"UPDATE application_runs SET uploaded_artifacts_json = {_json_literal([])} WHERE uploaded_artifacts_json IS NULL",
            ]
        )

    if "source_assets" in table_names:
        updates.append(f"UPDATE source_assets SET source_metadata_json = {_json_literal({})} WHERE source_metadata_json IS NULL")

    if "structured_sections" in table_names:
        updates.extend(
            [
                f"UPDATE structured_sections SET evidence_spans_json = {_json_literal([])} WHERE evidence_spans_json IS NULL",
                f"UPDATE structured_sections SET provenance_json = {_json_literal([])} WHERE provenance_json IS NULL",
                f"UPDATE structured_sections SET confidence_lineage_json = {_json_literal([])} WHERE confidence_lineage_json IS NULL",
            ]
        )

    if "opportunity_fits" in table_names:
        updates.extend(
            [
                f"UPDATE opportunity_fits SET requirement_profile_json = {_json_literal({})} WHERE requirement_profile_json IS NULL",
                f"UPDATE opportunity_fits SET rerank_scores_json = {_json_literal([])} WHERE rerank_scores_json IS NULL",
            ]
        )

    if "resume_composition_plans" in table_names:
        updates.extend(
            [
                f"UPDATE resume_composition_plans SET evidence_pack_json = {_json_literal([])} WHERE evidence_pack_json IS NULL",
                f"UPDATE resume_composition_plans SET layout_blueprint_json = {_json_literal({})} WHERE layout_blueprint_json IS NULL",
                f"UPDATE resume_composition_plans SET rendered_metrics_json = {_json_literal({})} WHERE rendered_metrics_json IS NULL",
                f"UPDATE resume_composition_plans SET verification_json = {_json_literal({})} WHERE verification_json IS NULL",
                f"UPDATE resume_composition_plans SET repair_loop_json = {_json_literal([])} WHERE repair_loop_json IS NULL",
            ]
        )

    if "evidence_fragments" in table_names:
        updates.extend(
            [
                f"UPDATE evidence_fragments SET role_tags_json = {_json_literal([])} WHERE role_tags_json IS NULL",
                f"UPDATE evidence_fragments SET skills_json = {_json_literal([])} WHERE skills_json IS NULL",
                f"UPDATE evidence_fragments SET certifications_json = {_json_literal([])} WHERE certifications_json IS NULL",
            ]
        )

    if not updates:
        return

    with engine.begin() as connection:
        for statement in updates:
            connection.execute(text(statement))
