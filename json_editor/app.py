"""Main window for the JSON device parameter editor."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QEvent, QMimeData, QSettings, Qt
from PySide6.QtGui import (
    QAction,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QIcon,
    QKeySequence,
    QPalette,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .commands import (
    MergeOptionsCommand,
    PasteCellsCommand,
    ReplaceDevicesCommand,
    SetValueCommand,
)
from .document import (
    JsonDocument,
    coerce_text,
    count_params,
    merge_device_params,
)
from .grouping import group_color, group_of
from .widgets.device_sidebar import ROLE_DEVICE, DeviceSidebar
from .widgets.param_tree import ROLE_LEAF, ROLE_PATH, ParamTreeWidget
from .widgets.range_panel import RangePanel

DEVICE_MIME = "application/x-json-editor-device"
APP_TITLE = "JSON 器件参数编辑器"


def _theme_path() -> Path:
    return _asset_path("theme.qss")


def _asset_path(name: str) -> Path:
    here = Path(__file__).resolve().parent
    candidates = [here / name, here / "assets" / name]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        root = Path(meipass)
        candidates.extend(
            [
                root / "json_editor" / name,
                root / "json_editor" / "assets" / name,
            ]
        )
    for path in candidates:
        if path.exists():
            return path
    return here / "assets" / name


def _app_icon() -> QIcon:
    icon = QIcon()
    ico = _asset_path("app.ico")
    png = _asset_path("app.png")
    if ico.exists():
        icon.addFile(str(ico))
    if png.exists():
        icon.addFile(str(png))
    return icon


def apply_dark_palette(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor("#121820"))
    pal.setColor(QPalette.ColorRole.WindowText, QColor("#e8eef4"))
    pal.setColor(QPalette.ColorRole.Base, QColor("#1a2332"))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#1f2a3a"))
    pal.setColor(QPalette.ColorRole.Text, QColor("#e8eef4"))
    pal.setColor(QPalette.ColorRole.Button, QColor("#243044"))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor("#e8eef4"))
    pal.setColor(QPalette.ColorRole.Highlight, QColor("#1e5a8c"))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor("#243044"))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor("#e8eef4"))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor("#6b7c91"))
    pal.setColor(QPalette.ColorRole.Link, QColor("#3d9cf0"))
    app.setPalette(pal)
    qss = _theme_path().read_text(encoding="utf-8")
    app.setStyleSheet(qss)


class DeviceHeader(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HeaderCard")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.name_label = QLabel("未选择器件")
        self.name_label.setObjectName("DeviceName")
        self.meta_label = QLabel("打开 JSON 参数文件开始编辑")
        self.meta_label.setObjectName("DeviceMeta")
        text_col.addWidget(self.name_label)
        text_col.addWidget(self.meta_label)

        self.badge = QLabel("")
        self.badge.setObjectName("TypeBadge")
        self.badge.hide()

        layout.addLayout(text_col, 1)
        layout.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignTop)

    def show_empty(self, message: str = "打开 JSON 参数文件开始编辑") -> None:
        self.name_label.setText("未选择器件")
        self.meta_label.setText(message)
        self.badge.hide()

    def show_device(self, name: str, extra_count: int, params) -> None:
        title = name if extra_count <= 0 else f"{name}  +{extra_count}"
        self.name_label.setText(title)
        label = group_of(name)
        leaves, nested = count_params(params) if isinstance(params, (dict, list)) else (0, 0)
        parts = [f"{leaves} 个参数"]
        if nested:
            parts.append(f"{nested} 个嵌套")
        if extra_count > 0:
            parts.append(f"已选 {extra_count + 1} 个器件")
        self.meta_label.setText("  ·  ".join(parts))
        color = group_color(label)
        self.badge.setText(label)
        self.badge.setStyleSheet(
            f"background-color: {color}; color: #121820; font-size: 11px;"
            " font-weight: 700; padding: 3px 10px; border-radius: 9px;"
        )
        self.badge.show()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.document = JsonDocument(self)
        self.undo_stack = QUndoStack(self)
        self.settings = QSettings("ChipTools", "JsonDeviceEditor")
        self.current_device: str | None = None
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(1100, 700)
        self.resize(1280, 820)
        self.setAcceptDrops(True)
        icon = _app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        self._build_ui()
        self._build_actions()
        self._connect()
        self._update_actions()
        self._update_title()

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("AppRoot")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_topbar())

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(14, 12, 14, 12)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.sidebar = DeviceSidebar()
        self.sidebar.setMinimumWidth(220)
        self.sidebar.setMaximumWidth(420)

        detail = QFrame()
        detail.setObjectName("DetailPanel")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(14, 14, 14, 14)
        detail_layout.setSpacing(10)
        self.header = DeviceHeader()
        self.param_filter = QLineEdit()
        self.param_filter.setObjectName("SearchBox")
        self.param_filter.setPlaceholderText("筛选参数名… 如 arm")
        self.param_filter.setClearButtonEnabled(True)
        self.param_filter.setToolTip("按参数名或路径过滤，例如 arm 只显示 arm / arm_side / arm_w")
        self.param_tree = ParamTreeWidget()
        self.param_tree.set_document(self.document)
        self.empty_hint = QLabel("打开 JSON 参数文件，或将文件拖放到窗口中")
        self.empty_hint.setObjectName("EmptyHint")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail_layout.addWidget(self.header)
        detail_layout.addWidget(self.param_filter)
        detail_layout.addWidget(self.param_tree, 1)
        detail_layout.addWidget(self.empty_hint, 1)
        self.param_tree.hide()
        self.param_filter.hide()

        splitter.addWidget(self.sidebar)
        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 980])

        self.range_panel = RangePanel()
        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.addWidget(splitter)
        vsplit.addWidget(self.range_panel)
        vsplit.setStretchFactor(0, 3)
        vsplit.setStretchFactor(1, 1)
        vsplit.setSizes([560, 220])
        body_layout.addWidget(vsplit)
        outer.addWidget(body, 1)

        status = QStatusBar()
        self.setStatusBar(status)
        self.status_devices = QLabel("未加载")
        self.status_current = QLabel("")
        self.status_clip = QLabel("")
        status.addWidget(self.status_devices)
        status.addPermanentWidget(self.status_current)
        status.addPermanentWidget(self.status_clip)

    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(58)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 10, 18, 10)
        layout.setSpacing(8)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title = QLabel(APP_TITLE)
        title.setObjectName("AppTitle")
        file_row = QHBoxLayout()
        file_row.setSpacing(6)
        self.dirty_dot = QLabel("●")
        self.dirty_dot.setObjectName("DirtyDot")
        self.dirty_dot.hide()
        self.file_label = QLabel("未打开文件")
        self.file_label.setObjectName("FileLabel")
        file_row.addWidget(self.dirty_dot)
        file_row.addWidget(self.file_label)
        file_row.addStretch()
        title_col.addWidget(title)
        title_col.addLayout(file_row)

        layout.addLayout(title_col, 1)
        layout.addStretch()

        self.btn_open = QPushButton("打开")
        self.btn_save = QPushButton("保存")
        self.btn_save.setObjectName("PrimaryButton")
        self.btn_save_as = QPushButton("另存为")
        self.btn_undo = QPushButton("撤销")
        self.btn_redo = QPushButton("重做")
        self.btn_copy = QPushButton("复制")
        self.btn_paste = QPushButton("粘贴")
        for button in (
            self.btn_open,
            self.btn_save,
            self.btn_save_as,
            self.btn_undo,
            self.btn_redo,
            self.btn_copy,
            self.btn_paste,
        ):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            layout.addWidget(button)
        return bar

    def _build_actions(self) -> None:
        def add(text, sequence, slot, *, shortcut_context=Qt.ShortcutContext.WindowShortcut) -> QAction:
            action = QAction(text, self)
            action.setShortcut(QKeySequence(sequence))
            action.setShortcutContext(shortcut_context)
            action.triggered.connect(slot)
            self.addAction(action)
            return action

        self.act_open = add("打开", QKeySequence.StandardKey.Open, self.open_file)
        self.act_save = add("保存", QKeySequence.StandardKey.Save, self.save_file)
        self.act_save_as = add("另存为", QKeySequence.StandardKey.SaveAs, self.save_file_as)
        self.act_undo = QAction("撤销", self)
        self.act_undo.triggered.connect(self.undo_stack.undo)
        self.addAction(self.act_undo)
        self.act_redo = QAction("重做", self)
        self.act_redo.triggered.connect(self.undo_stack.redo)
        self.addAction(self.act_redo)
        self.act_copy = QAction("复制", self)
        self.act_copy.triggered.connect(self.copy_payload)
        self.addAction(self.act_copy)
        self.act_paste = QAction("粘贴", self)
        self.act_paste.triggered.connect(self.paste_payload)
        self.addAction(self.act_paste)
        add("搜索", QKeySequence.StandardKey.Find, self.sidebar.focus_search)

        self.btn_open.clicked.connect(self.open_file)
        self.btn_save.clicked.connect(self.save_file)
        self.btn_save_as.clicked.connect(self.save_file_as)
        self.btn_undo.clicked.connect(self.undo_stack.undo)
        self.btn_redo.clicked.connect(self.undo_stack.redo)
        self.btn_copy.clicked.connect(self.copy_payload)
        self.btn_paste.clicked.connect(self.paste_payload)

    def _connect(self) -> None:
        self.sidebar.selectionChanged.connect(self._on_devices_selected)
        self.sidebar.copyRequested.connect(self.copy_devices)
        self.sidebar.pasteRequested.connect(self.paste_devices)
        self.param_tree.valueCommitted.connect(self._on_value_committed)
        self.param_tree.copyRequested.connect(self.copy_cells)
        self.param_tree.pasteRequested.connect(self.paste_cells)
        self.param_tree.itemSelectionChanged.connect(self._on_param_selection)
        self.param_filter.textChanged.connect(self.param_tree.apply_filter)
        self.range_panel.applyRequested.connect(self._on_range_apply)
        self.range_panel.selectRequested.connect(self._on_range_select)
        self.range_panel.spin_n_row.valueChanged.connect(self._save_grid_settings)
        self.range_panel.spin_n_col.valueChanged.connect(self._save_grid_settings)
        self.document.valueChanged.connect(self._on_value_changed)
        self.document.deviceReplaced.connect(self._on_device_replaced)
        self.document.loaded.connect(self._on_loaded)
        self.document.saved.connect(self._on_saved)
        self.undo_stack.canUndoChanged.connect(lambda _: self._update_actions())
        self.undo_stack.canRedoChanged.connect(lambda _: self._update_actions())
        self.undo_stack.cleanChanged.connect(lambda _: self._update_title())

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".json"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".json"):
                if self._maybe_save_before_leave():
                    self._load_path(path)
                break

    def closeEvent(self, event) -> None:
        if self._maybe_save_before_leave():
            self.undo_stack.blockSignals(True)
            event.accept()
        else:
            event.ignore()

    def open_file(self) -> None:
        if not self._maybe_save_before_leave():
            return
        start = self.settings.value("last_dir", str(Path.home()))
        path, _ = QFileDialog.getOpenFileName(
            self, "打开 JSON 参数文件", start, "JSON 文件 (*.json);;所有文件 (*.*)"
        )
        if path:
            self._load_path(path)

    def save_file(self) -> None:
        if self.document.path is None:
            self.save_file_as()
            return
        try:
            self.document.save()
            self.undo_stack.setClean()
        except OSError as exc:
            QMessageBox.critical(self, "保存失败", str(exc))

    def save_file_as(self) -> None:
        start = str(self.document.path) if self.document.path else self.settings.value(
            "last_dir", str(Path.home())
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "另存为", start, "JSON 文件 (*.json);;所有文件 (*.*)"
        )
        if not path:
            return
        try:
            self.document.save(path)
            self.undo_stack.setClean()
            self.settings.setValue("last_dir", str(Path(path).parent))
        except OSError as exc:
            QMessageBox.critical(self, "保存失败", str(exc))

    def copy_payload(self) -> None:
        if self.param_tree.hasFocus() and (
            self.param_tree.has_leaf_selection()
            or (
                self.param_tree.currentItem() is not None
                and bool(self.param_tree.currentItem().data(0, ROLE_LEAF))
            )
        ):
            self.copy_cells()
        else:
            self.copy_devices()

    def paste_payload(self) -> None:
        if self._clipboard_has_device() and not (
            self.param_tree.hasFocus() and self.param_tree.has_leaf_selection()
        ):
            self.paste_devices(keep_position=False)
        elif self.param_tree.hasFocus() or self.param_tree.has_leaf_selection():
            self.paste_cells()
        else:
            self.paste_devices(keep_position=False)

    def copy_devices(self) -> None:
        names = self.sidebar.selected_devices()
        if not names:
            return
        payload = {
            "_json_editor_device_copy": True,
            "devices": {name: self.document.get_device(name) for name in names},
        }
        devices = payload["devices"]
        text_obj = devices[names[0]] if len(names) == 1 else devices
        mime = self._make_mime(payload, json.dumps(text_obj, indent=2, ensure_ascii=False))
        QApplication.clipboard().setMimeData(mime)
        label = names[0] if len(names) == 1 else f"{len(names)} 个器件"
        self.status_clip.setText(f"剪贴板：器件 {label}")
        self.statusBar().showMessage(f"已复制 {label}", 2000)

    def paste_devices(self, keep_position: bool = False) -> None:
        payload = self._read_device_clipboard()
        if payload is None:
            self.statusBar().showMessage("剪贴板中没有器件参数", 2500)
            return
        targets = self.sidebar.selected_devices()
        if not targets:
            self.statusBar().showMessage("请先选择要粘贴的器件", 2500)
            return
        sources = list(payload.get("devices", {}).values())
        if not sources:
            return
        replacements: dict[str, tuple] = {}
        for index, target in enumerate(targets):
            source = sources[0] if len(sources) == 1 else sources[index % len(sources)]
            old = copy.deepcopy(self.document.get_device(target))
            if isinstance(old, dict) and isinstance(source, dict):
                new = merge_device_params(old, source, keep_position)
            else:
                new = copy.deepcopy(source)
            if new != old:
                replacements[target] = (old, new)
        if not replacements:
            return
        mode = "保留位置" if keep_position else "全部参数"
        self.undo_stack.push(
            ReplaceDevicesCommand(
                self.document,
                replacements,
                f"粘贴{mode} → {', '.join(replacements)}",
            )
        )
        self.statusBar().showMessage(f"已粘贴到 {len(replacements)} 个器件", 2000)

    def copy_cells(self) -> None:
        if self.param_tree.currentItem() is not None and not self.param_tree.has_leaf_selection():
            current = self.param_tree.currentItem()
            if current.data(0, ROLE_LEAF):
                current.setSelected(True)
        text = self.param_tree.copy_text()
        if not text:
            self.copy_devices()
            return
        QApplication.clipboard().setText(text)
        self.status_clip.setText("剪贴板：参数值")
        self.statusBar().showMessage("已复制参数值", 2000)

    def paste_cells(self) -> None:
        if self.current_device is None:
            return
        text = QApplication.clipboard().text()
        if not text:
            return
        values = _split_clipboard_values(text)
        items = self.param_tree.selected_leaf_items()
        if not items:
            current = self.param_tree.currentItem()
            if current is not None and current.data(0, ROLE_LEAF):
                items = [current]
        if not items:
            return
        changes = []
        for index, item in enumerate(items):
            path = tuple(item.data(0, ROLE_PATH) or ())
            old = self.document.get_value(self.current_device, path)
            incoming = values[0] if len(values) == 1 else values[index % len(values)]
            new = coerce_text(incoming, old)
            if new != old:
                changes.append((path, old, new))
        if not changes:
            return
        self.undo_stack.push(PasteCellsCommand(self.document, self.current_device, changes))

    def _on_value_committed(self, path: tuple, text: str) -> None:
        if self.current_device is None:
            return
        old = self.document.get_value(self.current_device, path)
        new = coerce_text(text, old)
        if new == old:
            self.param_tree.update_value(path, old)
            return
        self.undo_stack.push(
            SetValueCommand(self.document, self.current_device, path, old, new)
        )

    def _on_value_changed(self, device: str, path: tuple, value) -> None:
        if device == self.param_tree.device:
            self.param_tree.update_value(path, value)
            self.param_tree.refresh_modified()
        self._refresh_header()
        self._update_title()

    def _on_device_replaced(self, device: str) -> None:
        if device == self.param_tree.device:
            self.param_tree.load_device(device, self.document.get_device(device))
        self._refresh_header()
        self._update_title()

    def _on_loaded(self) -> None:
        names = self.document.device_names()
        self.sidebar.set_devices(names)
        n_row = int(self.settings.value("grid_n_row", 0) or 0)
        n_col = int(self.settings.value("grid_n_col", 0) or 0)
        self.range_panel.set_devices(
            names,
            n_row=n_row or None,
            n_col=n_col or None,
        )
        self._save_grid_settings()
        self.undo_stack.clear()
        self.undo_stack.setClean()
        if names:
            self.sidebar.select_devices([names[0]])
        else:
            self._show_empty("文件中没有器件")
        self.status_devices.setText(f"共 {len(names)} 个器件")
        self._update_title()
        self._update_actions()

    def _on_saved(self) -> None:
        self.param_tree.refresh_modified()
        self._update_title()
        self.statusBar().showMessage("已保存", 2000)

    def _on_devices_selected(self, names: list[str]) -> None:
        if not names:
            self.current_device = None
            self._show_empty("从左侧选择一个器件")
            self.status_current.setText("")
            self._update_actions()
            return
        current_item = self.sidebar.tree.currentItem()
        current = names[-1]
        if current_item is not None:
            name = current_item.data(0, ROLE_DEVICE)
            if name:
                current = name
        self.current_device = current
        params = self.document.get_device(current)
        self.empty_hint.hide()
        self.param_filter.show()
        self.param_tree.show()
        self.param_tree.load_device(current, params)
        self.param_tree.apply_filter(self.param_filter.text())
        self.header.show_device(current, len(names) - 1, params)
        self.status_current.setText(f"当前：{current}")
        self._update_actions()

    def _load_path(self, path: str) -> None:
        try:
            self.document.load(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "打开失败", str(exc))
            return
        self.settings.setValue("last_dir", str(Path(path).parent))

    def _show_empty(self, message: str) -> None:
        self.header.show_empty(message)
        self.param_tree.hide()
        self.param_filter.hide()
        self.empty_hint.setText(message)
        self.empty_hint.show()

    def _on_param_selection(self) -> None:
        options = self.param_tree.current_options()
        if options:
            self.range_panel.set_options(options)

    def _on_range_select(self, names: list[str]) -> None:
        if not names:
            return
        visible = set(self.sidebar.visible_device_names())
        if any(name not in visible for name in names) and self.sidebar.search.text():
            self.sidebar.search.clear()
        self.sidebar.select_devices(names)

    def _on_range_apply(self, names: list[str], options: list) -> None:
        changes = []
        skipped = 0
        devices_changed: set[str] = set()
        for name in names:
            for path, text in options:
                path = tuple(path)
                if not self.document.has_path(name, path):
                    skipped += 1
                    continue
                old = self.document.get_value(name, path)
                new = coerce_text(str(text), old)
                if new != old:
                    changes.append((name, path, old, new))
                    devices_changed.add(name)
        if not changes:
            self.statusBar().showMessage(f"没有需要修改的项（跳过 {skipped}）", 2500)
            return
        self.undo_stack.push(
            MergeOptionsCommand(
                self.document,
                changes,
                f"范围写入 {len(options)} 项 → {len(devices_changed)} 个器件",
            )
        )
        self.statusBar().showMessage(
            f"已改 {len(changes)} 项 / {len(devices_changed)} 个器件，跳过 {skipped}",
            3500,
        )

    def _save_grid_settings(self, *_args) -> None:
        n_row, n_col = self.range_panel.grid_settings()
        self.settings.setValue("grid_n_row", n_row)
        self.settings.setValue("grid_n_col", n_col)

    def _refresh_header(self) -> None:
        names = self.sidebar.selected_devices()
        if self.current_device and self.current_device in (self.document.data or {}):
            self.header.show_device(
                self.current_device,
                max(0, len(names) - 1),
                self.document.get_device(self.current_device),
            )

    def _maybe_save_before_leave(self) -> bool:
        if self.undo_stack.isClean():
            return True
        box = QMessageBox(self)
        box.setWindowTitle("未保存的更改")
        box.setText("当前文件有未保存的修改，是否保存？")
        box.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel
        )
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        result = box.exec()
        if result == QMessageBox.StandardButton.Save:
            self.save_file()
            return self.undo_stack.isClean()
        if result == QMessageBox.StandardButton.Discard:
            return True
        return False

    def _clipboard_has_device(self) -> bool:
        mime = QApplication.clipboard().mimeData()
        return mime is not None and mime.hasFormat(DEVICE_MIME)

    def _read_device_clipboard(self) -> dict | None:
        mime = QApplication.clipboard().mimeData()
        if mime is not None and mime.hasFormat(DEVICE_MIME):
            raw = bytes(mime.data(DEVICE_MIME)).decode("utf-8")
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict) and payload.get("_json_editor_device_copy"):
                return payload
        text = QApplication.clipboard().text().strip()
        if not text:
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        if isinstance(data, dict) and data.get("_json_editor_device_copy"):
            return data
        if isinstance(data, dict):
            if data and all(isinstance(v, dict) for v in data.values()):
                return {"_json_editor_device_copy": True, "devices": data}
            return {"_json_editor_device_copy": True, "devices": {"_clipboard": data}}
        return None

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            from PySide6.QtWidgets import QLineEdit

            if isinstance(watched, QLineEdit):
                return False
            if event.matches(QKeySequence.StandardKey.Copy):
                self.copy_payload()
                return True
            if event.matches(QKeySequence.StandardKey.Paste):
                self.paste_payload()
                return True
            if (
                event.key() == Qt.Key.Key_V
                and event.modifiers()
                == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
            ):
                self.paste_devices(keep_position=True)
                return True
            if event.matches(QKeySequence.StandardKey.Undo):
                self.undo_stack.undo()
                return True
            if event.matches(QKeySequence.StandardKey.Redo) or (
                event.key() == Qt.Key.Key_Y
                and event.modifiers() == Qt.KeyboardModifier.ControlModifier
            ):
                self.undo_stack.redo()
                return True
        return super().eventFilter(watched, event)

    def _make_mime(self, payload: dict, text: str):
        mime = QMimeData()
        mime.setData(DEVICE_MIME, QByteArray(json.dumps(payload, ensure_ascii=False).encode("utf-8")))
        mime.setText(text)
        return mime

    def _update_actions(self) -> None:
        has_doc = bool(self.document.data)
        has_sel = bool(self.sidebar.selected_devices())
        self.btn_save.setEnabled(has_doc)
        self.btn_save_as.setEnabled(has_doc)
        self.btn_undo.setEnabled(self.undo_stack.canUndo())
        self.btn_redo.setEnabled(self.undo_stack.canRedo())
        self.btn_copy.setEnabled(has_sel)
        self.btn_paste.setEnabled(has_sel)
        self.act_save.setEnabled(has_doc)
        self.act_save_as.setEnabled(has_doc)
        self.act_undo.setEnabled(self.undo_stack.canUndo())
        self.act_redo.setEnabled(self.undo_stack.canRedo())
        self.act_copy.setEnabled(has_sel)
        self.act_paste.setEnabled(has_sel)

    def _update_title(self) -> None:
        dirty = not self.undo_stack.isClean()
        name = self.document.filename
        star = "● " if dirty else ""
        self.setWindowTitle(f"{star}{name} — {APP_TITLE}" if self.document.path else APP_TITLE)
        self.file_label.setText(name)
        self.dirty_dot.setVisible(dirty)


def _split_clipboard_values(text: str) -> list[str]:
    values: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        values.extend(line.split("\t"))
    values = [item for item in values if item != ""]
    return values or [text]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName(APP_TITLE)
    app.setOrganizationName("ChipTools")
    font = QFont("Microsoft YaHei UI")
    if font.exactMatch():
        app.setFont(font)
    apply_dark_palette(app)
    icon = _app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    window = MainWindow()
    app.installEventFilter(window)
    window.show()
    startup = None
    args = argv[1:]
    for arg in args:
        if arg.lower().endswith(".json") and Path(arg).exists():
            startup = arg
            break
    if startup:
        window._load_path(startup)
    return app.exec()
