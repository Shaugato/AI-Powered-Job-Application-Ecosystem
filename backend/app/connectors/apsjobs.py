from backend.app.connectors.base import SourceConnector


class APSJobsConnector(SourceConnector):
    def __init__(self) -> None:
        super().__init__(
            source_name="apsjobs",
            auto_submit_certified=False,
            notes=[
                "Government applications are permanently review-required.",
                "Monitoring uses configured search pages or APS search result URLs.",
            ],
        )

    def build_search_url(self, *, query: str, location: str | None = None, remote_policy: str | None = None, metadata: dict | None = None) -> str | None:
        metadata = metadata or {}
        return str(metadata.get("search_url") or "").strip() or None

    def discovery_selectors(self) -> dict[str, list[str]]:
        return {
            "cards": ["article", "li.slds-item", "div.slds-card"],
            "title": ["h2 a", "h3 a", "a[href*='job-search']"],
            "company": ["[class*=agency]", "[class*=department]", "p"],
            "location": ["[class*=location]", "span.slds-text-body_small", "p"],
            "snippet": ["[class*=summary]", "p", "div.slds-text-body_regular"],
            "url": ["a[href]"],
        }
