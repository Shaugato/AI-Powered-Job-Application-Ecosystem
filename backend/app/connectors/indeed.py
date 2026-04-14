from urllib.parse import quote_plus

from backend.app.connectors.base import SourceConnector


class IndeedConnector(SourceConnector):
    def __init__(self) -> None:
        super().__init__(
            source_name="indeed",
            auto_submit_certified=False,
            notes=[
                "Monitoring runs against public Indeed search pages.",
                "Submission remains review-gated until the account-backed adapter is hardened.",
            ],
        )

    def build_search_url(self, *, query: str, location: str | None = None, remote_policy: str | None = None, metadata: dict | None = None) -> str | None:
        metadata = metadata or {}
        if metadata.get("search_url"):
            return str(metadata["search_url"])
        params = [f"q={quote_plus(query)}"]
        if location:
            params.append(f"l={quote_plus(location)}")
        if remote_policy == "remote":
            params.append("sc=0kf%3Aattr%28DSQF7%29%3B")
        return f"https://au.indeed.com/jobs?{'&'.join(params)}"

    def discovery_selectors(self) -> dict[str, list[str]]:
        return {
            "cards": ["div.job_seen_beacon", "div[data-jk]", "li div.result"],
            "title": ["h2.jobTitle a", "a.jcs-JobTitle", "h2 a", "a[href*='/viewjob']"],
            "company": ["span.companyName", "[data-testid='company-name']", "[class*=companyName]"],
            "location": ["div.companyLocation", "[data-testid='text-location']", "[class*=companyLocation]"],
            "snippet": ["div.job-snippet", "div[data-testid='job-snippet']", "ul", "p"],
            "url": ["h2.jobTitle a", "a.jcs-JobTitle", "a[href*='/viewjob']", "a[href]"],
        }
