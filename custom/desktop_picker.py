#!/usr/bin/env python3
"""独立进程运行的桌面环境选择窗口，结果写到 argv[1] 指定的文件。"""

import sys
import os

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

WIKI_URL = (
    'https://github.com/SHORiN-KiWATA/Shorin-ArchLinux-Guide/wiki/'
    '%E4%B8%80%E9%94%AE%E9%85%8D%E7%BD%AE%E6%A1%8C%E9%9D%A2%E7%8E%AF%E5%A2%83'
)


def main():
    result_file = sys.argv[1] if len(sys.argv) > 1 else '/tmp/elvara_desktop_choice'

    from PySide6.QtWidgets import (
        QApplication, QDialog, QVBoxLayout, QHBoxLayout,
        QLabel, QListWidget, QListWidgetItem, QPushButton,
    )
    from PySide6.QtCore import Qt, QUrl, QSize
    from PySide6.QtGui import QDesktopServices

    app = QApplication(sys.argv)

    dlg = QDialog()
    dlg.setWindowTitle('选择桌面环境')
    dlg.setMinimumSize(560, 500)
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
        QPushButton#primary:hover { background: #0077ed; }
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
    # 双击也能确认
    lst.itemDoubleClicked.connect(lambda _: dlg.accept())
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
    key = selected.data(Qt.ItemDataRole.UserRole) if selected else 'none'

    with open(result_file, 'w') as f:
        f.write(key)


if __name__ == '__main__':
    main()
