from __future__ import annotations

from dataclasses import dataclass, field

from .models import Opportunity

DEFAULT_POSITIVE_KEYWORDS = {
    "api",
    "automation",
    "bug",
    "csv",
    "data",
    "design",
    "editing",
    "fix",
    "html",
    "javascript",
    "json",
    "marketing",
    "parser",
    "python",
    "scraping",
    "script",
    "support",
    "translation",
    "writing",
}
DEFAULT_EXCLUDED_KEYWORDS = {
    "bounty proposal",
    "captcha",
    "manual verification",
    "meeting required",
    "on-site",
    "phone call",
    "physical work",
    "proposed bounty",
}
DEFAULT_REMOTE_REGIONS = {
    "anywhere",
    "worldwide",
    "global",
    "apac",
    "asia",
    "south korea",
    "korea",
}
DEFAULT_EXCLUDED_SENIORITY = {
    "director",
    "head of",
    "lead ",
    "manager",
    "principal",
    "senior",
    "staff ",
    "vice president",
    "vp ",
}


@dataclass(slots=True)
class FilterDecision:
    eligible: bool
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RuleFilter:
    min_budget_usd: float = 20.0
    positive_keywords: set[str] = field(default_factory=lambda: set(DEFAULT_POSITIVE_KEYWORDS))
    excluded_keywords: set[str] = field(default_factory=lambda: set(DEFAULT_EXCLUDED_KEYWORDS))
    remote_regions: set[str] = field(default_factory=lambda: set(DEFAULT_REMOTE_REGIONS))
    excluded_seniority: set[str] = field(
        default_factory=lambda: set(DEFAULT_EXCLUDED_SENIORITY)
    )

    def evaluate(self, opportunity: Opportunity) -> FilterDecision:
        text = f"{opportunity.title}\n{opportunity.description}".lower()
        reasons: list[str] = []

        excluded = sorted(keyword for keyword in self.excluded_keywords if keyword in text)
        if excluded:
            reasons.append(f"excluded keywords: {', '.join(excluded)}")
        title = opportunity.title.lower()
        if "proposed" in title and "bounty" in title:
            reasons.append("unfunded proposed bounty")

        has_budget = opportunity.budget_min is not None or opportunity.budget_max is not None
        if has_budget and opportunity.currency.upper() != "USD":
            reasons.append(f"unsupported currency: {opportunity.currency}")

        budget = opportunity.budget_max or opportunity.budget_min
        if budget is None and opportunity.kind != "remote_job":
            reasons.append("no explicit budget found")
        elif (
            budget is not None
            and opportunity.income_basis == "one_time"
            and budget < self.min_budget_usd
        ):
            reasons.append(f"budget below ${self.min_budget_usd:.0f}")

        if opportunity.kind == "remote_job":
            location = (opportunity.location or "").lower()
            if location and not any(region in location for region in self.remote_regions):
                reasons.append(f"location not available from Korea: {opportunity.location}")
            seniority = sorted(
                marker.strip() for marker in self.excluded_seniority if marker in title
            )
            if seniority:
                reasons.append(f"seniority too high: {', '.join(seniority)}")
        else:
            positive = sorted(keyword for keyword in self.positive_keywords if keyword in text)
            if not positive:
                reasons.append("no preferred task keyword")

        return FilterDecision(eligible=not reasons, reasons=reasons)
