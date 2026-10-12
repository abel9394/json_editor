"""Row/column range picker that lists Q / R / coupler names and applies options."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..grid import infer_grid, names_in_range, qubit_count

KIND_QUBIT = "qubit"
KIND_RESONATOR = "resonator"
KIND_COUPLER = "coupler"

ROLE_PATH = Qt.ItemDataRole.UserRole
ROLE_VALUE = Qt.ItemDataRole.UserRole + 1


def _format_option(path: tuple, value: str) -> str:
    key = "/".join(str(part) for part in path)
    return f"{key} = {value}"


def _parse_path(key: str) -> tuple:
    return tuple(part for part in key.strip().split("/") if part != "")


class RangePanel(QFrame):
    applyRequested = Signal(list, list)
    selectRequested = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("RangePanel")
        self._names: list[str] = []
        self._updating = False
        self._filling_list = False
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)

        title = QLabel("按行列范围批量修改")
        title.setStyleSheet("font-size: 13px; font-weight: 700; color: #e8eef4;")
        layout.addWidget(title)

        grid_row = QHBoxLayout()
        grid_row.setSpacing(8)
        grid_row.addWidget(QLabel("总行"))
        self.spin_n_row = self._spin(1, 64, 12)
        grid_row.addWidget(self.spin_n_row)
        grid_row.addWidget(QLabel("总列"))
        self.spin_n_col = self._spin(1, 64, 6)
        grid_row.addWidget(self.spin_n_col)
        grid_row.addWidget(self._vbar())
        grid_row.addWidget(QLabel("行"))
        self.spin_row1 = self._spin(1, 64, 1)
        self.spin_row2 = self._spin(1, 64, 10)
        grid_row.addWidget(self.spin_row1)
        grid_row.addWidget(QLabel("–"))
        grid_row.addWidget(self.spin_row2)
        grid_row.addWidget(QLabel("列"))
        self.spin_col1 = self._spin(1, 64, 1)
        self.spin_col2 = self._spin(1, 64, 6)
        grid_row.addWidget(self.spin_col1)
        grid_row.addWidget(QLabel("–"))
        grid_row.addWidget(self.spin_col2)
        grid_row.addWidget(self._vbar())
        grid_row.addWidget(QLabel("类型"))
        self.kind = QComboBox()
        self.kind.addItem("比特 Q", KIND_QUBIT)
        self.kind.addItem("谐振腔 R", KIND_RESONATOR)
        self.kind.addItem("耦合器 tc_", KIND_COUPLER)
        self.kind.setMinimumWidth(120)
        grid_row.addWidget(self.kind)
        grid_row.addStretch()
        layout.addLayout(grid_row)

        mid = QHBoxLayout()
        mid.setSpacing(10)
        left = QVBoxLayout()
        self.match_label = QLabel("匹配 0 个")
        self.match_label.setStyleSheet("color: #8b9cb3;")
        self.list = QListWidget()
        self.list.setObjectName("RangeList")
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list.itemSelectionChanged.connect(self._on_list_selection)
        left.addWidget(self.match_label)
        left.addWidget(self.list, 1)

        right = QVBoxLayout()
        self.option_label = QLabel("当前 option  0 项")
        self.option_label.setStyleSheet("color: #8b9cb3;")
        self.option_list = QListWidget()
        self.option_list.setObjectName("RangeList")
        self.option_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.option_list.installEventFilter(self)
        right.addWidget(self.option_label)
        right.addWidget(self.option_list, 1)

        key_row = QHBoxLayout()
        self.edit_key = QLineEdit()
        self.edit_key.setPlaceholderText("参数名，如 arm")
        self.edit_value = QLineEdit()
        self.edit_value.setPlaceholderText("值，如 none")
        self.edit_key.returnPressed.connect(self._add_manual_option)
        self.edit_value.returnPressed.connect(self._add_manual_option)
        self.btn_add = QPushButton("添加")
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.clicked.connect(self._add_manual_option)
        key_row.addWidget(self.edit_key, 2)
        key_row.addWidget(QLabel("="))
        key_row.addWidget(self.edit_value, 2)
        key_row.addWidget(self.btn_add)
        right.addLayout(key_row)

        hint = QLabel("右侧 Ctrl/Shift 多选参数会同步到此列表；只写入目标里已有的键。")
        hint.setStyleSheet("color: #6b7c91; font-size: 12px;")
        hint.setWordWrap(True)
        right.addWidget(hint)

        btn_row = QHBoxLayout()
        self.btn_select = QPushButton("在左侧选中")
        self.btn_select.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove = QPushButton("移除")
        self.btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply = QPushButton("应用到范围内")
        self.btn_apply.setObjectName("PrimaryButton")
        self.btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_row.addWidget(self.btn_select)
        btn_row.addWidget(self.btn_remove)
        btn_row.addWidget(self.btn_apply)
        right.addLayout(btn_row)

        mid.addLayout(left, 3)
        mid.addLayout(right, 4)
        layout.addLayout(mid, 1)

        for spin in (
            self.spin_n_row,
            self.spin_n_col,
            self.spin_row1,
            self.spin_row2,
            self.spin_col1,
            self.spin_col2,
        ):
            spin.valueChanged.connect(self.refresh_names)
        self.kind.currentIndexChanged.connect(self.refresh_names)
        self.btn_select.clicked.connect(self._emit_select)
        self.btn_remove.clicked.connect(self._remove_selected_options)
        self.btn_apply.clicked.connect(self._emit_apply)
        self._refresh_option_label()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.option_list and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self._remove_selected_options()
                return True
        return super().eventFilter(watched, event)

    def _spin(self, lo: int, hi: int, value: int) -> QSpinBox:
        box = QSpinBox()
        box.setRange(lo, hi)
        box.setValue(value)
        box.setFixedWidth(64)
        return box

    def _vbar(self) -> QLabel:
        bar = QLabel("|")
        bar.setStyleSheet("color: #33455c;")
        return bar

    def set_devices(self, names: list[str], n_row: int | None = None, n_col: int | None = None) -> None:
        self._names = list(names)
        count = qubit_count(names)
        if n_col is None or n_row is None:
            inferred_row, inferred_col = infer_grid(count, n_col)
            n_row = n_row or inferred_row
            n_col = n_col or inferred_col
        self._updating = True
        self.spin_n_row.setValue(max(1, int(n_row)))
        self.spin_n_col.setValue(max(1, int(n_col)))
        self.spin_row1.setMaximum(self.spin_n_row.value())
        self.spin_row2.setMaximum(self.spin_n_row.value())
        self.spin_col1.setMaximum(self.spin_n_col.value())
        self.spin_col2.setMaximum(self.spin_n_col.value())
        if self.spin_row2.value() > self.spin_n_row.value():
            self.spin_row2.setValue(self.spin_n_row.value())
        if self.spin_col2.value() > self.spin_n_col.value():
            self.spin_col2.setValue(self.spin_n_col.value())
        self._updating = False
        self.refresh_names()

    def set_option(self, path: tuple, value_text: str) -> None:
        self.set_options([(path, value_text)])

    def set_options(self, options: list[tuple[tuple, str]]) -> None:
        self.option_list.clear()
        for path, value_text in options:
            self._upsert_option(tuple(path), value_text)
        self._refresh_option_label()

    def collected_options(self) -> list[tuple[tuple, str]]:
        options: list[tuple[tuple, str]] = []
        for i in range(self.option_list.count()):
            item = self.option_list.item(i)
            path = tuple(item.data(ROLE_PATH) or ())
            value = item.data(ROLE_VALUE)
            if path:
                options.append((path, "" if value is None else str(value)))
        return options

    def matched_names(self) -> list[str]:
        names: list[str] = []
        for i in range(self.list.count()):
            names.append(self.list.item(i).text())
        return names

    def grid_settings(self) -> tuple[int, int]:
        return self.spin_n_row.value(), self.spin_n_col.value()

    def refresh_names(self) -> None:
        if self._updating:
            return
        n_col = self.spin_n_col.value()
        n_row = self.spin_n_row.value()
        self.spin_row1.setMaximum(n_row)
        self.spin_row2.setMaximum(n_row)
        self.spin_col1.setMaximum(n_col)
        self.spin_col2.setMaximum(n_col)
        rows = (self.spin_row1.value(), self.spin_row2.value())
        cols = (self.spin_col1.value(), self.spin_col2.value())
        kind = self.kind.currentData()
        names = names_in_range(self._names, kind, n_col, rows, cols)
        self._filling_list = True
        self.list.clear()
        for name in names:
            self.list.addItem(QListWidgetItem(name))
        self._filling_list = False
        self.match_label.setText(f"匹配 {len(names)} 个")
        self.btn_select.setEnabled(bool(names))
        self._refresh_option_label()

    def _upsert_option(self, path: tuple, value_text: str) -> None:
        for i in range(self.option_list.count()):
            item = self.option_list.item(i)
            stored = tuple(item.data(ROLE_PATH) or ())
            if stored == path:
                item.setData(ROLE_VALUE, value_text)
                item.setText(_format_option(path, value_text))
                return
        item = QListWidgetItem(_format_option(path, value_text))
        item.setData(ROLE_PATH, path)
        item.setData(ROLE_VALUE, value_text)
        self.option_list.addItem(item)

    def _add_manual_option(self) -> None:
        path = _parse_path(self.edit_key.text())
        if not path:
            return
        self._upsert_option(path, self.edit_value.text())
        self.edit_key.clear()
        self.edit_value.clear()
        self._refresh_option_label()

    def _remove_selected_options(self) -> None:
        rows = sorted(
            {self.option_list.row(item) for item in self.option_list.selectedItems()},
            reverse=True,
        )
        for row in rows:
            self.option_list.takeItem(row)
        self._refresh_option_label()

    def _refresh_option_label(self) -> None:
        count = self.option_list.count()
        self.option_label.setText(f"当前 option  {count} 项")
        self.btn_apply.setEnabled(bool(self.matched_names()) and count > 0)
        self.btn_remove.setEnabled(count > 0)

    def _on_list_selection(self) -> None:
        if self._filling_list:
            return
        selected = [item.text() for item in self.list.selectedItems()]
        if selected:
            self.selectRequested.emit(selected)

    def _emit_select(self) -> None:
        names = self.matched_names()
        if names:
            self.selectRequested.emit(names)

    def _emit_apply(self) -> None:
        names = self.matched_names()
        options = self.collected_options()
        if not names or not options:
            return
        self.applyRequested.emit(names, options)
