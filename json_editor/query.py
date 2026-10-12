"""Device-name search: substring, comma lists, and Q1-Q12 ranges."""

from __future__ import annotations

import re
from collections.abc import Callable

_RANGE = re.compile(
    r"^([A-Za-z_]*)(\d+)\s*-\s*([A-Za-z_]*)(\d+)$",
    re.IGNORECASE,
)


def device_matches(name: str, query: str) -> bool:
    matcher = compile_query(query)
    return matcher(name)


def compile_query(query: str) -> Callable[[str], bool]:
    text = query.strip()
    if not text:
        return lambda _name: True
    tokens = [token.strip() for token in text.split(",") if token.strip()]
    if not tokens:
        return lambda _name: True
    matchers = [_token_matcher(token) for token in tokens]
    return lambda name: any(match(name) for match in matchers)


def _token_matcher(token: str) -> Callable[[str], bool]:
    compact = re.sub(r"\s+", "", token)
    ranged = _RANGE.fullmatch(compact)
    if ranged:
        prefix_a, start_s, prefix_b, end_s = ranged.groups()
        prefix = prefix_a or prefix_b
        lo, hi = sorted((int(start_s), int(end_s)))
        if prefix:
            pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$", re.IGNORECASE)

            def match_prefixed(name: str) -> bool:
                hit = pattern.fullmatch(name)
                return hit is not None and lo <= int(hit.group(1)) <= hi

            return match_prefixed

        def match_index(name: str) -> bool:
            hit = re.search(r"(\d+)$", name)
            return hit is not None and lo <= int(hit.group(1)) <= hi

        return match_index

    needle = token.lower()
    return lambda name: needle in name.lower()
