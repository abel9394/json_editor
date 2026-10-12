"""FlipChip-style row/column windows for Q / R / tc_ names.

Numbering matches FlipChip(row, column): Q1 is top-left, row-major,
1-based inclusive ranges like coupler_names_in_range((1, 10), (1, 6)).
"""

from __future__ import annotations

import re

_QUBIT = re.compile(r"^Q(\d+)$", re.IGNORECASE)
_RESONATOR = re.compile(r"^R(\d+)$", re.IGNORECASE)
_COUPLER_QS = re.compile(r"Q(\d+)", re.IGNORECASE)

PREFERRED_COLS = (6, 7, 8, 5, 10, 12, 4, 9, 3)


def qubit_rc(index: int, n_col: int) -> tuple[int, int]:
    """1-based (row, col) from 1-based qubit index."""
    cols = max(int(n_col), 1)
    row = (int(index) - 1) // cols + 1
    col = (int(index) - 1) % cols + 1
    return row, col


def in_window(index: int, n_col: int, rows: tuple[int, int], cols: tuple[int, int]) -> bool:
    row, col = qubit_rc(index, n_col)
    r1, r2 = sorted((int(rows[0]), int(rows[1])))
    c1, c2 = sorted((int(cols[0]), int(cols[1])))
    return r1 <= row <= r2 and c1 <= col <= c2


def qubit_count(names: list[str]) -> int:
    indices = [_QUBIT.fullmatch(name) for name in names]
    values = [int(match.group(1)) for match in indices if match]
    return max(values) if values else 0


def infer_grid(n_qubits: int, n_col_hint: int | None = None) -> tuple[int, int]:
    count = max(int(n_qubits), 0)
    if count <= 0:
        return 1, 1
    if n_col_hint and n_col_hint > 0 and count % n_col_hint == 0:
        return count // n_col_hint, n_col_hint
    for cols in PREFERRED_COLS:
        if count % cols == 0:
            return count // cols, cols
    return 1, count


def qubits_in_range(
    names: list[str],
    n_col: int,
    rows: tuple[int, int],
    cols: tuple[int, int],
) -> list[str]:
    found = []
    for name in names:
        match = _QUBIT.fullmatch(name)
        if match and in_window(int(match.group(1)), n_col, rows, cols):
            found.append(name)
    return sorted(found, key=lambda item: int(_QUBIT.fullmatch(item).group(1)))


def resonators_in_range(
    names: list[str],
    n_col: int,
    rows: tuple[int, int],
    cols: tuple[int, int],
) -> list[str]:
    found = []
    for name in names:
        match = _RESONATOR.fullmatch(name)
        if match and in_window(int(match.group(1)), n_col, rows, cols):
            found.append(name)
    return sorted(found, key=lambda item: int(_RESONATOR.fullmatch(item).group(1)))


def couplers_in_range(
    names: list[str],
    n_col: int,
    rows: tuple[int, int],
    cols: tuple[int, int],
) -> list[str]:
    found = []
    for name in names:
        if not name.lower().startswith("tc_"):
            continue
        qubits = [int(hit) for hit in _COUPLER_QS.findall(name)]
        if not qubits:
            continue
        dummy = "dummy" in name.lower()
        if dummy:
            ok = in_window(qubits[0], n_col, rows, cols)
        else:
            ok = all(in_window(index, n_col, rows, cols) for index in qubits)
        if ok:
            found.append(name)
    return found


def names_in_range(
    names: list[str],
    kind: str,
    n_col: int,
    rows: tuple[int, int],
    cols: tuple[int, int],
) -> list[str]:
    key = kind.lower()
    if key in ("qubit", "q", "比特"):
        return qubits_in_range(names, n_col, rows, cols)
    if key in ("resonator", "r", "谐振腔"):
        return resonators_in_range(names, n_col, rows, cols)
    return couplers_in_range(names, n_col, rows, cols)
