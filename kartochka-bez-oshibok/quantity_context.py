"""Shared conservative guards: an offer or price is not a package count."""
import re

CAUTION = re.compile(
    r"\b(?:не|до|от|около|примерно|более|менее)\b|[±+–—]|\d\s*-\s*\d"
    r"|\b(?:подар\w*|бонус\w*|цен[аыуе]|стоимость|зака[зж]\w*|покуп\w*|скидк\w*)\b",
    re.I,
)
