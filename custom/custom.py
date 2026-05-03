import shutil
import os
import json
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from installer import system


class CustomInstaller:
    DESKTOP_OPTIONS = [
        ('none',         '不安装桌面环境',       '仅基础系统，无图形界面'),
        ('kde',          'KDE Plasma',           '功能完整的传统桌面，推荐新手'),
        ('shorindms',    'Shorin DMS Niri',      'Shorin 定制 Niri，推荐'),
        ('shorinnocniri','Shorin Noctalia Niri',  'Noctalia 主题 Niri 桌面'),
        ('shorinniri',   'Shorin Niri',           'Shorin 标准 Niri 配置'),
        ('minimalniri',  'Minimal Niri',          '极简 Niri，轻量快速'),
        ('minimallabwc', 'Minimal Labwc',         '极简 Labwc 合成器'),
        ('hyprniri',     'Shorin Hyprland+Niri',  'Hyprland 滚动模式'),
        ('gnome',        'GNOME',                 '经典 GNOME 桌面'),
        ('end4',         'Quickshell: End4',      'illogical-impulse 风格'),
        ('dms',          'Quickshell: DMS',       'DankMaterialShell'),
        ('caelestia',    'Quickshell: Caelestia', 'Caelestia 风格'),
        ('inir',         'Quickshell: Inir',      'Inir 风格'),
    ]

    WIKI_URL = (
        'https://github.com/SHORiN-KiWATA/Shorin-ArchLinux-Guide/wiki/'
        '%E4%B8%80%E9%94%AE%E9%85%8D%E7%BD%AE%E6%A1%8C%E9%9D%A2%E7%8E%AF%E5%A2%83'
    )

    def pre_run(self) -> None:
        """在主线程中调用，用于需要 GUI 交互的预处理（如桌面环境选择）。"""
        self._desktop_env = self._pick_desktop()

    def run(self, mount_point: str) -> None:
        desktop_env = getattr(self, '_desktop_env', None) or self._pick_desktop()

        shorin_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shorin-arch-setup')
        shorin_dst = os.path.join(mount_point, 'root', 'shorin-arch-setup')

        if os.path.exists(shorin_dst):
            shutil.rmtree(shorin_dst)
        shutil.copytree(shorin_src, shorin_dst, symlinks=True)

        config = {
            'desktop_env': desktop_env,
            'optional_modules': ['gpu', 'grub', 'apps'],
            'mirror': 'cn',
            'grub_theme': '1CyberGRUB-2077',
            'flatpak_mirror': 'ustc',
        }
        config_path = os.path.join(mount_point, 'root', 'setup-config.json')
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        customize_sh = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'customize_system.sh')
        customize_dst = os.path.join(mount_point, 'root', 'customize_system.sh')
        shutil.copy(customize_sh, customize_dst)
        system.arch_chroot(mount_point, ['bash', '/root/customize_system.sh'])

        system.arch_chroot(mount_point, ['bash', '/root/shorin-arch-setup/install.sh'])

        shutil.rmtree(shorin_dst, ignore_errors=True)
        for f in [config_path,
                  os.path.join(mount_point, 'tmp', 'shorin_install_user'),
                  os.path.join(mount_point, 'root', 'customize_system.sh')]:
            try:
                os.remove(f)
            except FileNotFoundError:
                pass

    def _pick_desktop(self) -> str:
        if system.is_linux_tty_or_non_desktop():
            return self._pick_desktop_tty()
        else:
            return self._pick_desktop_gui()

    def _pick_desktop_tty(self) -> str:
        print('\n请选择桌面环境：')
        for i, (code, name, desc) in enumerate(self.DESKTOP_OPTIONS, 1):
            print(f'    {i}. {name}  —  {desc}')
        while True:
            try:
                choice = int(input('请输入选择的编号：'))
                if 1 <= choice <= len(self.DESKTOP_OPTIONS):
                    return self.DESKTOP_OPTIONS[choice - 1][0]
                print('无效的编号，请重试。')
            except ValueError:
                print('请输入有效的数字。')

    def _pick_desktop_gui(self) -> str:
        return self._run_desktop_dialog()

    def _run_desktop_dialog(self) -> str:
        try:
            from PySide6.QtWidgets import (
                QApplication, QDialog, QVBoxLayout, QHBoxLayout,
                QLabel, QListWidget, QListWidgetItem, QPushButton,
            )
            from PySide6.QtCore import Qt, QUrl, QSize
            from PySide6.QtGui import QDesktopServices

            app = QApplication.instance()
            if app is None:
                app = QApplication([])

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
                QListWidget::item { padding: 6px 14px; border-bottom: 1px solid #f0f0f0; }
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
            wiki_btn.clicked.connect(
                lambda: QDesktopServices.openUrl(QUrl(self.WIKI_URL))
            )
            layout.addWidget(wiki_btn)

            list_widget = QListWidget()
            for code, name, desc in self.DESKTOP_OPTIONS:
                item = QListWidgetItem(f'  {name}\n  {desc}')
                item.setData(Qt.UserRole, code)
                item.setSizeHint(QSize(0, 64))
                list_widget.addItem(item)
            list_widget.setCurrentRow(0)
            list_widget.itemDoubleClicked.connect(lambda _: dlg.accept())
            layout.addWidget(list_widget, stretch=1)

            btn_row = QHBoxLayout()
            btn_row.addStretch()
            ok_btn = QPushButton('确认')
            ok_btn.setObjectName('primary')
            ok_btn.setFixedHeight(36)
            ok_btn.clicked.connect(dlg.accept)
            btn_row.addWidget(ok_btn)
            layout.addLayout(btn_row)

            result = dlg.exec()
            if result == QDialog.Accepted:
                selected_item = list_widget.currentItem()
                if selected_item:
                    return selected_item.data(Qt.UserRole)
        except Exception as e:
            print(f"GUI选择器错误: {e}")
            import traceback
            traceback.print_exc()
        return 'none'


if __name__ == '__main__':
    inst = CustomInstaller()
    result = inst._pick_desktop()
    print(f'选择的桌面环境: {result}')
