"""主窗口 - 完整版"""
import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QMessageBox,
    QTabWidget, QTextEdit, QLineEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QListWidget,
    QDialog, QDialogButtonBox, QFormLayout, QComboBox,
    QCheckBox, QGroupBox, QStatusBar, QMenuBar, QMenu,
    QListWidgetItem, QAbstractItemView,
)
from PyQt6.QtCore import Qt, QSize, QMimeData
from PyQt6.QtGui import QAction, QDragEnterEvent, QDropEvent


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self, app_service):
        super().__init__()
        self.app = app_service
        self._setup_ui()
        self._setup_menu()
        self._connect_signals()
        self._refresh_word_table()

    def _setup_ui(self):
        from src import __app_name__, __version__
        self.setWindowTitle(f"{__app_name__} v{__version__}")
        self.setMinimumSize(900, 650)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # 顶部说明
        info_label = QLabel("💡 拖拽文件到下方，或点击按钮选择文件进行脱敏 / 还原")
        layout.addWidget(info_label)

        # Tab 页
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.tabs.addTab(self._create_wordlib_tab(), "📚 词库管理")
        self.tabs.addTab(self._create_desensitize_tab(), "🔒 文档脱敏")
        self.tabs.addTab(self._create_restore_tab(), "🔁 文档还原")
        self.tabs.addTab(self._create_history_tab(), "📋 会话历史")
        self.tabs.addTab(self._create_settings_tab(), "⚙️ 设置")

        # 底部状态栏
        self.statusBar().showMessage("就绪")

    def _setup_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("文件")
        file_menu.addAction("打开文件...", self.on_open_file)
        file_menu.addSeparator()
        file_menu.addAction("退出", self.close)

        help_menu = menubar.addMenu("帮助")
        help_menu.addAction("关于", self.on_about)

    def _connect_signals(self):
        """绑定所有按钮事件"""
        # 词库 Tab
        self.btn_add_word.clicked.connect(self.on_add_word)
        self.btn_import.clicked.connect(self.on_import)
        self.btn_export.clicked.connect(self.on_export)
        self.btn_backup.clicked.connect(self.on_backup)
        self.btn_word_search.clicked.connect(self.on_search_words)
        self.btn_clear_search.clicked.connect(self.on_clear_search)
        self.word_table.itemSelectionChanged.connect(self.on_word_selection_changed)
        self.btn_delete_word.clicked.connect(self.on_delete_word)
        self.btn_edit_word.clicked.connect(self.on_edit_word)

        # 脱敏 Tab
        self.btn_select_file_des.clicked.connect(self.on_select_file_desensitize)
        self.btn_preview.clicked.connect(self.on_preview_desensitize)
        self.btn_execute_desensitize.clicked.connect(self.on_execute_desensitize)

        # 还原 Tab
        self.btn_select_file_res.clicked.connect(self.on_select_file_restore)
        self.btn_preview_restore.clicked.connect(self.on_preview_restore)
        self.btn_execute_restore.clicked.connect(self.on_execute_restore)

        # 设置 Tab
        self.btn_save_settings.clicked.connect(self.on_save_settings)
        self.btn_set_password.clicked.connect(self.on_set_password)
        self.btn_clear_password.clicked.connect(self.on_clear_password)

        # 历史 Tab
        self.btn_refresh_history.clicked.connect(self.on_refresh_history)
        self.btn_view_snapshot.clicked.connect(self.on_view_snapshot)

    # ============================================================
    # 词库管理 Tab
    # ============================================================

    def _create_wordlib_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        # 工具栏
        toolbar = QHBoxLayout()
        self.btn_add_word = QPushButton("➕ 新增词条")
        self.btn_import = QPushButton("📥 批量导入")
        self.btn_export = QPushButton("📤 导出词库")
        self.btn_backup = QPushButton("💾 备份词库")
        self.btn_delete_word = QPushButton("🗑️ 删除")
        self.btn_delete_word.setEnabled(False)
        self.btn_edit_word = QPushButton("✏️ 编辑")
        self.btn_edit_word.setEnabled(False)
        for btn in [self.btn_add_word, self.btn_import, self.btn_export,
                    self.btn_backup, self.btn_delete_word, self.btn_edit_word]:
            toolbar.addWidget(btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # 搜索栏
        search_layout = QHBoxLayout()
        self.word_search_input = QLineEdit()
        self.word_search_input.setPlaceholderText("搜索原始词或备注...")
        self.word_category_filter = QComboBox()
        self.word_category_filter.addItems(["全部", "PERSON", "COMPANY", "PHONE", "EMAIL",
                                            "IDCARD", "BANKCARD", "AMOUNT", "PROJECT", "LOCATION", "CUSTOM"])
        self.btn_word_search = QPushButton("搜索")
        self.btn_clear_search = QPushButton("清除")
        search_layout.addWidget(QLabel("关键字:"))
        search_layout.addWidget(self.word_search_input, stretch=1)
        search_layout.addWidget(QLabel("分类:"))
        search_layout.addWidget(self.word_category_filter)
        search_layout.addWidget(self.btn_word_search)
        search_layout.addWidget(self.btn_clear_search)
        layout.addLayout(search_layout)

        # 词库表格
        self.word_table = QTableWidget()
        self.word_table.setColumnCount(7)
        self.word_table.setHorizontalHeaderLabels(["ID", "分类", "原始词", "代号", "命中", "备注", "创建时间"])
        self.word_table.horizontalHeader().setStretchLastSection(True)
        self.word_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.word_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.word_table.setAlternatingRowColors(True)
        layout.addWidget(self.word_table)

        # 统计栏
        self.word_stats_label = QLabel("词条数: 0")
        layout.addWidget(self.word_stats_label)

        return w

    def _refresh_word_table(self, keyword=None, category=None):
        results = self.app.wordlib.search(keyword=keyword, category=category)
        self.word_table.setRowCount(len(results))
        for i, entry in enumerate(results):
            self.word_table.setItem(i, 0, QTableWidgetItem(str(entry.id)))
            self.word_table.setItem(i, 1, QTableWidgetItem(entry.category))
            self.word_table.setItem(i, 2, QTableWidgetItem(entry.original))
            self.word_table.setItem(i, 3, QTableWidgetItem(entry.placeholder))
            self.word_table.setItem(i, 4, QTableWidgetItem(str(entry.hit_count)))
            self.word_table.setItem(i, 5, QTableWidgetItem(entry.note or ""))
            self.word_table.setItem(i, 6, QTableWidgetItem(entry.created_at.strftime("%Y-%m-%d %H:%M")))
        self.word_stats_label.setText(f"词条数: {len(results)}")

    def on_search_words(self):
        keyword = self.word_search_input.text().strip() or None
        category = self.word_category_filter.currentText()
        category = None if category == "全部" else category
        self._refresh_word_table(keyword=keyword, category=category)

    def on_clear_search(self):
        self.word_search_input.clear()
        self.word_category_filter.setCurrentIndex(0)
        self._refresh_word_table()

    def on_word_selection_changed(self):
        # PyQt6 兼容写法：QTableWidget 没有 selectedRows()，
        # 要用 selectionModel().selectedRows()
        has_selection = bool(self.word_table.selectionModel().selectedRows())
        self.btn_delete_word.setEnabled(has_selection)
        self.btn_edit_word.setEnabled(has_selection)

    def on_add_word(self):
        dlg = AddWordDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            original = dlg.original_input.text().strip()
            category = dlg.category_combo.currentText()
            note = dlg.note_input.text().strip()
            try:
                self.app.wordlib.add_entry(original, category=category, note=note)
                self.statusBar().showMessage(f"已添加: {original} → [{category}_N]", 3000)
                self._refresh_word_table()
            except Exception as ex:
                QMessageBox.warning(self, "添加失败", str(ex))

    def on_edit_word(self):
        row = self.word_table.currentRow()
        if row < 0:
            return
        entry_id = int(self.word_table.item(row, 0).text())
        current_category = self.word_table.item(row, 1).text()
        current_note = self.word_table.item(row, 5).text()
        current_original = self.word_table.item(row, 2).text()

        dlg = EditWordDialog(current_original, current_category, current_note, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                # 更新备注（不能改 original 和 placeholder）
                from src.models.models import WordEntry
                entry = self.app.db.get(WordEntry, entry_id)
                if entry:
                    entry.note = dlg.note_input.text().strip()
                    entry.category = dlg.category_combo.currentText()
                    self.app.db.commit()
                    self._refresh_word_table()
                    self.statusBar().showMessage(f"已更新词条 ID={entry_id}", 3000)
            except Exception as ex:
                QMessageBox.warning(self, "更新失败", str(ex))

    def on_delete_word(self):
        rows = sorted([r.row() for r in self.word_table.selectedRows()], reverse=True)
        if not rows:
            return
        reply = QMessageBox.question(self, "确认删除",
            f"确定要删除选中的 {len(rows)} 个词条吗？\n删除后不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            for row in rows:
                entry_id = int(self.word_table.item(row, 0).text())
                try:
                    self.app.wordlib.delete_entry(entry_id)
                except Exception:
                    pass
            self._refresh_word_table()
            self.statusBar().showMessage(f"已删除 {len(rows)} 个词条", 3000)

    def on_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择导入文件", "",
            "Excel/CSV (*.xlsx *.csv);;所有文件 (*.*)")
        if path:
            try:
                result = self.app.batch_import(Path(path))
                QMessageBox.information(self, "导入完成",
                    f"总计行数: {result.total_rows}\n导入成功: {result.imported}\n跳过: {result.skipped}\n\n" +
                    (f"错误:\n" + "\n".join(result.errors[:5]) if result.errors else ""))
                self._refresh_word_table()
            except Exception as ex:
                QMessageBox.warning(self, "导入失败", str(ex))

    def on_export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出词库", "",
            "Excel (*.xlsx);;CSV (*.csv)")
        if path:
            try:
                import pandas as pd
                all_entries = self.app.wordlib.search()
                df = pd.DataFrame([{
                    "original": e.original,
                    "category": e.category,
                    "placeholder": e.placeholder,
                    "note": e.note or "",
                    "hit_count": e.hit_count,
                    "created_at": e.created_at.isoformat(),
                } for e in all_entries])
                df.to_excel(path, index=False) if path.endswith('.xlsx') else df.to_csv(path, index=False)
                self.statusBar().showMessage(f"已导出 {len(all_entries)} 条词条", 3000)
            except Exception as ex:
                QMessageBox.warning(self, "导出失败", str(ex))

    def on_backup(self):
        backup_path = self.app.backup()
        if backup_path:
            QMessageBox.information(self, "备份完成", f"已备份到:\n{backup_path}")
        else:
            QMessageBox.warning(self, "备份失败", "请检查数据库文件是否存在")

    # ============================================================
    # 文档脱敏 Tab
    # ============================================================

    def _create_desensitize_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        # 文件选择
        file_layout = QHBoxLayout()
        self.desensitize_file_label = QLabel("未选择文件")
        self.btn_select_file_des = QPushButton("📁 选择文件")
        self.btn_preview = QPushButton("🔍 预览")
        self.btn_execute_desensitize = QPushButton("🚀 执行脱敏")
        self.btn_preview.setEnabled(False)
        self.btn_execute_desensitize.setEnabled(False)
        file_layout.addWidget(QLabel("文件:"))
        file_layout.addWidget(self.desensitize_file_label, stretch=1)
        file_layout.addWidget(self.btn_select_file_des)
        file_layout.addWidget(self.btn_preview)
        file_layout.addWidget(self.btn_execute_desensitize)
        layout.addLayout(file_layout)

        # 输出格式选择
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("输出格式:"))
        self.output_format_combo = QComboBox()
        self.output_format_combo.addItems([
            "Markdown (.md) - 推荐 LLM 使用",
            "Word (.docx) - 重建表格/格式",
            "保持原格式",
        ])
        self.output_format_combo.setCurrentIndex(0)  # 默认 MD
        output_layout.addWidget(self.output_format_combo, stretch=1)
        layout.addLayout(output_layout)

        # 脱敏预览
        preview_group = QGroupBox("脱敏预览")
        preview_layout = QVBoxLayout()
        self.desensitize_preview = QTextEdit()
        self.desensitize_preview.setReadOnly(True)
        preview_layout.addWidget(self.desensitize_preview)
        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group, stretch=2)

        # 待确认列表
        confirm_group = QGroupBox("待确认替换项")
        confirm_layout = QVBoxLayout()
        self.confirm_list = QListWidget()
        self.confirm_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        confirm_layout.addWidget(self.confirm_list)
        confirm_group.setLayout(confirm_layout)
        layout.addWidget(confirm_group, stretch=1)

        return w

    def _create_restore_tab(self) -> QWidget:
        """文档还原 Tab"""
        w = QWidget()
        layout = QVBoxLayout(w)

        file_layout = QHBoxLayout()
        self.restore_file_label = QLabel("未选择文件")
        self.btn_select_file_res = QPushButton("📁 选择文件")
        self.btn_preview_restore = QPushButton("🔍 预览还原")
        self.btn_execute_restore = QPushButton("🔁 执行还原")
        self.btn_preview_restore.setEnabled(False)
        self.btn_execute_restore.setEnabled(False)
        file_layout.addWidget(QLabel("文件:"))
        file_layout.addWidget(self.restore_file_label, stretch=1)
        file_layout.addWidget(self.btn_select_file_res)
        file_layout.addWidget(self.btn_preview_restore)
        file_layout.addWidget(self.btn_execute_restore)
        layout.addLayout(file_layout)

        preview_group = QGroupBox("还原预览")
        preview_layout = QVBoxLayout()
        self.restore_preview = QTextEdit()
        self.restore_preview.setReadOnly(True)
        preview_layout.addWidget(self.restore_preview)
        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group, stretch=2)

        # 快照选择
        snapshot_layout = QHBoxLayout()
        snapshot_layout.addWidget(QLabel("使用快照:"))
        self.snapshot_combo = QComboBox()
        self.snapshot_combo.addItem("（当前词库）")
        snapshot_layout.addWidget(self.snapshot_combo, stretch=1)
        layout.addLayout(snapshot_layout)

        self.restore_warning = QLabel("")
        self.restore_warning.setStyleSheet("color: orange;")
        layout.addWidget(self.restore_warning)

        return w

    def _create_history_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        toolbar = QHBoxLayout()
        self.btn_refresh_history = QPushButton("🔄 刷新")
        self.btn_view_snapshot = QPushButton("查看快照")
        toolbar.addWidget(self.btn_refresh_history)
        toolbar.addWidget(self.btn_view_snapshot)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(6)
        self.history_table.setHorizontalHeaderLabels(["会话ID", "时间", "操作", "源文件", "状态", "替换数"])
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.history_table)

        return w

    def _create_settings_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        # 代号策略
        strategy_group = QGroupBox("代号生成策略")
        strategy_layout = QFormLayout()
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems(["结构化编号 [PERSON_1]", "语义摘要 [PERSON_ZS_1]", "随机匿名 [X_A3F7]"])
        strategy_layout.addRow("默认策略:", self.strategy_combo)
        strategy_group.setLayout(strategy_layout)
        layout.addWidget(strategy_group)

        # 数据库设置
        db_group = QGroupBox("数据库与存储")
        db_layout = QFormLayout()
        self.db_path_input = QLineEdit()
        db_layout.addRow("数据库路径:", self.db_path_input)
        self.snapshot_dir_input = QLineEdit()
        db_layout.addRow("快照目录:", self.snapshot_dir_input)
        db_group.setLayout(db_layout)
        layout.addWidget(db_group)

        # 安全设置
        security_group = QGroupBox("安全设置")
        security_layout = QFormLayout()
        self.password_enable_cb = QCheckBox("启用访问密码保护")
        security_layout.addRow("", self.password_enable_cb)
        pw_layout = QHBoxLayout()
        self.btn_set_password = QPushButton("设置密码")
        self.btn_clear_password = QPushButton("清除密码")
        pw_layout.addWidget(self.btn_set_password)
        pw_layout.addWidget(self.btn_clear_password)
        security_layout.addRow("密码操作:", pw_layout)
        security_group.setLayout(security_layout)
        layout.addWidget(security_group)

        # 备份设置
        backup_group = QGroupBox("备份设置")
        backup_layout = QFormLayout()
        self.auto_backup_cb = QCheckBox("自动备份（每次修改词库前）")
        self.backup_retention_input = QLineEdit()
        backup_layout.addRow("自动备份:", self.auto_backup_cb)
        backup_layout.addRow("备份保留数量:", self.backup_retention_input)
        backup_group.setLayout(backup_layout)
        layout.addWidget(backup_group)

        # 高级设置
        advanced_group = QGroupBox("高级设置")
        advanced_layout = QFormLayout()
        self.fuzzy_match_cb = QCheckBox("模糊匹配（子串匹配）")
        self.case_sensitive_cb = QCheckBox("区分大小写")
        self.amount_threshold_input = QLineEdit()
        advanced_layout.addRow("模糊匹配:", self.fuzzy_match_cb)
        advanced_layout.addRow("大小写敏感:", self.case_sensitive_cb)
        advanced_layout.addRow("金额识别阈值(元):", self.amount_threshold_input)
        advanced_group.setLayout(advanced_layout)
        layout.addWidget(advanced_group)

        layout.addStretch()

        save_layout = QHBoxLayout()
        self.btn_save_settings = QPushButton("💾 保存设置")
        self.btn_save_settings.setFixedHeight(45)
        self.btn_reset_settings = QPushButton("🔄 恢复默认")
        save_layout.addWidget(self.btn_save_settings)
        save_layout.addWidget(self.btn_reset_settings)
        layout.addLayout(save_layout)

        # 加载当前设置
        self._load_settings()

        return w

    # ============================================================
    # 事件处理
    # ============================================================

    def _load_settings(self):
        config = self.app.settings.load()
        strategy_map = {"structured": 0, "semantic": 1, "random": 2}
        self.strategy_combo.setCurrentIndex(strategy_map.get(config.placeholder_strategy, 0))
        self.db_path_input.setText(config.db_path)
        self.snapshot_dir_input.setText(config.snapshot_dir)
        self.auto_backup_cb.setChecked(config.auto_backup)
        self.backup_retention_input.setText(str(config.backup_retention))
        self.fuzzy_match_cb.setChecked(config.fuzzy_match)
        self.case_sensitive_cb.setChecked(config.case_sensitive)
        self.amount_threshold_input.setText(str(config.amount_threshold))
        self.password_enable_cb.setChecked(config.has_password)

    def on_save_settings(self):
        strategy_map = {0: "structured", 1: "semantic", 2: "random"}
        try:
            self.app.settings.update(
                placeholder_strategy=strategy_map[self.strategy_combo.currentIndex()],
                db_path=self.db_path_input.text(),
                snapshot_dir=self.snapshot_dir_input.text(),
                auto_backup=self.auto_backup_cb.isChecked(),
                backup_retention=int(self.backup_retention_input.text()),
                fuzzy_match=self.fuzzy_match_cb.isChecked(),
                case_sensitive=self.case_sensitive_cb.isChecked(),
                amount_threshold=int(self.amount_threshold_input.text()),
            )
            QMessageBox.information(self, "保存成功", "设置已保存")
        except Exception as ex:
            QMessageBox.warning(self, "保存失败", str(ex))

    def on_set_password(self):
        dlg = SetPasswordDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            pw = dlg.password_input.text()
            if len(pw) < 4:
                QMessageBox.warning(self, "密码太短", "密码至少需要4个字符")
                return
            try:
                self.app.settings.set_password(pw)
                self.password_enable_cb.setChecked(True)
                QMessageBox.information(self, "成功", "密码已设置")
            except Exception as ex:
                QMessageBox.warning(self, "失败", str(ex))

    def on_clear_password(self):
        reply = QMessageBox.question(self, "确认", "确定要清除密码吗？")
        if reply == QMessageBox.StandardButton.Yes:
            self.app.settings.clear_password()
            self.password_enable_cb.setChecked(False)
            QMessageBox.information(self, "成功", "密码已清除")

    def on_open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "打开文件", "",
            "支持的文档 (*.txt *.docx *.xlsx *.pptx *.csv *.md);;所有文件 (*.*)")
        if path:
            self.desensitize_file_label.setText(path)
            self.btn_preview.setEnabled(True)

    def on_select_file_desensitize(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择要脱敏的文件", "",
            "支持的文档 (*.txt *.docx *.xlsx *.pptx *.csv *.md);;所有文件 (*.*)")
        if path:
            self.desensitize_file_label.setText(path)
            self.btn_preview.setEnabled(True)

    def on_preview_desensitize(self):
        filepath = Path(self.desensitize_file_label.text())
        if not filepath.exists():
            QMessageBox.warning(self, "文件不存在", str(filepath))
            return
        try:
            from src.services.document_handler import read_document
            content, handler = read_document(filepath)
            items, warnings = self.app.desensitizer.scan_text(content)
            self.confirm_list.clear()
            for item in items:
                self.confirm_list.addItem(f"☑ {item.original} → {item.placeholder} [{item.source}]")
            self.desensitize_preview.setText(
                self.app.desensitizer.desensitize(content, items))
            self.btn_execute_desensitize.setEnabled(True)
        except Exception as ex:
            QMessageBox.warning(self, "预览失败", str(ex))

    def on_execute_desensitize(self):
        filepath = Path(self.desensitize_file_label.text())
        try:
            from src.services.document_handler import read_document
            from src.services.header_generator import generate_header, detect_conflicts
            content, handler = read_document(filepath)
            items, warnings = self.app.desensitizer.scan_text(content)
            confirmed = items  # 全量确认
            result = self.app.desensitizer.desensitize(content, confirmed)

            # 检测冲突
            conflicts = detect_conflicts(content, result, items)

            # 生成脱敏文档首部（元数据 + 提示词）
            header = generate_header(filepath, items, conflicts)
            full_output = header + result

            # 根据用户选择的输出格式决定输出路径和写入方式
            fmt_index = self.output_format_combo.currentIndex()
            if fmt_index == 0:  # Markdown
                output_path = filepath.parent / f"{filepath.stem}_desensitized.md"
                # 头部已经在 full_output 里，直接写为 MD
                output_path.write_text(full_output, encoding='utf-8')
            elif fmt_index == 1:  # Word
                output_path = filepath.parent / f"{filepath.stem}_desensitized.docx"
                # MD → docx 重建（以保留表格/标题）
                from src.services.md_converter import markdown_to_docx
                markdown_to_docx(full_output, output_path)
            else:  # 保持原格式
                output_path = filepath.parent / f"{filepath.stem}_desensitized{filepath.suffix}"
                handler.write(output_path, full_output)

            # 构造完成消息：如有冲突，醒目标出
            completion_msg = f"已保存到:\n{output_path}"
            if conflicts:
                completion_msg = (
                    f"⚠️ 脱敏完成但发现 {len(conflicts)} 处冲突！\n\n"
                    f"已保存到:\n{output_path}\n\n"
                    f"冲突详情:\n" + "\n".join(f"  • {c}" for c in conflicts[:5])
                )
                if len(conflicts) > 5:
                    completion_msg += f"\n  • ... 还有 {len(conflicts) - 5} 处"
                box = QMessageBox(self)
                box.setIcon(QMessageBox.Icon.Warning)
                box.setWindowTitle("脱敏完成（含冲突）")
                box.setText(completion_msg)
                box.setStandardButtons(
                    QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Open
                )
                box.button(QMessageBox.StandardButton.Open).setText("📁 打开输出文件夹")
                if box.exec() == QMessageBox.StandardButton.Open:
                    self._open_in_file_explorer(output_path)
            else:
                box = QMessageBox(self)
                box.setIcon(QMessageBox.Icon.Information)
                box.setWindowTitle("脱敏完成")
                box.setText(completion_msg)
                box.setStandardButtons(
                    QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Open
                )
                box.button(QMessageBox.StandardButton.Open).setText("📁 打开输出文件夹")
                if box.exec() == QMessageBox.StandardButton.Open:
                    self._open_in_file_explorer(output_path)
            self.statusBar().showMessage(f"脱敏完成: {output_path}", 5000)
        except Exception as ex:
            QMessageBox.warning(self, "脱敏失败", str(ex))

    def on_select_file_restore(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择要还原的文件", "",
            "支持的文档 (*.txt *.docx *.xlsx *.pptx *.csv *.md);;所有文件 (*.*)")
        if path:
            self.restore_file_label.setText(path)
            self.btn_preview_restore.setEnabled(True)

    def on_preview_restore(self):
        filepath = Path(self.restore_file_label.text())
        try:
            from src.services.document_handler import read_document
            content, handler = read_document(filepath)
            if self.snapshot_combo.currentIndex() == 0:
                mappings = self.app.restore_svc.load_mappings_from_library()
            else:
                snapshot_id = self.snapshot_combo.currentData()
                mappings = self.app.restore_svc.load_mappings_from_snapshot(snapshot_id)
            result = self.app.restore_svc.restore_text(content, mappings)
            self.restore_preview.setText(result.restored_text)
            if result.unreplaced:
                self.restore_warning.setText(f"⚠️ {len(result.unreplaced)} 个代号无法匹配: {', '.join(result.unreplaced[:3])}")
            self.btn_execute_restore.setEnabled(True)
        except Exception as ex:
            QMessageBox.warning(self, "预览失败", str(ex))

    def on_execute_restore(self):
        filepath = Path(self.restore_file_label.text())
        try:
            from src.services.document_handler import read_document
            content, handler = read_document(filepath)
            if self.snapshot_combo.currentIndex() == 0:
                mappings = self.app.restore_svc.load_mappings_from_library()
            else:
                snapshot_id = self.snapshot_combo.currentData()
                mappings = self.app.restore_svc.load_mappings_from_snapshot(snapshot_id)
            result = self.app.restore_svc.restore_text(content, mappings)
            output_path = filepath.parent / f"{filepath.stem}_restored{filepath.suffix}"
            handler.write(output_path, result.restored_text)
            self.statusBar().showMessage(f"还原完成: {output_path}", 5000)
            QMessageBox.information(self, "还原完成", f"已保存到:\n{output_path}")
        except Exception as ex:
            QMessageBox.warning(self, "还原失败", str(ex))

    def on_refresh_history(self):
        sessions = self.app.session_svc.list_sessions()
        self.history_table.setRowCount(len(sessions))
        for i, s in enumerate(sessions):
            stats = {}
            try:
                stats = eval(s.stats) if isinstance(s.stats, str) else s.stats
            except:
                pass
            self.history_table.setItem(i, 0, QTableWidgetItem(s.id[:8]))
            self.history_table.setItem(i, 1, QTableWidgetItem(s.created_at.strftime("%Y-%m-%d %H:%M")))
            self.history_table.setItem(i, 2, QTableWidgetItem(s.operation_type))
            self.history_table.setItem(i, 3, QTableWidgetItem(Path(s.source_filename).name))
            self.history_table.setItem(i, 4, QTableWidgetItem(s.status))
            self.history_table.setItem(i, 5, QTableWidgetItem(str(stats.get("replaced", 0))))

    def on_view_snapshot(self):
        row = self.history_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选择一行会话")
            return
        session_id = self.history_table.item(row, 0).text()
        # 显示快照详情
        sessions = self.app.session_svc.list_sessions()
        session = next((s for s in sessions if s.id.startswith(session_id)), None)
        if session and session.snapshot_id:
            mappings = self.app.snapshot_svc.load_mappings(session.snapshot_id)
            QMessageBox.information(self, "快照映射",
                f"快照ID: {session.snapshot_id[:8]}\n" +
                f"映射数量: {len(mappings)}\n\n" +
                "\n".join([f"{m['placeholder']} → {m.get('original','(加密)')}" for m in mappings[:10]]))

    def on_about(self):
        from src import __app_name__, __version__, __app_name_en__, __description__
        QMessageBox.about(self, f"关于 {__app_name__}",
            f"<h2 style='margin-bottom: 0'>{__app_name__} <span style='color: #888'>{__version__}</span></h2>"
            f"<p style='color: #666; margin-top: 4px'>{__app_name_en__}</p>"
            f"<p>{__description__}</p>"
            f"<hr>"
            f"<p>🛡️ <b>安全</b> · 📍 <b>本地</b> · 🔄 <b>可逆</b></p>"
            f"<p>所有数据仅存储在本地，不上传任何外部服务。</p>"
            f"<p>Powered by Python + PyQt6</p>"
            f"<p><a href='https://github.com/kumabarloc/local-desensitizer'>GitHub 仓库</a></p>")

    def _open_in_file_explorer(self, path: Path):
        """在系统文件管理器中打开文件（Windows 资源管理器/macOS Finder/Linux 文件管理器）"""
        import subprocess
        import os
        import sys
        path = Path(path)
        if not path.exists():
            QMessageBox.warning(self, "文件不存在", f"找不到文件:\n{path}")
            return
        try:
            if sys.platform == "win32":
                # Windows: explorer /select 定位到文件
                subprocess.Popen(['explorer', '/select,', str(path)])
            elif sys.platform == "darwin":
                # macOS: open -R 在 Finder 中显示
                subprocess.Popen(['open', '-R', str(path)])
            else:
                # Linux: 打开父目录
                subprocess.Popen(['xdg-open', str(path.parent)])
        except Exception as ex:
            QMessageBox.warning(self, "打开失败", f"无法打开文件管理器:\n{ex}")


# ============================================================
# 子对话框
# ============================================================

class AddWordDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新增敏感词条")
        self.setMinimumWidth(450)
        layout = QFormLayout(self)

        self.original_input = QLineEdit()
        self.original_input.setPlaceholderText("输入原始内容...")
        layout.addRow("原始词 *:", self.original_input)

        self.category_combo = QComboBox()
        self.category_combo.addItems([
            "PERSON", "COMPANY", "PROJECT", "PHONE", "EMAIL",
            "IDCARD", "BANKCARD", "AMOUNT", "IPV4", "LOCATION", "CUSTOM"
        ])
        layout.addRow("分类:", self.category_combo)

        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("可选备注...")
        layout.addRow("备注:", self.note_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)


class EditWordDialog(QDialog):
    def __init__(self, original, category, note, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑词条")
        self.setMinimumWidth(450)
        layout = QFormLayout(self)

        layout.addRow(QLabel(f"原始词: <b>{original}</b>（不可修改）"))
        layout.addRow(QLabel(f"代号: [{category}_N]（不可修改）"))

        self.category_combo = QComboBox()
        self.category_combo.addItems([
            "PERSON", "COMPANY", "PROJECT", "PHONE", "EMAIL",
            "IDCARD", "BANKCARD", "AMOUNT", "IPV4", "LOCATION", "CUSTOM"
        ])
        self.category_combo.setCurrentText(category)
        layout.addRow("分类:", self.category_combo)

        self.note_input = QLineEdit()
        self.note_input.setText(note)
        self.note_input.setPlaceholderText("可选备注...")
        layout.addRow("备注:", self.note_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)


class SetPasswordDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置访问密码")
        self.setMinimumWidth(350)
        layout = QFormLayout(self)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("输入新密码...")
        layout.addRow("新密码:", self.password_input)

        self.confirm_input = QLineEdit()
        self.confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_input.setPlaceholderText("再次输入确认...")
        layout.addRow("确认密码:", self.confirm_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._check_match)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _check_match(self):
        if self.password_input.text() != self.confirm_input.text():
            QMessageBox.warning(self, "不匹配", "两次输入的密码不一致")
            return
        self.accept()