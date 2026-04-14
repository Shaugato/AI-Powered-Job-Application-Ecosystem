from backend.app.models.entities import FragmentType
from backend.app.services.corpus import chunk_text_to_fragments, infer_role_tags


def test_chunk_text_to_fragments() -> None:
    text = """DevOps Engineer

- Built CI/CD pipelines
- Managed Terraform

AWS Certified Solutions Architect
"""
    fragments = chunk_text_to_fragments(text)
    assert len(fragments) == 3
    assert fragments[0].fragment_type == FragmentType.SKILL


def test_infer_role_tags() -> None:
    tags = infer_role_tags("Implemented AWS infrastructure and Kubernetes automation")
    assert "Cloud" in tags
    assert "DevOps" in tags
