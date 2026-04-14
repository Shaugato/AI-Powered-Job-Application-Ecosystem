from backend.app.services.dedupe import are_near_duplicates, fingerprint_job, normalize_text


def test_normalize_text_strips_urls_and_punctuation() -> None:
    normalized = normalize_text("AWS Engineer! https://example.com/apply")
    assert normalized == "aws engineer"


def test_detects_near_duplicates() -> None:
    left = "Senior AWS engineer building Terraform infrastructure and Kubernetes clusters."
    right = "Senior AWS Engineer building Terraform infrastructure plus Kubernetes clusters"
    assert are_near_duplicates(left, right)


def test_fingerprint_changes_for_distinct_roles() -> None:
    a = fingerprint_job("Example", "DevOps Engineer", "Build Terraform pipelines")
    b = fingerprint_job("Example", "Network Engineer", "Manage firewalls and routing")
    assert a != b
