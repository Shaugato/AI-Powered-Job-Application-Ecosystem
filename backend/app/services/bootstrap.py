from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal
from backend.app.models.entities import PromptVersion, RoleTaxonomy, TemplateVariant

DEFAULT_ROLES = [
    ("DevOps", 1.0, ["platform engineer", "sre"]),
    ("Cloud", 1.0, ["aws", "azure", "gcp"]),
    ("Networking", 0.9, ["network engineer", "ccna"]),
    ("Security", 0.9, ["soc", "siem", "secops"]),
    ("IT Support", 0.8, ["service desk", "desktop support"]),
    ("Infrastructure", 0.8, ["systems engineer", "server admin"]),
]

DEFAULT_PROMPT = """You are tailoring a factual job application.
- Use only the supplied evidence fragments.
- Do not invent skills, titles, dates, or certifications.
- Reuse the user's tone when possible.
- Prioritize ATS keyword coverage without stuffing.
- Return only the requested JSON schema."""

DEFAULT_TEMPLATES = [
    ("default-resume", "resume", "backend/app/templates/resume.tex.j2"),
    ("default-cover-letter", "cover_letter", "backend/app/templates/cover_letter.tex.j2"),
]


def bootstrap_defaults() -> None:
    with SessionLocal() as db:
        _seed_roles(db)
        _seed_prompt(db)
        _seed_templates(db)


def _seed_roles(db: Session) -> None:
    if db.query(RoleTaxonomy).count():
        return
    for domain_name, weight, aliases in DEFAULT_ROLES:
        db.add(RoleTaxonomy(domain_name=domain_name, priority_weight=weight, aliases_json=aliases))
    db.commit()


def _seed_prompt(db: Session) -> None:
    if db.query(PromptVersion).count():
        return
    db.add(
        PromptVersion(
            name="default-grounded-generator",
            role_tags_json=[],
            prompt_text=DEFAULT_PROMPT,
            temperature=0.1,
        )
    )
    db.commit()


def _seed_templates(db: Session) -> None:
    existing = {row.name for row in db.query(TemplateVariant).all()}
    for name, kind, path in DEFAULT_TEMPLATES:
        if name in existing:
            continue
        db.add(TemplateVariant(name=name, document_kind=kind, template_path=path))
    db.commit()
