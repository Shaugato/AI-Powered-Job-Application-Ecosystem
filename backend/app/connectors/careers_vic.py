from backend.app.connectors.base import SourceConnector


class CareersVicConnector(SourceConnector):
    def __init__(self) -> None:
        super().__init__(
            source_name="careers_vic",
            auto_submit_certified=False,
            notes=[
                "Government-style workflows remain review-required.",
                "Monitoring uses configured search result URLs for Victorian public sector roles.",
            ],
        )

    def build_search_url(self, *, query: str, location: str | None = None, remote_policy: str | None = None, metadata: dict | None = None) -> str | None:
        metadata = metadata or {}
        return str(metadata.get("search_url") or "").strip() or None

    def discovery_selectors(self) -> dict[str, list[str]]:
        return {
            "cards": ["article", "li", "div.job-card"],
            "title": ["h2 a", "h3 a", "a[href*='/job/']"],
            "company": ["[class*=organisation]", "[class*=department]", "p"],
            "location": ["[class*=location]", "span", "p"],
            "snippet": ["[class*=summary]", "p", "div"],
            "url": ["a[href]"],
        }
