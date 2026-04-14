from urllib.parse import quote_plus

from backend.app.connectors.base import SourceConnector


class LinkedInConnector(SourceConnector):
    def __init__(self) -> None:
        super().__init__(
            source_name="linkedin",
            auto_submit_certified=False,
            notes=[
                "Prefer Easy Apply flows only.",
                "Operate conservatively because platform automation risk is high.",
            ],
        )

    def build_search_url(self, *, query: str, location: str | None = None, remote_policy: str | None = None, metadata: dict | None = None) -> str | None:
        metadata = metadata or {}
        if metadata.get("search_url"):
            return str(metadata["search_url"])
        params = [f"keywords={quote_plus(query)}"]
        if location:
            params.append(f"location={quote_plus(location)}")
        if remote_policy == "remote":
            params.append("f_WT=2")
        return f"https://www.linkedin.com/jobs/search/?{'&'.join(params)}"

    def discovery_selectors(self) -> dict[str, list[str]]:
        return {
            "cards": ["li div.base-card", "div.base-search-card", "li"],
            "title": ["h3.base-search-card__title", "h3", "a.base-card__full-link"],
            "company": ["h4.base-search-card__subtitle", "a.hidden-nested-link", "[class*=subtitle]"],
            "location": ["span.job-search-card__location", "span.base-search-card__metadata", "[class*=location]"],
            "snippet": ["p.base-search-card__metadata", "div.base-search-card__info", "p"],
            "url": ["a.base-card__full-link", "a[href*='/jobs/view/']", "a[href]"],
        }
