from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from ..models import Opportunity
from .common import html_to_text, normalize_income_basis, parse_usd_salary


@dataclass(slots=True)
class RemotiveCollector:
    timeout_seconds: float = 30.0
    api_url: str = "https://remotive.com/api/remote-jobs"

    def collect(self) -> list[Opportunity]:
        with httpx.Client(
            timeout=self.timeout_seconds,
            headers={"User-Agent": "money-agent/0.2", "Accept": "application/json"},
        ) as client:
            response = client.get(self.api_url)
            response.raise_for_status()
        return [self._normalize(item) for item in response.json().get("jobs", [])]

    @staticmethod
    def _normalize(item: dict[str, Any]) -> Opportunity:
        salary_text = str(item.get("salary") or "")
        salary_min, salary_max = parse_usd_salary(salary_text)
        income_basis = normalize_income_basis(salary_text)
        if income_basis == "unknown" and salary_min is not None:
            income_basis = "annual"
        category = str(item.get("category") or "")
        job_type = str(item.get("job_type") or "")
        tags = [str(value) for value in item.get("tags") or []]
        skills = [value for value in (category, job_type, *tags) if value]
        return Opportunity(
            source="remotive",
            external_id=str(item["id"]),
            title=str(item.get("title") or "Untitled remote role"),
            description=html_to_text(str(item.get("description") or "")),
            url=str(item["url"]),
            budget_min=salary_min,
            budget_max=salary_max,
            currency="USD",
            created_at=str(item.get("publication_date") or "") or None,
            skills=skills,
            language="English",
            kind="remote_job",
            income_basis=income_basis,
            organization=str(item.get("company_name") or "") or None,
            location=str(item.get("candidate_required_location") or "") or None,
        )
