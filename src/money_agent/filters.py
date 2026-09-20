from __future__ import annotations

from dataclasses import dataclass, field

from .models import Opportunity

DEFAULT_POSITIVE_KEYWORDS = {
    "api",
    "automation",
    "bug",
    "csv",
    "data",
    "fix",
    "html",
    "javascript",
    "json",
    "parser",
    "python",
    "scraping",
    "script",
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


@dataclass(slots=True)
class FilterDecision:
    eligible: bool
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RuleFilter:
    min_budget_usd: float = 20.0
    positive_keywords: set[str] = field(default_factory=lambda: set(DEFAULT_POSITIVE_KEYWORDS))
    excluded_keywords: set[str] = field(default_factory=lambda: set(DEFAULT_EXCLUDED_KEYWORDS))

    def evaluate(self, opportunity: Opportunity) -> FilterDecision:
        text = f"{opportunity.title}\n{opportunity.description}".lower()
        reasons: list[str] = []

        excluded = sorted(keyword for keyword in self.excluded_keywords if keyword in text)
        if excluded:
            reasons.append(f"excluded keywords: {', '.join(excluded)}")

        if opportunity.currency.upper() != "USD":
            reasons.append(f"unsupported currency: {opportunity.currency}")

        budget = opportunity.budget_max or opportunity.budget_min
        if budget is None:
            reasons.append("no explicit budget found")
        elif budget < self.min_budget_usd:
            reasons.append(f"budget below ${self.min_budget_usd:.0f}")

        positive = sorted(keyword for keyword in self.positive_keywords if keyword in text)
        if not positive:
            reasons.append("no preferred task keyword")

        return FilterDecision(eligible=not reasons, reasons=reasons)
