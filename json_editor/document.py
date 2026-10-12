"""JSON document model with type-preserving edits."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

PathKey = str | int
ValuePath = tuple[PathKey, ...]

_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$")

POSITION_KEYS = ("pos_x", "pos_y", "orientation")


class JsonDocument(QObject):
    loaded = Signal()
    saved = Signal()
    valueChanged = Signal(str, tuple, object)
    deviceReplaced = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.path: Path | None = None
        self.data: dict[str, Any] = {}
        self.saved_data: dict[str, Any] = {}

    @property
    def filename(self) -> str:
        return self.path.name if self.path else "未打开文件"

    def device_names(self) -> list[str]:
        return list(self.data.keys())

    def get_device(self, name: str) -> Any:
        return self.data.get(name)

    def load(self, path: str | Path) -> None:
        path = Path(path)
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("JSON 根节点必须是对象（器件名 → 参数）")
        self.path = path
        self.data = payload
        self.saved_data = copy.deepcopy(payload)
        self.loaded.emit()

    def save(self, path: str | Path | None = None) -> None:
        target = Path(path) if path is not None else self.path
        if target is None:
            raise ValueError("没有可保存的路径")
        with target.open("w", encoding="utf-8") as handle:
            json.dump(self.data, handle, indent=4, ensure_ascii=False)
            handle.write("\n")
        self.path = target
        self.saved_data = copy.deepcopy(self.data)
        self.saved.emit()

    def get_value(self, device: str, path: ValuePath) -> Any:
        return _get_at(self.data[device], path)

    def has_path(self, device: str, path: ValuePath) -> bool:
        if device not in self.data:
            return False
        try:
            _get_at(self.data[device], path)
            return True
        except (KeyError, IndexError, TypeError):
            return False

    def set_value(self, device: str, path: ValuePath, value: Any) -> None:
        _set_at(self.data[device], path, value)
        self.valueChanged.emit(device, path, value)

    def replace_device(self, device: str, params: Any) -> None:
        self.data[device] = params
        self.deviceReplaced.emit(device)

    def saved_value(self, device: str, path: ValuePath) -> Any:
        if device not in self.saved_data:
            return _MISSING
        try:
            return _get_at(self.saved_data[device], path)
        except (KeyError, IndexError, TypeError):
            return _MISSING

    def is_modified(self, device: str, path: ValuePath) -> bool:
        try:
            current = self.get_value(device, path)
        except (KeyError, IndexError, TypeError):
            return True
        saved = self.saved_value(device, path)
        return saved is _MISSING or current != saved


_MISSING = object()


def _get_at(node: Any, path: ValuePath) -> Any:
    current = node
    for key in path:
        current = current[key]
    return current


def _set_at(node: Any, path: ValuePath, value: Any) -> None:
    current = node
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = value


def value_to_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def coerce_text(text: str, original: Any) -> Any:
    stripped = text.strip()
    if isinstance(original, bool):
        lowered = stripped.lower()
        if lowered in ("true", "1", "yes"):
            return True
        if lowered in ("false", "0", "no"):
            return False
        return stripped
    if isinstance(original, int) and not isinstance(original, bool):
        if _INT_RE.fullmatch(stripped):
            return int(stripped)
        if _FLOAT_RE.fullmatch(stripped):
            return float(stripped)
        return stripped
    if isinstance(original, float):
        if _FLOAT_RE.fullmatch(stripped):
            return float(stripped)
        return stripped
    if original is None:
        lowered = stripped.lower()
        if lowered in ("null", ""):
            return None
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        if _INT_RE.fullmatch(stripped):
            return int(stripped)
        if _FLOAT_RE.fullmatch(stripped):
            return float(stripped)
        return stripped
    return text


def merge_device_params(target: dict, source: dict, keep_position: bool) -> dict:
    merged = copy.deepcopy(source)
    if keep_position and isinstance(target, dict):
        for key in POSITION_KEYS:
            if key in target:
                merged[key] = copy.deepcopy(target[key])
    return merged


def count_params(node: Any) -> tuple[int, int]:
    """Return (leaf_count, nested_container_count)."""
    leaves = 0
    nested = 0
    if isinstance(node, dict):
        for value in node.values():
            if isinstance(value, (dict, list)):
                nested += 1
                child_leaves, child_nested = count_params(value)
                leaves += child_leaves
                nested += child_nested
            else:
                leaves += 1
    elif isinstance(node, list):
        for value in node:
            if isinstance(value, (dict, list)):
                nested += 1
                child_leaves, child_nested = count_params(value)
                leaves += child_leaves
                nested += child_nested
            else:
                leaves += 1
    return leaves, nested
