from types import SimpleNamespace

from backend.app.models.entities import TruthStatus
from backend.app.services.retrieval import classify_job_labels, rank_fragment


def test_classify_job_labels_handles_hybrid_roles() -> None:
    labels = classify_job_labels("Lead AWS security engineer managing IAM and SIEM", "Cloud Security Engineer")
    assert "Cloud" in labels
    assert "Security" in labels


def test_rank_fragment_rewards_role_alignment() -> None:
    job = SimpleNamespace(
        description_text="AWS Terraform Kubernetes",
        classification_labels_json=["Cloud", "DevOps"],
        title="Senior DevOps Engineer",
    )
    fragment = SimpleNamespace(
        payload_text="Built Kubernetes clusters on AWS using Terraform",
        success_weight=1.2,
        role_tags_json=["Cloud", "DevOps"],
        truth_status=TruthStatus.APPROVED,
        seniority="senior",
    )
    assert rank_fragment(job, fragment) > 0.5
