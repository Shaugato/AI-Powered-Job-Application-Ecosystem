from __future__ import annotations

from dataclasses import dataclass

from backend.app.connectors.apsjobs import APSJobsConnector
from backend.app.connectors.base import SourceConnector
from backend.app.connectors.careers_vic import CareersVicConnector
from backend.app.connectors.company_portal import CompanyPortalConnector
from backend.app.connectors.indeed import IndeedConnector
from backend.app.connectors.linkedin import LinkedInConnector
from backend.app.connectors.seek import SeekConnector


@dataclass
class SourceRegistry:
    connectors: dict[str, SourceConnector]

    @classmethod
    def default(cls) -> "SourceRegistry":
        connectors = {
            "seek": SeekConnector(),
            "linkedin": LinkedInConnector(),
            "indeed": IndeedConnector(),
            "apsjobs": APSJobsConnector(),
            "careers_vic": CareersVicConnector(),
            "company_portal": CompanyPortalConnector(),
        }
        return cls(connectors=connectors)

    def get(self, source_name: str) -> SourceConnector:
        return self.connectors[source_name]
