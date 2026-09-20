from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from ..models import Opportunity
from .common import html_to_text, normalize_income_basis


@dataclass(slots=True)
class JobicyCollector:
    timeout_seconds: float = 30.0
    api_url: str = "https://jobicy.com/api/v2/remote-jobs"

    def collect(self, *, count: int = 100) -> list[Opportunity]:
        with httpx.Client(
            timeout=self.timeout_seconds,
            headers={"User-Agent": "money-agent/0.2", "Accept": "application/json"},
        ) as client:
            response = client.get(self.api_url, params={"count": min(max(count, 1), 200)})
            response.raise_for_status()
        return [self._normalize(item) for item in response.json().get("jobs", [])]

    @staticmethod
    def _normalize(item: dict[str, Any]) -> Opportunity:
        salary_min = _number_or_none(item.get("salaryMin"))
        salary_max = _number_or_none(item.get("salaryMax"))
        industries = [str(value) for value in item.get("jobIndustry") or []]
        job_types = [str(value) for value in item.get("jobType") or []]
        level = str(item.get("jobLevel") or "")
        skills = [*industries, *job_types]
        if level:
            skills.append(level)
        return Opportunity(
            source="jobicy",
            external_id=str(item["id"]),
            title=str(item.get("jobTitle") or "Untitled remote role"),
            description=html_to_text(
                str(item.get("jobDescription") or item.get("jobExcerpt") or "")
            ),
            url=str(item["url"]),
            budget_min=salary_min,
            budget_max=salary_max,
            currency=str(item.get("salaryCurrency") or "USD").upper(),
            created_at=str(item.get("pubDate") or "") or None,
            skills=skills,
            language="English",
            kind="remote_job",
            income_basis=normalize_income_basis(str(item.get("salaryPeriod") or "")),
            organization=str(item.get("companyName") or "") or None,
            location=str(item.get("jobGeo") or "") or None,
        )


def _number_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    return float(value)

