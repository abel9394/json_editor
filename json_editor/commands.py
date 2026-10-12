"""Undo commands for parameter and device edits."""

from __future__ import annotations

import copy
from typing import Any

from PySide6.QtGui import QUndoCommand

from .document import JsonDocument, ValuePath


class SetValueCommand(QUndoCommand):
    def __init__(
        self,
        document: JsonDocument,
        device: str,
        path: ValuePath,
        old_value: Any,
        new_value: Any,
    ) -> None:
        super().__init__(f"修改 {device} / {'/'.join(str(p) for p in path)}")
        self.document = document
        self.device = device
        self.path = path
        self.old_value = copy.deepcopy(old_value)
        self.new_value = copy.deepcopy(new_value)

    def redo(self) -> None:
        self.document.set_value(self.device, self.path, copy.deepcopy(self.new_value))

    def undo(self) -> None:
        self.document.set_value(self.device, self.path, copy.deepcopy(self.old_value))


class ReplaceDevicesCommand(QUndoCommand):
    def __init__(
        self,
        document: JsonDocument,
        replacements: dict[str, tuple[Any, Any]],
        description: str = "粘贴器件参数",
    ) -> None:
        super().__init__(description)
        self.document = document
        self.replacements = {
            name: (copy.deepcopy(old), copy.deepcopy(new))
            for name, (old, new) in replacements.items()
        }

    def redo(self) -> None:
        for name, (_old, new) in self.replacements.items():
            self.document.replace_device(name, copy.deepcopy(new))

    def undo(self) -> None:
        for name, (old, _new) in self.replacements.items():
            self.document.replace_device(name, copy.deepcopy(old))


class MergeOptionsCommand(QUndoCommand):
    """Write one option onto many devices in a single undo step."""

    def __init__(
        self,
        document: JsonDocument,
        changes: list[tuple[str, ValuePath, Any, Any]],
        description: str = "批量修改参数",
    ) -> None:
        super().__init__(description)
        self.document = document
        self.changes = [
            (device, path, copy.deepcopy(old), copy.deepcopy(new))
            for device, path, old, new in changes
        ]

    def redo(self) -> None:
        for device, path, _old, new in self.changes:
            self.document.set_value(device, path, copy.deepcopy(new))

    def undo(self) -> None:
        for device, path, old, _new in self.changes:
            self.document.set_value(device, path, copy.deepcopy(old))


class PasteCellsCommand(QUndoCommand):
    def __init__(
        self,
        document: JsonDocument,
        device: str,
        changes: list[tuple[ValuePath, Any, Any]],
    ) -> None:
        super().__init__(f"粘贴 {len(changes)} 个参数")
        self.document = document
        self.device = device
        self.changes = [
            (path, copy.deepcopy(old), copy.deepcopy(new)) for path, old, new in changes
        ]

    def redo(self) -> None:
        for path, _old, new in self.changes:
            self.document.set_value(self.device, path, copy.deepcopy(new))

    def undo(self) -> None:
        for path, old, _new in self.changes:
            self.document.set_value(self.device, path, copy.deepcopy(old))
