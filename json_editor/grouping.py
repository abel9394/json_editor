"""Group quantum-chip device names by prefix."""

from __future__ import annotations

import re
from collections import defaultdict

_KNOWN_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^Q\d+$", re.IGNORECASE), "Qubit"),
    (re.compile(r"^R\d+$", re.IGNORECASE), "Resonator"),
    (re.compile(r"^C\d+$", re.IGNORECASE), "Coupler"),
    (re.compile(r"^coupler", re.IGNORECASE), "Coupler"),
    (re.compile(r"^tc_", re.IGNORECASE), "Coupler"),
    (re.compile(r"^purcell", re.IGNORECASE), "Purcell"),
    (re.compile(r"^launch", re.IGNORECASE), "Launchpad"),
    (re.compile(r"^readout", re.IGNORECASE), "Readout"),
]

PREFERRED_ORDER = [
    "Qubit",
    "Resonator",
    "Coupler",
    "Purcell",
    "Readout",
    "Launchpad",
]

GROUP_COLORS = {
    "Qubit": "#3d9cf0",
    "Resonator": "#2ee6a6",
    "Coupler": "#fbbf24",
    "Purcell": "#c084fc",
    "Readout": "#f472b6",
    "Launchpad": "#fb923c",
    "Other": "#8b9cb3",
}

_NATURAL_SPLIT = re.compile(r"(\d+)")
_PREFIX = re.compile(r"^([A-Za-z]+(?:_[A-Za-z]+)*)")


def group_of(name: str) -> str:
    for pattern, label in _KNOWN_RULES:
        if pattern.search(name):
            return label
    match = _PREFIX.match(name)
    if match:
        return match.group(1).replace("_", " ").title()
    return "Other"


def group_color(label: str) -> str:
    return GROUP_COLORS.get(label, GROUP_COLORS["Other"])


def natural_key(name: str) -> list:
    parts: list = []
    for token in _NATURAL_SPLIT.split(name):
        if token.isdigit():
            parts.append(int(token))
        else:
            parts.append(token.lower())
    return parts


def group_devices(names: list[str]) -> list[tuple[str, list[str]]]:
    buckets: dict[str, list[str]] = defaultdict(list)
    for name in names:
        buckets[group_of(name)].append(name)

    preferred = [label for label in PREFERRED_ORDER if label in buckets]
    rest = sorted(label for label in buckets if label not in PREFERRED_ORDER)
    ordered: list[tuple[str, list[str]]] = []
    for label in preferred + rest:
        ordered.append((label, sorted(buckets[label], key=natural_key)))
    return ordered
