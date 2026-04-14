from urllib.parse import quote_plus

from backend.app.connectors.base import SourceConnector


class SeekConnector(SourceConnector):
    def __init__(self) -> None:
        super().__init__(
            source_name="seek",
            auto_submit_certified=False,
            notes=[
                "Monitoring runs against configured search pages.",
                "Submission remains review-gated until adapter certification is complete.",
            ],
        )

    def build_search_url(self, *, query: str, location: str | None = None, remote_policy: str | None = None, metadata: dict | None = None) -> str | None:
        metadata = metadata or {}
        if metadata.get("search_url"):
            return str(metadata["search_url"])
        params = [f"keywords={quote_plus(query)}"]
        if location:
            params.append(f"where={quote_plus(location)}")
        if remote_policy == "remote":
            params.append("worktype=244%2C243")
        return f"https://www.seek.com.au/jobs?{'&'.join(params)}"

    def discovery_selectors(self) -> dict[str, list[str]]:
        return {
            "cards": ["article[data-automation*=job]", "article", "div[data-automation*=job-card]"],
            "title": ["a[data-automation*=jobTitle]", "h3 a", "h3"],
            "company": ["a[data-automation*=jobCompany]", "span[data-automation*=jobCompany]", "[data-automation*=company]"],
            "location": ["a[data-automation*=jobLocation]", "span[data-automation*=jobLocation]", "[data-automation*=location]"],
            "snippet": ["span[data-automation*=jobShortDescription]", "p", "[data-automation*=jobDescription]"],
            "url": ["a[href*='/job/']", "h3 a", "a[href]"],
        }
