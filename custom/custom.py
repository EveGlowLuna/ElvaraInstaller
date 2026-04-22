import shutil
import os
import json

from installer import base_system


class CustomInstaller:
    DESKTOP_ENVIRONMENTS = [
        ('shorinniri', 'Shorin Niri (推荐)'),
        ('gnome', 'GNOME'),
        ('kde', 'KDE Plasma'),
        ('hyprniri', 'Shorin HyprNiri'),
        ('shorindms', 'Shorin DMS'),
        ('shorinnocniri', 'Shorin Noctalia'),
        ('end4', 'End4 Quickshell'),
        ('dms', 'DMS Quickshell'),
        ('caelestia', 'Caelestia Quickshell'),
        ('inir', 'Inir Quickshell'),
        ('minimalniri', '极简版 Niri'),
        ('minimallabwc', '极简版 Labwc'),
        ('none', '不安装桌面环境'),
    ]

    def run(self, mount_point: str) -> None:
        desktop_env = self._pick_desktop()

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
        config_path = os.path.join(mount_point, 'tmp', 'setup-config.json')
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        customize_sh = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'customize_system.sh')
        customize_dst = os.path.join(mount_point, 'root', 'customize_system.sh')
        shutil.copy(customize_sh, customize_dst)
        base_system.arch_chroot(mount_point, ['bash', '/root/customize_system.sh'])

        base_system.arch_chroot(mount_point, ['bash', '/root/shorin-arch-setup/install.sh'])

        shutil.rmtree(shorin_dst, ignore_errors=True)
        for f in [config_path,
                  os.path.join(mount_point, 'tmp', 'shorin_install_user'),
                  os.path.join(mount_point, 'root', 'customize_system.sh')]:
            try:
                os.remove(f)
            except FileNotFoundError:
                pass

    def _pick_desktop(self) -> str:
        if base_system.is_linux_tty_or_non_desktop():
            return self._pick_desktop_tty()
        else:
            return self._pick_desktop_gui()

    def _pick_desktop_tty(self) -> str:
        print('\n请选择桌面环境：')
        for i, (code, name) in enumerate(self.DESKTOP_ENVIRONMENTS, 1):
            print(f'    {i}. {name}')
        
        while True:
            try:
                choice = int(input('请输入选择的编号：'))
                if 1 <= choice <= len(self.DESKTOP_ENVIRONMENTS):
                    return self.DESKTOP_ENVIRONMENTS[choice - 1][0]
                print('无效的编号，请重试。')
            except ValueError:
                print('请输入有效的数字。')

    def _pick_desktop_gui(self) -> str:
        try:
            from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QWidget
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QFont

            app = QApplication.instance()
            if app is None:
                app = QApplication([])

            dialog = QDialog()
            dialog.setWindowTitle('选择桌面环境')
            dialog.setMinimumSize(400, 320)

            screen = QApplication.primaryScreen().availableGeometry()
            dialog.move(
                screen.x() + (screen.width() - dialog.width()) // 2,
                screen.y() + (screen.height() - dialog.height()) // 2,
            )

            root = QVBoxLayout(dialog)
            root.setContentsMargins(30, 24, 30, 24)
            root.setSpacing(16)

            title = QLabel('请选择桌面环境')
            font = QFont()
            font.setPointSize(16)
            font.setBold(True)
            title.setFont(font)
            title.setStyleSheet('color: #1d1d1f;')
            root.addWidget(title)

            self._list_widget = QListWidget()
            self._list_widget.setStyleSheet("""
                QListWidget {
                    border: 1px solid #d1d1d6;
                    border-radius: 8px;
                    background: white;
                    font-size: 14px;
                }
                QListWidget::item {
                    padding: 10px 14px;
                    border-bottom: 1px solid #f0f0f0;
                }
                QListWidget::item:selected {
                    background: #e8f0fb;
                    color: #0071e3;
                }
                QListWidget::item:hover {
                    background: #f5f5f7;
                }
            """)

            for code, name in self.DESKTOP_ENVIRONMENTS:
                item = QListWidgetItem(name)
                item.setData(Qt.UserRole, code)
                self._list_widget.addItem(item)
            self._list_widget.setCurrentRow(0)
            root.addWidget(self._list_widget, stretch=1)

            btn = QPushButton('确认选择')
            btn.setStyleSheet("""
                QPushButton {
                    background: #0071e3;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 10px 24px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background: #0077ed;
                }
            """)
            btn.clicked.connect(dialog.accept)
            root.addWidget(btn)

            dialog.setStyleSheet("""
                QDialog {
                    background: white;
                    border-radius: 12px;
                }
            """)

            if dialog.exec() == QDialog.Accepted:
                selected = self._list_widget.currentItem()
                if selected:
                    return selected.data(Qt.UserRole)
        except Exception:
            pass
        return 'gnome'
