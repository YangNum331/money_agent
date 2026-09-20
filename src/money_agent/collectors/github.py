from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from ..models import Opportunity

MONEY_PATTERN = re.compile(
    r"(?:(?:USD|US\$|\$)\s?)(\d{1,6}(?:[,.]\d{1,2})?)|"
    r"(\d{1,6}(?:[,.]\d{1,2})?)\s?(?:USD|US dollars?)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class GitHubCollector:
    token: str | None = None
    min_repository_stars: int = 10
    min_repository_age_days: int = 180
    max_repo_exclusions_per_query: int = 2
    timeout_seconds: float = 30.0
    api_url: str = "https://api.github.com"

    def collect(self, *, queries: list[str], per_query: int = 30) -> list[Opportunity]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "money-agent/0.1",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        found: dict[str, Opportunity] = {}
        repository_cache: dict[str, bool] = {}
        with httpx.Client(headers=headers, timeout=self.timeout_seconds) as client:
            for query in queries:
                exclusions: list[str] = []
                accepted_for_query = 0
                while accepted_for_query < per_query:
                    qualified_query = " ".join(
                        [query, "is:issue is:open", *exclusions]
                    )
                    response = client.get(
                        f"{self.api_url.rstrip('/')}/search/issues",
                        params={"q": qualified_query, "per_page": min(max(per_query, 10), 100)},
                    )
                    response.raise_for_status()
                    new_exclusions: list[str] = []
                    for item in response.json().get("items", []):
                        repository_url = item.get("repository_url")
                        if not repository_url:
                            continue
                        if repository_url not in repository_cache:
                            repository_cache[repository_url] = self._repository_is_credible(
                                client, repository_url
                            )
                        if not repository_cache[repository_url]:
                            qualifier = f"-repo:{_repository_name(repository_url)}"
                            if qualifier not in exclusions and qualifier not in new_exclusions:
                                new_exclusions.append(qualifier)
                            continue
                        opportunity = self._normalize(item)
                        if opportunity.budget_max is not None:
                            was_new = opportunity.external_id not in found
                            found[opportunity.external_id] = opportunity
                            accepted_for_query += int(was_new)
                    remaining = self.max_repo_exclusions_per_query - len(exclusions)
                    additions = new_exclusions[: max(remaining, 0)]
                    if not additions or len(exclusions) >= self.max_repo_exclusions_per_query:
                        break
                    exclusions.extend(additions)
        return list(found.values())

    def _repository_is_credible(self, client: httpx.Client, repository_url: str) -> bool:
        response = client.get(repository_url)
        response.raise_for_status()
        repository = response.json()
        if repository.get("fork", False) or repository.get("archived", False):
            return False
        if int(repository.get("stargazers_count", 0)) < self.min_repository_stars:
            return False
        created_at = repository.get("created_at")
        if not created_at:
            return False
        created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        age_days = (datetime.now(UTC) - created).days
        return age_days >= self.min_repository_age_days

    @staticmethod
    def _normalize(item: dict[str, Any]) -> Opportunity:
        body = item.get("body") or ""
        title = item.get("title") or ""
        amounts = extract_usd_amounts(f"{title}\n{body}")
        labels = [label["name"] for label in item.get("labels", []) if "name" in label]
        return Opportunity(
            source="github",
            external_id=str(item["id"]),
            title=title,
            description=body,
            url=item["html_url"],
            budget_min=min(amounts) if amounts else None,
            budget_max=max(amounts) if amounts else None,
            currency="USD",
            created_at=item.get("created_at"),
            skills=labels,
            language="English",
        )


def extract_usd_amounts(text: str) -> list[float]:
    values: list[float] = []
    for match in MONEY_PATTERN.finditer(text):
        raw = match.group(1) or match.group(2)
        if raw:
            values.append(float(raw.replace(",", "")))
    return values


def _repository_name(repository_url: str) -> str:
    marker = "/repos/"
    if marker not in repository_url:
        raise ValueError(f"Unexpected GitHub repository URL: {repository_url}")
    return repository_url.split(marker, 1)[1].strip("/")
