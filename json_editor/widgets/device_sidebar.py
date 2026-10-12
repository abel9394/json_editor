"""Searchable, grouped device list."""

from __future__ import annotations

from PySide6.QtCore import QItemSelectionModel, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..grouping import group_color, group_devices, group_of
from ..query import compile_query

ROLE_DEVICE = Qt.ItemDataRole.UserRole
ROLE_IS_GROUP = Qt.ItemDataRole.UserRole + 1

MATCH_COLOR = QColor("#7ec8ff")
NORMAL_COLOR = QColor("#d5deea")


class DeviceSidebar(QFrame):
    selectionChanged = Signal(list)
    copyRequested = Signal()
    pasteRequested = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self._names: list[str] = []
        self._updating = False
        self._matcher = compile_query("")
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title_row = QHBoxLayout()
        title = QLabel("器件")
        title.setStyleSheet("font-size: 13px; font-weight: 700; color: #e8eef4;")
        self.count_label = QLabel("0")
        self.count_label.setStyleSheet("color: #8b9cb3; font-size: 12px;")
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(self.count_label)

        self.search = QLineEdit()
        self.search.setObjectName("SearchBox")
        self.search.setPlaceholderText("搜索：Q1、tc_、Q1-Q12、Q1,R3")
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip("支持子串、逗号多选、数字区间（如 Q1-Q12）。Enter 选中全部匹配。")
        self.search.textChanged.connect(self._apply_filter)
        self.search.returnPressed.connect(self.select_visible)

        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        self.match_label = QLabel("")
        self.match_label.setStyleSheet("color: #8b9cb3; font-size: 12px;")
        self.btn_select_matches = QPushButton("选中全部")
        self.btn_select_matches.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_select_matches.setEnabled(False)
        self.btn_select_matches.clicked.connect(self.select_visible)
        search_row.addWidget(self.search, 1)
        search_row.addWidget(self.btn_select_matches)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setAnimated(True)
        self.tree.setExpandsOnDoubleClick(True)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.tree.itemSelectionChanged.connect(self._on_selection)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._open_menu)

        layout.addLayout(title_row)
        layout.addLayout(search_row)
        layout.addWidget(self.match_label)
        layout.addWidget(self.tree, 1)

    def set_devices(self, names: list[str], keep_selection: list[str] | None = None) -> None:
        self._names = list(names)
        selected = keep_selection or self.selected_devices()
        self._rebuild()
        if selected:
            self.select_devices(selected, notify=False)
        self.count_label.setText(str(len(names)))

    def selected_devices(self) -> list[str]:
        names: list[str] = []
        for item in self.tree.selectedItems():
            if item.data(0, ROLE_IS_GROUP):
                continue
            name = item.data(0, ROLE_DEVICE)
            if name:
                names.append(name)
        return names

    def visible_device_names(self) -> list[str]:
        names: list[str] = []
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            for j in range(group.childCount()):
                child = group.child(j)
                name = child.data(0, ROLE_DEVICE)
                if name:
                    names.append(name)
        return names

    def select_visible(self) -> None:
        names = self.visible_device_names()
        if names:
            self.select_devices(names, notify=True)

    def select_devices(self, names: list[str], notify: bool = True) -> None:
        wanted = set(names)
        self._updating = True
        self.tree.clearSelection()
        current = None
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            for j in range(group.childCount()):
                child = group.child(j)
                if child.data(0, ROLE_DEVICE) in wanted:
                    child.setSelected(True)
                    current = child
        if current is not None:
            self.tree.setCurrentItem(
                current, 0, QItemSelectionModel.SelectionFlag.NoUpdate
            )
            self.tree.scrollToItem(current)
        self._updating = False
        if notify:
            self._on_selection()

    def focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def has_device_focus(self) -> bool:
        return self.tree.hasFocus() or self.search.hasFocus()

    def _rebuild(self) -> None:
        self._updating = True
        self.tree.clear()
        query = self.search.text()
        self._matcher = compile_query(query)
        grouped = group_devices(self._names)
        group_font = QFont()
        group_font.setBold(True)
        match_count = 0
        filtering = bool(query.strip())
        for label, devices in grouped:
            visible = [name for name in devices if self._matcher(name)]
            if filtering and not visible:
                continue
            match_count += len(visible)
            group_item = QTreeWidgetItem([f"{label}  ({len(visible)})"])
            group_item.setData(0, ROLE_IS_GROUP, True)
            group_item.setFont(0, group_font)
            color = QColor(group_color(label))
            group_item.setForeground(0, QBrush(color))
            group_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            for name in visible:
                child = QTreeWidgetItem([name])
                child.setData(0, ROLE_DEVICE, name)
                child.setData(0, ROLE_IS_GROUP, False)
                child.setForeground(0, QBrush(MATCH_COLOR if filtering else NORMAL_COLOR))
                child.setToolTip(0, f"{group_of(name)}  ·  {name}")
                group_item.addChild(child)
            self.tree.addTopLevelItem(group_item)
            group_item.setExpanded(True)
        if filtering:
            self.match_label.setText(f"找到 {match_count} 个")
        else:
            self.match_label.setText("")
        self.btn_select_matches.setEnabled(match_count > 0 and filtering)
        self._updating = False

    def _apply_filter(self, _text: str) -> None:
        selected = self.selected_devices()
        self._rebuild()
        if selected:
            self.select_devices(selected, notify=False)

    def _on_selection(self) -> None:
        if self._updating:
            return
        self.selectionChanged.emit(self.selected_devices())

    def _open_menu(self, pos) -> None:
        from PySide6.QtWidgets import QMenu

        names = self.selected_devices()
        menu = QMenu(self)
        copy_action = menu.addAction("复制器件参数")
        copy_action.setEnabled(bool(names))
        select_vis = menu.addAction("选中当前全部匹配")
        select_vis.setEnabled(bool(self.visible_device_names()) and bool(self.search.text().strip()))
        menu.addSeparator()
        paste_all = menu.addAction("粘贴全部参数")
        paste_keep = menu.addAction("粘贴（保留位置）")
        action = menu.exec(self.tree.viewport().mapToGlobal(pos))
        if action is copy_action:
            self.copyRequested.emit()
        elif action is select_vis:
            self.select_visible()
        elif action is paste_all:
            self.pasteRequested.emit(False)
        elif action is paste_keep:
            self.pasteRequested.emit(True)
