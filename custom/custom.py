import shutil
import subprocess
import os
import sys

from installer import base_system

# 桌面环境列表，(显示名, key, 描述)
DESKTOP_OPTIONS = [
    ('不安装桌面环境',          'none',         '仅基础系统，无图形界面'),
    ('KDE Plasma',              'kde',          '功能完整的传统桌面，推荐新手'),
    ('Shorin DMS Niri',         'shorindmsgit', 'Shorin 定制 Niri，推荐'),
    ('Shorin Noctalia Niri',    'shorinnocniri','Noctalia 主题 Niri 桌面'),
    ('Shorin Niri',             'shorinniri',   'Shorin 标准 Niri 配置'),
    ('Minimal Niri',            'minimalniri',  '极简 Niri，轻量快速'),
    ('Minimal Labwc',           'minimallabwc', '极简 Labwc 合成器'),
    ('Shorin Hyprland+Niri',    'hyprniri',     'Hyprland 滚动模式'),
    ('GNOME',                   'gnome',        '经典 GNOME 桌面'),
    ('Quickshell: End4',        'end4',         'illogical-impulse 风格'),
    ('Quickshell: DMS',         'dms',          'DankMaterialShell'),
    ('Quickshell: Caelestia',   'caelestia',    'Caelestia 风格'),
]

WIKI_URL = 'https://github.com/SHORiN-KiWATA/Shorin-ArchLinux-Guide/wiki/%E4%B8%80%E9%94%AE%E9%85%8D%E7%BD%AE%E6%A1%8C%E9%9D%A2%E7%8E%AF%E5%A2%83'


def _pick_desktop() -> str:
    """弹出桌面环境选择对话框，返回选中的 key。"""
    from PySide6.QtWidgets import (
        QApplication, QDialog, QVBoxLayout, QHBoxLayout,
        QLabel, QListWidget, QListWidgetItem, QPushButton,
    )
    from PySide6.QtCore import Qt, QUrl, QSize
    from PySide6.QtGui import QDesktopServices

    app = QApplication.instance() or QApplication(sys.argv)

    dlg = QDialog()
    dlg.setWindowTitle('选择桌面环境')
    dlg.setMinimumSize(560, 480)
    dlg.setStyleSheet("""
        QDialog { background: #f5f5f7; }
        QLabel#title { font-size: 20px; font-weight: bold; color: #1d1d1f; }
        QLabel#sub   { font-size: 13px; color: #6e6e73; }
        QListWidget  {
            border: 1px solid #d1d1d6; border-radius: 8px;
            background: white; font-size: 14px;
        }
        QListWidget::item { padding: 10px 14px; border-bottom: 1px solid #f0f0f0; }
        QListWidget::item:selected { background: #e8f0fb; color: #0071e3; }
        QListWidget::item:hover    { background: #f5f5f7; }
        QPushButton#primary {
            background: #0071e3; color: white; border: none;
            border-radius: 8px; padding: 8px 24px; font-size: 14px;
        }
        QPushButton#primary:hover    { background: #0077ed; }
        QPushButton#primary:disabled { background: #b0b0b0; }
        QPushButton#link {
            background: transparent; color: #0071e3; border: none;
            font-size: 13px; text-decoration: underline;
        }
        QPushButton#link:hover { color: #0077ed; }
    """)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(32, 28, 32, 24)
    layout.setSpacing(12)

    title = QLabel('选择桌面环境')
    title.setObjectName('title')
    layout.addWidget(title)

    sub = QLabel('安装完成后将自动配置所选桌面环境。\n不确定选哪个？点击下方链接查看效果预览。')
    sub.setObjectName('sub')
    sub.setWordWrap(True)
    layout.addWidget(sub)

    wiki_btn = QPushButton('查看各桌面环境效果预览 →')
    wiki_btn.setObjectName('link')
    wiki_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    wiki_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(WIKI_URL)))
    layout.addWidget(wiki_btn)

    lst = QListWidget()
    for name, key, desc in DESKTOP_OPTIONS:
        item = QListWidgetItem(f'  {name}\n  {desc}')
        item.setData(Qt.ItemDataRole.UserRole, key)
        item.setSizeHint(QSize(0, 52))
        lst.addItem(item)
    lst.setCurrentRow(0)
    layout.addWidget(lst, stretch=1)

    btn_row = QHBoxLayout()
    btn_row.addStretch()
    ok_btn = QPushButton('确认')
    ok_btn.setObjectName('primary')
    ok_btn.setFixedHeight(36)
    ok_btn.clicked.connect(dlg.accept)
    btn_row.addWidget(ok_btn)
    layout.addLayout(btn_row)

    dlg.exec()

    selected = lst.currentItem()
    return selected.data(Qt.ItemDataRole.UserRole) if selected else 'none'


def run(mount_point: str):
    desktop_env = _pick_desktop()

    shorin_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shorin-arch-setup')
    shorin_dst = os.path.join(mount_point, 'root', 'shorin-arch-setup')

    # 复制 shorin-arch-setup 进 chroot
    if os.path.exists(shorin_dst):
        shutil.rmtree(shorin_dst)
    shutil.copytree(shorin_src, shorin_dst)

    # 运行适配脚本（在 chroot 外打补丁、写入执行脚本）
    compat = os.path.join(shorin_src, 'scripts', 'chroot-compat.sh')
    username = _get_username(mount_point)
    subprocess.run(['bash', compat, mount_point, username, desktop_env], check=True)

    # 在 chroot 里执行
    base_system.arch_chroot(mount_point, ['bash', '/root/run-shorin.sh'])

    # 清理
    shutil.rmtree(shorin_dst, ignore_errors=True)
    try:
        os.remove(os.path.join(mount_point, 'root', 'run-shorin.sh'))
    except FileNotFoundError:
        pass


def _get_username(mount_point: str) -> str:
    passwd = os.path.join(mount_point, 'etc', 'passwd')
    try:
        with open(passwd) as f:
            for line in f:
                parts = line.strip().split(':')
                if len(parts) >= 4 and parts[2] == '1000':
                    return parts[0]
    except Exception:
        pass
    return 'user'
