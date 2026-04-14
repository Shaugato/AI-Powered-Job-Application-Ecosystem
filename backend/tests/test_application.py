from backend.app.models.entities import ApplicationMode
from backend.app.services.application import plan_mode_for_job


def test_government_portals_require_review() -> None:
    mode, reasons = plan_mode_for_job(source="apsjobs", risk_flags=[], auto_submit_certified=True)
    assert mode == ApplicationMode.REVIEW_REQUIRED
    assert reasons


def test_certified_low_risk_flow_can_auto_submit() -> None:
    mode, reasons = plan_mode_for_job(source="company_portal", risk_flags=[], auto_submit_certified=True)
    assert mode == ApplicationMode.AUTO_SUBMIT
    assert reasons == []
