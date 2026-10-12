"""Editable nested parameter tree."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QWidget,
)

from ..document import ValuePath, value_to_text

ROLE_PATH = Qt.ItemDataRole.UserRole
ROLE_LEAF = Qt.ItemDataRole.UserRole + 1

MODIFIED_COLOR = QColor("#f0b429")
NORMAL_COLOR = QColor("#e8eef4")
KEY_COLOR = QColor("#b7c5d6")
CONTAINER_COLOR = QColor("#8b9cb3")


class ParamTreeWidget(QTreeWidget):
    valueCommitted = Signal(tuple, str)
    copyRequested = Signal()
    pasteRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.device: str | None = None
        self._syncing = False
        self._document = None
        self._filter_query = ""
        self.setColumnCount(2)
        self.setHeaderLabels(["参数", "值"])
        self.setAlternatingRowColors(True)
        self.setRootIsDecorated(True)
        self.setUniformRowHeights(True)
        self.setAnimated(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        header = self.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(True)
        self.itemChanged.connect(self._on_item_changed)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._open_menu)

    def set_document(self, document) -> None:
        self._document = document

    def load_device(self, name: str | None, params: Any) -> None:
        self.device = name
        expanded = self._expanded_paths()
        self._syncing = True
        self.clear()
        if name is None or params is None:
            self._syncing = False
            return
        if isinstance(params, dict):
            for key, value in params.items():
                self._add_node(self.invisibleRootItem(), (key,), key, value)
        else:
            self._add_node(self.invisibleRootItem(), tuple(), name, params)
        self._restore_expanded(expanded)
        if not expanded:
            self.expandToDepth(0)
        self._syncing = False
        self.refresh_modified()
        self.apply_filter(self._filter_query)

    def leaf_items(self) -> list[QTreeWidgetItem]:
        items: list[QTreeWidgetItem] = []
        iterator = QTreeWidgetItemIterator(self)
        while iterator.value():
            item = iterator.value()
            if item.data(0, ROLE_LEAF):
                items.append(item)
            iterator += 1
        return items

    def selected_leaf_items(self) -> list[QTreeWidgetItem]:
        return [item for item in self.selectedItems() if item.data(0, ROLE_LEAF)]

    def has_leaf_selection(self) -> bool:
        return bool(self.selected_leaf_items())

    def copy_text(self) -> str:
        leaves = self.selected_leaf_items()
        if not leaves:
            leaves = self.leaf_items() if self.currentItem() is None else []
            current = self.currentItem()
            if current is not None and current.data(0, ROLE_LEAF):
                leaves = [current]
        return "\t".join(item.text(1) for item in leaves)

    def selected_paths(self) -> list[ValuePath]:
        return [tuple(item.data(0, ROLE_PATH)) for item in self.selected_leaf_items()]

    def current_options(self) -> list[tuple[ValuePath, str]]:
        leaves = self.selected_leaf_items()
        if not leaves:
            current = self.currentItem()
            if current is not None and current.data(0, ROLE_LEAF):
                leaves = [current]
        options: list[tuple[ValuePath, str]] = []
        for item in leaves:
            path = tuple(item.data(0, ROLE_PATH) or ())
            if path:
                options.append((path, item.text(1)))
        return options

    def current_option(self) -> tuple[ValuePath, str] | None:
        options = self.current_options()
        return options[0] if options else None

    def apply_filter(self, query: str) -> None:
        self._filter_query = query or ""
        needle = self._filter_query.strip().lower()
        for i in range(self.topLevelItemCount()):
            self._filter_item(self.topLevelItem(i), needle, ancestor_matched=False)

    def update_value(self, path: ValuePath, value: Any) -> None:
        item = self._find_item(path)
        if item is None:
            return
        self._syncing = True
        item.setText(1, value_to_text(value))
        self._syncing = False
        self._paint_item(item)

    def refresh_modified(self) -> None:
        if self._document is None or self.device is None:
            return
        for item in self.leaf_items():
            self._paint_item(item)

    def _add_node(self, parent: QTreeWidgetItem, path: ValuePath, label: str, value: Any) -> None:
        item = QTreeWidgetItem()
        item.setText(0, str(label))
        item.setData(0, ROLE_PATH, path)
        item.setFont(0, self._key_font())
        item.setForeground(0, QBrush(KEY_COLOR))
        if isinstance(value, dict):
            item.setData(0, ROLE_LEAF, False)
            item.setText(1, f"{{ {len(value)} }}")
            item.setForeground(1, QBrush(CONTAINER_COLOR))
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            parent.addChild(item)
            for key, child in value.items():
                self._add_node(item, path + (key,), str(key), child)
        elif isinstance(value, list):
            item.setData(0, ROLE_LEAF, False)
            item.setText(1, f"[ {len(value)} ]")
            item.setForeground(1, QBrush(CONTAINER_COLOR))
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            parent.addChild(item)
            for index, child in enumerate(value):
                self._add_node(item, path + (index,), f"[{index}]", child)
        else:
            item.setData(0, ROLE_LEAF, True)
            item.setText(1, value_to_text(value))
            item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsEditable
            )
            parent.addChild(item)

    def _key_font(self) -> QFont:
        font = QFont(self.font())
        font.setWeight(QFont.Weight.DemiBold)
        return font

    def _item_matches(self, item: QTreeWidgetItem, needle: str) -> bool:
        if not needle:
            return True
        if needle in item.text(0).lower():
            return True
        path = item.data(0, ROLE_PATH) or ()
        joined = "/".join(str(part) for part in path).lower()
        return needle in joined

    def _filter_item(self, item: QTreeWidgetItem, needle: str, ancestor_matched: bool) -> bool:
        self_match = (not needle) or self._item_matches(item, needle)
        force = ancestor_matched or self_match
        child_visible = False
        for i in range(item.childCount()):
            child_visible = (
                self._filter_item(item.child(i), needle, force) or child_visible
            )
        visible = (not needle) or force or child_visible
        item.setHidden(not visible)
        if needle and visible and item.childCount() > 0:
            item.setExpanded(True)
        return visible

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._syncing or column != 1 or not item.data(0, ROLE_LEAF):
            return
        path = tuple(item.data(0, ROLE_PATH) or ())
        self.valueCommitted.emit(path, item.text(1))

    def _find_item(self, path: ValuePath) -> QTreeWidgetItem | None:
        iterator = QTreeWidgetItemIterator(self)
        while iterator.value():
            item = iterator.value()
            stored = item.data(0, ROLE_PATH)
            if stored is not None and tuple(stored) == tuple(path):
                return item
            iterator += 1
        return None

    def _paint_item(self, item: QTreeWidgetItem) -> None:
        if self._document is None or self.device is None:
            return
        path = tuple(item.data(0, ROLE_PATH) or ())
        if self._document.is_modified(self.device, path):
            item.setForeground(1, QBrush(MODIFIED_COLOR))
            item.setToolTip(1, "已修改，尚未保存")
        else:
            item.setForeground(1, QBrush(NORMAL_COLOR))
            item.setToolTip(1, "")

    def _expanded_paths(self) -> set[tuple]:
        paths: set[tuple] = set()
        iterator = QTreeWidgetItemIterator(self)
        while iterator.value():
            item = iterator.value()
            if item.isExpanded():
                stored = item.data(0, ROLE_PATH)
                if stored is not None:
                    paths.add(tuple(stored))
            iterator += 1
        return paths

    def _restore_expanded(self, paths: set[tuple]) -> None:
        iterator = QTreeWidgetItemIterator(self)
        while iterator.value():
            item = iterator.value()
            stored = item.data(0, ROLE_PATH)
            if stored is not None and tuple(stored) in paths:
                item.setExpanded(True)
            iterator += 1

    def _open_menu(self, pos) -> None:
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        copy_action = menu.addAction("复制参数值")
        paste_action = menu.addAction("粘贴参数值")
        has_leaf = self.has_leaf_selection() or (
            self.currentItem() is not None and bool(self.currentItem().data(0, ROLE_LEAF))
        )
        copy_action.setEnabled(has_leaf)
        paste_action.setEnabled(has_leaf)
        action = menu.exec(self.viewport().mapToGlobal(pos))
        if action is copy_action:
            self.copyRequested.emit()
        elif action is paste_action:
            self.pasteRequested.emit()
