from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if value:
            self.parts.append(value)


def html_to_text(value: str | None) -> str:
    parser = _TextExtractor()
    parser.feed(value or "")
    return unescape(" ".join(parser.parts))


CURRENCY_AMOUNT = re.compile(
    r"(?:USD\s*|\$)\s*(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*([kK])?",
    re.IGNORECASE,
)


def parse_usd_salary(value: str | None) -> tuple[float | None, float | None]:
    if not value or not any(marker in value.upper() for marker in ("$", "USD")):
        return None, None
    amounts: list[float] = []
    for raw, suffix in CURRENCY_AMOUNT.findall(value):
        number = float(raw.replace(",", ""))
        if suffix:
            number *= 1_000
        amounts.append(number)
    if not amounts:
        return None, None
    return min(amounts), max(amounts)


def normalize_income_basis(value: str | None) -> str:
    lowered = (value or "").lower()
    if "hour" in lowered:
        return "hourly"
    if "week" in lowered:
        return "weekly"
    if "month" in lowered:
        return "monthly"
    if any(marker in lowered for marker in ("year", "annual", "annum")):
        return "annual"
    return "unknown"
