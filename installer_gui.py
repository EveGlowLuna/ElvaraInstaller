"""ElvaraOS 安装程序 — PySide6 GUI"""
import os
import socket
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QObject, QSize
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QStackedWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QComboBox,
    QFormLayout, QGroupBox, QTextEdit, QProgressBar,
    QMessageBox, QSizePolicy,
    QFrame, QSpinBox,
)

from archinstall.lib.disk.device_handler import device_handler
from archinstall.lib.hardware import SysInfo
from archinstall.lib.models.locale import LocaleConfiguration
from archinstall.lib.models.users import Password, User

from install.core import perform_installation
from install.disk import (
    build_disk_layout,
    build_disk_layout_coexist,
    detect_existing_systems,
    analyze_coexist_partitions,
)
from install.log import setup_gui_logging

# ── 常量 ─────────────────────────────────────────────────────────────────────

ICON_PATH = '/usr/share/pixmaps/elvara.png'

TIMEZONES = [
    'Asia/Shanghai', 'Asia/Chongqing', 'Asia/Hong_Kong', 'Asia/Taipei',
    'Asia/Tokyo', 'Asia/Seoul', 'Asia/Singapore', 'Asia/Kolkata',
    'Asia/Dubai', 'Asia/Jerusalem', 'Europe/London', 'Europe/Paris',
    'Europe/Berlin', 'Europe/Moscow', 'America/New_York', 'America/Chicago',
    'America/Denver', 'America/Los_Angeles', 'America/Sao_Paulo',
    'Australia/Sydney', 'Pacific/Auckland', 'UTC',
]

KB_LAYOUTS = [
    ('us', '美式英语 (US)'), ('gb', '英式英语 (GB)'), ('de', '德语 (DE)'),
    ('fr', '法语 (FR)'), ('es', '西班牙语 (ES)'), ('it', '意大利语 (IT)'),
    ('ru', '俄语 (RU)'), ('jp', '日语 (JP)'), ('kr', '韩语 (KR)'),
    ('cn', '中文 (CN)'), ('dvorak', 'Dvorak'), ('colemak', 'Colemak'),
]

# 安装步骤及权重（权重之和 = 100）
INSTALL_STEPS = [
    ('准备磁盘分区',       5),
    ('配置镜像源',         3),
    ('格式化文件系统',     5),
    ('安装基础系统',      15),
    ('安装桌面环境',      40),
    ('配置系统',           8),
    ('安装引导加载程序',   8),
    ('创建用户',           3),
    ('复制系统定制内容',   8),
    ('安装 yay',           5),
]

# ── 样式 ─────────────────────────────────────────────────────────────────────

STYLE = """
QMainWindow, QWidget#root {
    background: #f5f5f7;
}
QWidget#page {
    background: white;
    border-radius: 12px;
}
QPushButton#nav {
    background: #0071e3;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 8px 24px;
    font-size: 14px;
}
QPushButton#nav:hover { background: #0077ed; }
QPushButton#nav:disabled { background: #b0b0b0; }
QPushButton#nav_secondary {
    background: transparent;
    color: #0071e3;
    border: 1px solid #0071e3;
    border-radius: 8px;
    padding: 8px 24px;
    font-size: 14px;
}
QPushButton#nav_secondary:hover { background: #e8f0fb; }
QPushButton#danger {
    background: #ff3b30;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 8px 24px;
    font-size: 14px;
}
QPushButton#danger:hover { background: #ff453a; }
QListWidget {
    border: 1px solid #d1d1d6;
    border-radius: 8px;
    background: white;
    font-size: 14px;
}
QListWidget::item { padding: 10px 14px; border-bottom: 1px solid #f0f0f0; }
QListWidget::item:selected { background: #e8f0fb; color: #0071e3; }
QListWidget::item:hover { background: #f5f5f7; color: #1d1d1f; }
QComboBox QAbstractItemView {
    background: white;
    border: 1px solid #d1d1d6;
    border-radius: 6px;
    selection-background-color: #e8f0fb;
    selection-color: #0071e3;
    outline: none;
}
QComboBox QAbstractItemView::item {
    padding: 6px 10px;
    color: #1d1d1f;
}
QComboBox QAbstractItemView::item:hover {
    background: #f5f5f7;
    color: #1d1d1f;
}
QLineEdit, QComboBox, QSpinBox {
    border: 1px solid #d1d1d6;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 14px;
    background: white;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-color: #0071e3;
}
QProgressBar {
    border: none;
    border-radius: 4px;
    background: #e5e5ea;
    height: 8px;
    text-align: center;
}
QProgressBar::chunk {
    border-radius: 4px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #0071e3, stop:1 #34aadc);
}
QLabel#title {
    font-size: 26px;
    font-weight: bold;
    color: #1d1d1f;
}
QLabel#subtitle {
    font-size: 15px;
    color: #6e6e73;
    line-height: 1.5;
}
QLabel#step_hint {
    font-size: 13px;
    color: #6e6e73;
}
QTextEdit#log {
    background: #1e1e1e;
    color: #d4d4d4;
    font-family: monospace;
    font-size: 12px;
    border-radius: 8px;
    border: none;
}
"""

# ── 安装工作线程 ─────────────────────────────────────────────────────────────

class InstallWorker(QObject):
    log      = Signal(str)
    step     = Signal(int, str)   # step_index, step_name
    finished = Signal(bool, str)

    def __init__(self, kwargs: dict):
        super().__init__()
        self._kwargs = kwargs

    def run(self) -> None:
        setup_gui_logging(self.log.emit)

        # 用 monkey-patch 在每个关键步骤发出 step 信号
        _patch_steps(self.step.emit)

        try:
            perform_installation(**self._kwargs)
            self.finished.emit(True, '')
        except Exception as e:
            from loguru import logger
            logger.exception('安装过程中发生异常')
            self.finished.emit(False, str(e))


def _patch_steps(emit_step):
    """在安装流程的关键节点注入 step 信号"""
    import archinstall.lib.installer as _inst_mod
    import archinstall.lib.disk.filesystem as _fs_mod

    _orig_fs = _fs_mod.FilesystemHandler.perform_filesystem_operations
    _orig_minimal = _inst_mod.Installer.minimal_installation
    _orig_packages = _inst_mod.Installer.add_additional_packages
    _orig_bootloader = _inst_mod.Installer.add_bootloader
    _orig_users = _inst_mod.Installer.create_users
    _orig_genfstab = _inst_mod.Installer.genfstab

    def _fs_wrap(self, *a, **kw):
        emit_step(2, INSTALL_STEPS[2][0])
        return _orig_fs(self, *a, **kw)

    def _minimal_wrap(self, *a, **kw):
        emit_step(3, INSTALL_STEPS[3][0])
        return _orig_minimal(self, *a, **kw)

    def _packages_wrap(self, packages, *a, **kw):
        if isinstance(packages, list) and len(packages) > 5:
            emit_step(4, INSTALL_STEPS[4][0])
        return _orig_packages(self, packages, *a, **kw)

    def _bootloader_wrap(self, *a, **kw):
        emit_step(6, INSTALL_STEPS[6][0])
        return _orig_bootloader(self, *a, **kw)

    def _users_wrap(self, *a, **kw):
        emit_step(7, INSTALL_STEPS[7][0])
        return _orig_users(self, *a, **kw)

    def _genfstab_wrap(self, *a, **kw):
        emit_step(8, INSTALL_STEPS[8][0])
        return _orig_genfstab(self, *a, **kw)

    _fs_mod.FilesystemHandler.perform_filesystem_operations = _fs_wrap
    _inst_mod.Installer.minimal_installation = _minimal_wrap
    _inst_mod.Installer.add_additional_packages = _packages_wrap
    _inst_mod.Installer.add_bootloader = _bootloader_wrap
    _inst_mod.Installer.create_users = _users_wrap
    _inst_mod.Installer.genfstab = _genfstab_wrap


# ── 通用组件 ─────────────────────────────────────────────────────────────────

def _nav_btn(text: str, primary: bool = True) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName('nav' if primary else 'nav_secondary')
    btn.setFixedHeight(36)
    return btn


def _divider() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet('color: #e5e5ea;')
    return f


# ── 页面 1：欢迎 ─────────────────────────────────────────────────────────────

class WelcomePage(QWidget):
    def __init__(self, on_next, on_quit):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(60, 40, 60, 40)
        root.setSpacing(0)

        root.addStretch(2)

        # 图标
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        px = QPixmap(ICON_PATH)
        if not px.isNull():
            icon_label.setPixmap(px.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation))
        root.addWidget(icon_label)
        root.addSpacing(24)

        # 标题
        title = QLabel('欢迎安装 ElvaraOS！')
        title.setObjectName('title')
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(title)
        root.addSpacing(16)

        # 说明
        desc = QLabel(
            'ElvaraOS 将引导你安装系统到硬盘中。\n'
            '在开始之前，请确保电脑已经联网。\n'
            '点击右上角状态栏或直接打开设置可进行联网操作。'
        )
        desc.setObjectName('subtitle')
        desc.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        desc.setWordWrap(True)
        root.addWidget(desc)

        root.addStretch(3)
        root.addWidget(_divider())
        root.addSpacing(16)

        # 按钮行
        btn_row = QHBoxLayout()
        quit_btn = QPushButton('退出')
        quit_btn.setObjectName('danger')
        quit_btn.setFixedHeight(36)
        quit_btn.clicked.connect(on_quit)
        next_btn = _nav_btn('下一步 →')
        next_btn.clicked.connect(on_next)
        btn_row.addWidget(quit_btn)
        btn_row.addStretch()
        btn_row.addWidget(next_btn)
        root.addLayout(btn_row)


# ── 页面 2：磁盘选择 ─────────────────────────────────────────────────────────

class DiskPage(QWidget):
    def __init__(self, on_prev, on_next):
        super().__init__()
        self._on_next = on_next
        self._devices = device_handler.devices
        self._wipe = True
        self._target_part_info = None   # 共存时指定的目标分区
        self._alloc_gb = 20

        root = QVBoxLayout(self)
        root.setContentsMargins(60, 40, 60, 40)
        root.setSpacing(12)

        title = QLabel('选择安装位置')
        title.setObjectName('title')
        root.addWidget(title)

        hint = QLabel('请选择要将系统安装到哪个磁盘。')
        hint.setObjectName('subtitle')
        root.addWidget(hint)
        root.addSpacing(8)

        # 磁盘列表
        self._list = QListWidget()
        self._list.setMinimumHeight(160)
        for dev in self._devices:
            model = dev.device_info.model or 'Unknown'
            size  = dev.device_info.total_size.format_highest()
            path  = str(dev.device_info.path)
            item  = QListWidgetItem(f'  {model}\n  {size}  ·  {path}')
            item.setSizeHint(QSize(0, 56))
            self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)
        root.addWidget(self._list)

        # 共存：选择目标分区（多个空闲分区时显示）
        self._part_box = QGroupBox('选择安装到哪个分区')
        part_layout = QVBoxLayout(self._part_box)
        self._part_list = QListWidget()
        self._part_list.setMaximumHeight(120)
        part_layout.addWidget(self._part_list)
        self._part_box.setVisible(False)
        root.addWidget(self._part_box)

        # 共存：分配空间大小（无空闲分区时显示）
        self._alloc_box = QGroupBox('为 ElvaraOS 分配空间')
        alloc_layout = QFormLayout(self._alloc_box)
        self._size_spin = QSpinBox()
        self._size_spin.setRange(8, 9999)
        self._size_spin.setValue(20)
        self._size_spin.setSuffix(' GB')
        self._disk_total_label = QLabel()
        alloc_layout.addRow('分配大小：', self._size_spin)
        alloc_layout.addRow('磁盘总大小：', self._disk_total_label)
        self._alloc_box.setVisible(False)
        root.addWidget(self._alloc_box)

        root.addStretch()
        root.addWidget(_divider())
        root.addSpacing(8)

        btn_row = QHBoxLayout()
        prev_btn = _nav_btn('← 上一步', primary=False)
        prev_btn.clicked.connect(on_prev)
        self._next_btn = _nav_btn('下一步 →')
        self._next_btn.clicked.connect(self._handle_next)
        btn_row.addWidget(prev_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._next_btn)
        root.addLayout(btn_row)

    def _selected_device(self):
        row = self._list.currentRow()
        return self._devices[row] if 0 <= row < len(self._devices) else None

    def _handle_next(self) -> None:
        dev = self._selected_device()
        if dev is None:
            QMessageBox.warning(self, '提示', '请先选择一个磁盘')
            return

        existing = detect_existing_systems(dev)

        # 如果共存面板已展开，直接提交
        if self._part_box.isVisible() or self._alloc_box.isVisible():
            self._submit(dev)
            return

        if not existing:
            # 空盘，直接清空安装
            self._wipe = True
            self._submit(dev)
            return

        # 有已有系统，询问是否保留
        reply = QMessageBox.question(
            self, '检测到已有系统',
            '检测到磁盘上已有分区或系统。\n\n是否希望保留磁盘中的系统？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.No:
            self._wipe = True
            self._submit(dev)
            return

        # 共存模式：分析分区
        self._wipe = False
        self._show_coexist_options(dev)

    def _show_coexist_options(self, dev) -> None:
        analysis = analyze_coexist_partitions(dev)
        free_parts = analysis['free_parts']
        free_regions = analysis['free_regions']

        sector_size = dev.device_info.sector_size
        from archinstall.lib.models.device import Size, Unit
        min_size = Size(8, Unit.GiB, sector_size)
        usable_regions = [
            r for r in free_regions
            if Size(r.get_length(Unit.sectors), Unit.sectors, sector_size) >= min_size
        ]

        if len(free_parts) == 1:
            # 只有一个空闲分区，直接用它
            self._target_part_info = free_parts[0]['part_info']
            self._part_box.setVisible(False)
            self._alloc_box.setVisible(False)
            self._submit(dev)

        elif len(free_parts) > 1:
            # 多个空闲分区，让用户选
            self._part_list.clear()
            self._part_items = free_parts
            for p in free_parts:
                self._part_list.addItem(f"{p['path']}  {p['size']}  ({p['fs']})")
            if self._part_list.count():
                self._part_list.setCurrentRow(0)
            self._part_box.setVisible(True)
            self._alloc_box.setVisible(False)

        elif usable_regions:
            # 没有空闲分区，但有未分配空间，让用户指定大小
            self._target_part_info = None
            total = dev.device_info.total_size.format_highest()
            self._disk_total_label.setText(total)
            self._part_box.setVisible(False)
            self._alloc_box.setVisible(True)

        else:
            QMessageBox.critical(
                self, '空间不足',
                '磁盘上没有可用的空闲分区或未分配空间（至少需要 8 GiB）。\n'
                '请先在现有系统中缩小分区，或选择清空全盘模式。'
            )

    def _submit(self, dev) -> None:
        # 如果分区选择列表可见，读取选中项
        if self._part_box.isVisible():
            row = self._part_list.currentRow()
            if row < 0:
                QMessageBox.warning(self, '提示', '请选择一个目标分区')
                return
            self._target_part_info = self._part_items[row]['part_info']

        self._alloc_gb = self._size_spin.value()
        self._on_next(dev, self._wipe, self._target_part_info, self._alloc_gb)

    def get_selection(self):
        return (
            self._selected_device(),
            self._wipe,
            self._target_part_info,
            self._alloc_gb,
        )


# ── 页面 3：系统配置 ─────────────────────────────────────────────────────────

class SystemPage(QWidget):
    def __init__(self, on_prev, on_next):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(60, 40, 60, 40)
        root.setSpacing(12)

        title = QLabel('系统配置')
        title.setObjectName('title')
        root.addWidget(title)
        root.addSpacing(8)

        form = QFormLayout()
        form.setSpacing(14)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # 时区
        self._tz_combo = QComboBox()
        self._tz_combo.addItems(TIMEZONES)
        self._tz_combo.setCurrentText('Asia/Shanghai')
        form.addRow('时区：', self._tz_combo)

        # 键盘布局
        self._kb_combo = QComboBox()
        for code, label in KB_LAYOUTS:
            self._kb_combo.addItem(label, code)
        form.addRow('键盘布局：', self._kb_combo)

        # 设备名称
        try:
            default_hostname = socket.gethostname()
            # 如果是 livecd 的 hostname，用通用默认值
            if 'archiso' in default_hostname.lower() or default_hostname == 'archlinux':
                default_hostname = 'elvaraos'
        except Exception:
            default_hostname = 'elvaraos'

        self._hostname_edit = QLineEdit(default_hostname)
        form.addRow('设备名称：', self._hostname_edit)

        root.addLayout(form)
        root.addStretch()
        root.addWidget(_divider())
        root.addSpacing(8)

        btn_row = QHBoxLayout()
        prev_btn = _nav_btn('← 上一步', primary=False)
        prev_btn.clicked.connect(on_prev)
        next_btn = _nav_btn('下一步 →')
        next_btn.clicked.connect(lambda: self._handle_next(on_next))
        btn_row.addWidget(prev_btn)
        btn_row.addStretch()
        btn_row.addWidget(next_btn)
        root.addLayout(btn_row)

    def _handle_next(self, on_next) -> None:
        if not self._hostname_edit.text().strip():
            QMessageBox.warning(self, '提示', '设备名称不能为空')
            return
        on_next()

    def get_config(self) -> dict:
        return {
            'timezone': self._tz_combo.currentText(),
            'kb_layout': self._kb_combo.currentData(),
            'hostname': self._hostname_edit.text().strip(),
        }


# ── 页面 4：用户创建 ─────────────────────────────────────────────────────────

class UserPage(QWidget):
    def __init__(self, on_prev, on_next):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(60, 40, 60, 40)
        root.setSpacing(12)

        title = QLabel('创建用户')
        title.setObjectName('title')
        root.addWidget(title)

        hint = QLabel('请创建你的个人账户。')
        hint.setObjectName('subtitle')
        root.addWidget(hint)
        root.addSpacing(8)

        form = QFormLayout()
        form.setSpacing(14)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self._username_edit = QLineEdit()
        self._username_edit.setPlaceholderText('仅限小写字母、数字和连字符')
        self._password_edit = QLineEdit()
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_confirm = QLineEdit()
        self._password_confirm.setEchoMode(QLineEdit.EchoMode.Password)

        form.addRow('用户名：', self._username_edit)
        form.addRow('密码：', self._password_edit)
        form.addRow('确认密码：', self._password_confirm)
        root.addLayout(form)

        root.addStretch()
        root.addWidget(_divider())
        root.addSpacing(8)

        btn_row = QHBoxLayout()
        prev_btn = _nav_btn('← 上一步', primary=False)
        prev_btn.clicked.connect(on_prev)
        next_btn = _nav_btn('下一步 →')
        next_btn.clicked.connect(lambda: self._handle_next(on_next))
        btn_row.addWidget(prev_btn)
        btn_row.addStretch()
        btn_row.addWidget(next_btn)
        root.addLayout(btn_row)

    def _handle_next(self, on_next) -> None:
        u = self._username_edit.text().strip()
        p = self._password_edit.text()
        c = self._password_confirm.text()
        if not u:
            QMessageBox.warning(self, '提示', '用户名不能为空')
            return
        if not p:
            QMessageBox.warning(self, '提示', '密码不能为空')
            return
        if p != c:
            QMessageBox.warning(self, '提示', '两次输入的密码不一致')
            return
        on_next()

    def get_user(self) -> User:
        return User(
            username=self._username_edit.text().strip(),
            password=Password(plaintext=self._password_edit.text()),
            sudo=True,
        )


# ── 页面 5：确认配置 ─────────────────────────────────────────────────────────

class ConfirmPage(QWidget):
    def __init__(self, on_prev, on_install):
        super().__init__()
        self._on_install = on_install
        root = QVBoxLayout(self)
        root.setContentsMargins(60, 40, 60, 40)
        root.setSpacing(12)

        title = QLabel('确认配置')
        title.setObjectName('title')
        root.addWidget(title)

        hint = QLabel('请确认以下配置无误后，点击"开始安装"。')
        hint.setObjectName('subtitle')
        root.addWidget(hint)
        root.addSpacing(8)

        self._summary = QLabel()
        self._summary.setWordWrap(True)
        self._summary.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._summary.setStyleSheet(
            'font-size: 14px; color: #1d1d1f; line-height: 1.8;'
            'background: #f5f5f7; border-radius: 8px; padding: 16px;'
        )
        self._summary.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self._summary, stretch=1)

        root.addSpacing(8)
        root.addWidget(_divider())
        root.addSpacing(8)

        btn_row = QHBoxLayout()
        prev_btn = _nav_btn('← 上一步', primary=False)
        prev_btn.clicked.connect(on_prev)
        install_btn = _nav_btn('开始安装')
        install_btn.clicked.connect(self._handle_install)
        btn_row.addWidget(prev_btn)
        btn_row.addStretch()
        btn_row.addWidget(install_btn)
        root.addLayout(btn_row)

    def update_summary(self, disk_info: str, system_info: dict, user_info: str) -> None:
        text = (
            f'<b>安装位置</b><br>{disk_info}<br><br>'
            f'<b>时区</b><br>{system_info.get("timezone", "")}<br><br>'
            f'<b>键盘布局</b><br>{system_info.get("kb_layout", "")}<br><br>'
            f'<b>设备名称</b><br>{system_info.get("hostname", "")}<br><br>'
            f'<b>用户名</b><br>{user_info}<br>'
        )
        self._summary.setText(text)

    def _handle_install(self) -> None:
        reply = QMessageBox.question(
            self, '镜像源',
            '安装需要联网下载基本系统与软件包。\n\n是否切换至国内镜像源（推荐中国大陆用户选择）？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        use_cn_mirror = (reply == QMessageBox.StandardButton.Yes)
        self._on_install(use_cn_mirror)


# ── 页面 6：安装进度 ─────────────────────────────────────────────────────────

class InstallPage(QWidget):
    def __init__(self):
        super().__init__()
        self._step_weights = [w for _, w in INSTALL_STEPS]
        self._cumulative = []
        total = 0
        for w in self._step_weights:
            total += w
            self._cumulative.append(total)
        self._total_weight = total
        self._show_log = False

        root = QVBoxLayout(self)
        root.setContentsMargins(60, 40, 60, 40)
        root.setSpacing(16)

        # 目标磁盘提示
        self._dest_label = QLabel()
        self._dest_label.setObjectName('subtitle')
        self._dest_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(self._dest_label)
        root.addSpacing(16)

        # 中间内容区：进度视图 和 日志视图 二选一，用 QStackedWidget 切换
        from PySide6.QtWidgets import QStackedWidget as _SW
        self._content_stack = _SW()

        # — 进度视图 —
        progress_widget = QWidget()
        pw_layout = QVBoxLayout(progress_widget)
        pw_layout.setContentsMargins(0, 0, 0, 0)
        pw_layout.setSpacing(10)
        pw_layout.addStretch()

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(8)
        self._progress.setTextVisible(False)
        pw_layout.addWidget(self._progress)

        self._step_label = QLabel('准备中...')
        self._step_label.setObjectName('step_hint')
        self._step_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        pw_layout.addWidget(self._step_label)
        pw_layout.addStretch()

        # — 日志视图 —
        self._log_view = QTextEdit()
        self._log_view.setObjectName('log')
        self._log_view.setReadOnly(True)

        self._content_stack.addWidget(progress_widget)   # index 0
        self._content_stack.addWidget(self._log_view)    # index 1
        self._content_stack.setCurrentIndex(0)

        root.addWidget(self._content_stack, stretch=1)
        root.addWidget(_divider())
        root.addSpacing(8)

        btn_row = QHBoxLayout()
        self._cancel_btn = QPushButton('取消')
        self._cancel_btn.setObjectName('danger')
        self._cancel_btn.setFixedHeight(36)
        btn_row.addWidget(self._cancel_btn)
        btn_row.addStretch()
        self._log_btn = _nav_btn('显示日志', primary=False)
        self._log_btn.clicked.connect(self._toggle_log)
        btn_row.addWidget(self._log_btn)
        root.addLayout(btn_row)

    def set_destination(self, text: str) -> None:
        self._dest_label.setText(f'ElvaraOS 将安装至：{text}')

    def on_step(self, step_index: int, step_name: str) -> None:
        if 0 <= step_index < len(self._cumulative):
            pct = int(self._cumulative[step_index] * 100 / self._total_weight)
            self._progress.setValue(pct)
        self._step_label.setText(step_name)

    def append_log(self, msg: str) -> None:
        self._log_view.append(msg)
        self._log_view.verticalScrollBar().setValue(
            self._log_view.verticalScrollBar().maximum()
        )

    def _toggle_log(self) -> None:
        self._show_log = not self._show_log
        self._content_stack.setCurrentIndex(1 if self._show_log else 0)
        self._log_btn.setText('隐藏日志' if self._show_log else '显示日志')

    def set_cancel_callback(self, cb) -> None:
        self._cancel_btn.clicked.connect(cb)


# ── 页面 7：安装完成 ─────────────────────────────────────────────────────────

class DonePage(QWidget):
    def __init__(self, on_quit, on_reboot):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(60, 40, 60, 40)
        root.setSpacing(0)

        root.addStretch(2)

        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        px = QPixmap(ICON_PATH)
        if not px.isNull():
            icon_label.setPixmap(px.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation))
        root.addWidget(icon_label)
        root.addSpacing(20)

        title = QLabel('安装完成！')
        title.setObjectName('title')
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(title)
        root.addSpacing(16)

        desc = QLabel(
            'ElvaraOS 已经安装到您的硬盘中。\n'
            '你可以选择留在这里，继续体验 LiveCD 环境，\n'
            '也可以直接重启进入新系统。\n\n'
            '注意：你在 LiveCD 中所做的一切更改都不会保存。'
        )
        desc.setObjectName('subtitle')
        desc.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        desc.setWordWrap(True)
        root.addWidget(desc)

        root.addStretch(3)
        root.addWidget(_divider())
        root.addSpacing(16)

        btn_row = QHBoxLayout()
        quit_btn = _nav_btn('留在这里', primary=False)
        quit_btn.clicked.connect(on_quit)
        reboot_btn = _nav_btn('重启系统')
        reboot_btn.clicked.connect(on_reboot)
        btn_row.addWidget(quit_btn)
        btn_row.addStretch()
        btn_row.addWidget(reboot_btn)
        root.addLayout(btn_row)


# ── 主窗口 ───────────────────────────────────────────────────────────────────

class InstallerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('ElvaraOS 安装程序')
        self._uefi = SysInfo.has_uefi()
        self._worker_thread: QThread | None = None

        # 居中 80% 屏幕
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(int(screen.width() * 0.72), int(screen.height() * 0.78))
        self.move(
            screen.x() + (screen.width() - self.width()) // 2,
            screen.y() + (screen.height() - self.height()) // 2,
        )

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        # 构建所有页面
        self._welcome  = WelcomePage(self._go_disk, self._quit)
        self._disk_pg  = DiskPage(self._go_welcome, self._from_disk)
        self._sys_pg   = SystemPage(self._go_disk_direct, self._go_user)
        self._user_pg  = UserPage(self._go_sys, self._go_confirm)
        self._confirm  = ConfirmPage(self._go_user, self._start_install)
        self._install  = InstallPage()
        self._done     = DonePage(self._quit, self._reboot)

        for page in [self._welcome, self._disk_pg, self._sys_pg,
                     self._user_pg, self._confirm, self._install, self._done]:
            self._stack.addWidget(page)

        self._install.set_cancel_callback(self._cancel_install)

    # ── 导航 ─────────────────────────────────────────────────────────────────

    def _go_welcome(self):  self._stack.setCurrentWidget(self._welcome)
    def _go_disk_direct(self): self._stack.setCurrentWidget(self._disk_pg)
    def _go_sys(self):      self._stack.setCurrentWidget(self._sys_pg)
    def _go_user(self):     self._stack.setCurrentWidget(self._user_pg)

    def _go_disk(self):
        self._stack.setCurrentWidget(self._disk_pg)

    def _from_disk(self, device, wipe: bool, target_part_info, alloc_gb: int):
        """磁盘页确认后，进入系统配置页"""
        self._selected_device = device
        self._wipe = wipe
        self._target_part_info = target_part_info
        self._alloc_gb = alloc_gb
        self._stack.setCurrentWidget(self._sys_pg)

    def _go_confirm(self):
        # 汇总信息更新确认页
        dev = self._selected_device
        model = dev.device_info.model or 'Unknown'
        size  = dev.device_info.total_size.format_highest()
        path  = str(dev.device_info.path)
        mode  = '清空全盘' if self._wipe else (
            f'共存 → {self._target_part_info.path}' if self._target_part_info
            else f'共存（分配 {self._alloc_gb} GB）'
        )
        disk_info = f'{model}  {size}  {path}\n安装模式：{mode}'

        sys_cfg  = self._sys_pg.get_config()
        username = self._user_pg.get_user().username
        self._confirm.update_summary(disk_info, sys_cfg, username)
        self._stack.setCurrentWidget(self._confirm)

    # ── 安装 ─────────────────────────────────────────────────────────────────

    def _start_install(self, use_cn_mirror: bool) -> None:
        from install.mirrors import FALLBACK_MIRRORS
        from pathlib import Path as _Path

        if use_cn_mirror:
            _Path('/etc/pacman.d/mirrorlist').write_text(FALLBACK_MIRRORS)

        dev = self._selected_device
        sys_cfg = self._sys_pg.get_config()
        user    = self._user_pg.get_user()

        # 构建磁盘布局
        try:
            if self._wipe:
                from install.disk import build_disk_layout
                disk_layout = build_disk_layout(dev, self._uefi)
            else:
                from install.disk import build_disk_layout_coexist
                disk_layout = build_disk_layout_coexist(
                    dev, self._uefi,
                    target_part_info=self._target_part_info,
                    alloc_gb=self._alloc_gb,
                )
        except ValueError as e:
            QMessageBox.critical(self, '磁盘错误', str(e))
            return

        locale_config = LocaleConfiguration(
            sys_lang='zh_CN.UTF-8',
            sys_enc='UTF-8',
            kb_layout=sys_cfg['kb_layout'],
        )

        # 设置安装目标提示
        path = str(dev.device_info.path)
        self._install.set_destination(path)
        self._stack.setCurrentWidget(self._install)
        self._install.on_step(0, INSTALL_STEPS[0][0])

        kwargs = dict(
            disk_layout_config=disk_layout,
            hostname=sys_cfg['hostname'],
            timezone=sys_cfg['timezone'],
            locale_config=locale_config,
            user=user,
        )

        self._worker = InstallWorker(kwargs)
        self._worker_thread = QThread()
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.log.connect(self._install.append_log)
        self._worker.step.connect(self._install.on_step)
        self._worker.finished.connect(self._on_finished)
        self._worker_thread.start()

    def _cancel_install(self) -> None:
        reply = QMessageBox.question(
            self, '取消安装', '确定要取消安装吗？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self._worker_thread and self._worker_thread.isRunning():
                self._worker_thread.terminate()
            self._stack.setCurrentWidget(self._welcome)

    def _on_finished(self, success: bool, message: str) -> None:
        if self._worker_thread:
            self._worker_thread.quit()
            self._worker_thread.wait()

        if success:
            self._install.on_step(len(INSTALL_STEPS) - 1, '安装完成')
            self._install._progress.setValue(100)
            self._stack.setCurrentWidget(self._done)
        else:
            QMessageBox.critical(
                self, '安装失败',
                f'{message}\n\n'
                '请尝试重新启动到 LiveCD。\n'
                '如果你发现仍存在这个问题，请前往官网反馈：\n'
                'https://github.com/EveGlowLuna/ElvaraOS',
            )
            self._stack.setCurrentWidget(self._confirm)

    def _quit(self):
        QApplication.quit()

    def _reboot(self):
        os.execv('/usr/bin/reboot', ['reboot'])


# ── 入口 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    if os.getuid() != 0:
        print('安装程序需要 root 权限运行', file=sys.stderr)
        sys.exit(1)

    # 以 root 身份运行时没有用户 session bus，抑制 Qt 的 DBus/GNOME 主题警告
    os.environ.setdefault('QT_QPA_PLATFORMTHEME', 'gtk3')
    os.environ['DBUS_SESSION_BUS_ADDRESS'] = 'disabled:'

    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)

    window = InstallerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
