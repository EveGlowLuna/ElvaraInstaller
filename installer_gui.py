"""ElvaraOS 安装程序 — PySide6 GUI"""
import os
import sys
import socket

from PySide6.QtCore import Qt, QThread, Signal, QObject, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QStackedWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QComboBox,
    QFormLayout, QTextEdit, QProgressBar,
    QMessageBox, QSizePolicy,
    QFrame,
)

from installer import disk, base_system, efi
from installer.log import setup_gui_logging
import importlib.util
import sys
import os

def _load_custom():
    """加载 custom/custom.py 并返回 CustomInstaller 实例。"""
    # 打包后用可执行文件所在目录，未打包用脚本所在目录
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    custom_path = os.path.join(base, 'custom', 'custom.py')
    spec = importlib.util.spec_from_file_location('custom.custom', custom_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.CustomInstaller()


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

INSTALL_STEPS = [
    ('准备磁盘分区',       5),
    ('挂载文件系统',       5),
    ('安装基础系统',      20),
    ('配置系统',          20),
    ('复制系统定制内容',  15),
    ('安装引导加载程序',  10),
    ('完成',              25),
]


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
QLineEdit, QComboBox {
    border: 1px solid #d1d1d6;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 14px;
    background: white;
}
QLineEdit:focus, QComboBox:focus { border-color: #0071e3; }
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


class InstallWorker(QObject):
    log      = Signal(str)
    step     = Signal(int, str)
    finished = Signal(bool, str)

    def __init__(self, kwargs: dict):
        super().__init__()
        self._kwargs = kwargs

    def run(self) -> None:
        import shutil
        setup_gui_logging(self.log.emit)
        # 清空旧日志
        try:
            open('/tmp/elvara_install.log', 'w').close()
        except Exception:
            pass
        try:
            kw = self._kwargs
            disk_root   = kw['disk_root']
            disk_efi    = kw['disk_efi']
            username    = kw['username']
            userpwd     = kw['userpwd']
            hostname    = kw['hostname']
            timezone    = kw['timezone']
            kb_layout   = kw['kb_layout']
            wipe        = kw['wipe']
            new_parts   = kw.get('new_parts', False)

            boot_mode = efi.get_boot_mode()
            
            # 步骤 0：分区
            self.step.emit(0, INSTALL_STEPS[0][0])
            # 先尝试 umount，忽略失败（磁盘可能没挂载）
            import subprocess as _sp
            r = _sp.run(['sudo', 'umount', '-R', '/mnt'], capture_output=True)
            if r.returncode != 0:
                _sp.run(['sudo', 'umount', '-Rl', '/mnt'], capture_output=True)
            
            if wipe:
                raw_disk = kw['raw_disk']
                disk.create_label(raw_disk, boot_mode)
                if boot_mode == 'boot':
                    disk.create_part(raw_disk, 'primary', '1MiB', '100%', is_boot=True, part_num=1)
                    base_system.udevadm_settle()
                    disk_root = disk.get_partition_path(raw_disk, 1)
                    disk_efi = None
                    disk.create_filesystem(disk_root, 'ext4')
                else:
                    part_size_gib = kw.get('part_size_gib')
                    end_size = '100%' if part_size_gib is None else f'{part_size_gib}GiB'
                    disk.create_part(raw_disk, 'primary', '1MiB', '513MiB', fs_type='fat32')
                    disk.create_part(raw_disk, 'primary', '513MiB', end_size)
                    base_system.udevadm_settle()
                    disk_efi  = disk.get_partition_path(raw_disk, 1)
                    disk_root = disk.get_partition_path(raw_disk, 2)
                    _sp.run(['sudo', 'parted', '-s', raw_disk, 'set', '1', 'esp', 'on'], check=True)
                    disk.create_filesystem(disk_efi, 'fat')
                    disk.create_filesystem(disk_root, 'ext4')
            elif new_parts:
                if boot_mode == 'boot':
                    raise RuntimeError("在 BIOS 系统上，不支持在已有分区的磁盘上创建新分区。请选择清空磁盘。")
                
                raw_disk = kw['raw_disk']
                part_size_gib = kw.get('part_size_gib')
                last_end = disk.get_last_part_end(raw_disk)
                efi_end  = f'{int(last_end.rstrip("MiB")) + 513}MiB' if last_end.endswith('MiB') else '513MiB'
                
                children_data = disk.get_disk_data()
                raw_name  = raw_disk.replace('/dev/', '')
                dev_info  = next((d for d in children_data['blockdevices'] if d['name'] == raw_name), None)
                existing  = dev_info.get('children', []) if dev_info else []
                efi_num   = len(existing) + 1
                root_num  = efi_num + 1
                end_size  = '100%' if part_size_gib is None else f'{part_size_gib}GiB'
                
                disk.create_part(raw_disk, 'primary', last_end, efi_end, fs_type='fat32')
                disk.create_part(raw_disk, 'primary', efi_end, end_size)
                _sp.run(['sudo', 'parted', '-s', raw_disk, 'set', str(efi_num), 'esp', 'on'], check=True)
                base_system.udevadm_settle()
                disk_efi  = disk.get_partition_path(raw_disk, efi_num)
                disk_root = disk.get_partition_path(raw_disk, root_num)
                disk.create_filesystem(disk_efi, 'fat')
                disk.create_filesystem(disk_root, 'ext4')
            elif disk_root:
                if not disk_efi and boot_mode != 'boot':
                    raise RuntimeError("在 UEFI 系统上，必须存在 EFI 分区。")
                disk.create_filesystem(disk_root, 'ext4')
            else:
                # Fallback for empty disk without wipe flag
                raw_disk = kw['raw_disk']
                disk.create_label(raw_disk, boot_mode)
                if boot_mode == 'boot':
                    disk.create_part(raw_disk, 'primary', '1MiB', '100%', is_boot=True, part_num=1)
                    base_system.udevadm_settle()
                    disk_root = disk.get_partition_path(raw_disk, 1)
                    disk_efi = None
                    disk.create_filesystem(disk_root, 'ext4')
                else:
                    part_size_gib = kw.get('part_size_gib')
                    end_size = '100%' if part_size_gib is None else f'{part_size_gib}GiB'
                    disk.create_part(raw_disk, 'primary', '1MiB', '513MiB', fs_type='fat32')
                    disk.create_part(raw_disk, 'primary', '513MiB', end_size)
                    base_system.udevadm_settle()
                    disk_efi  = disk.get_partition_path(raw_disk, 1)
                    disk_root = disk.get_partition_path(raw_disk, 2)
                    _sp.run(['sudo', 'parted', '-s', raw_disk, 'set', '1', 'esp', 'on'], check=True)
                    disk.create_filesystem(disk_efi, 'fat')
                    disk.create_filesystem(disk_root, 'ext4')

            # 挂载
            self.step.emit(1, INSTALL_STEPS[1][0])
            disk.mount_disk(disk_root, disk_efi)

            # 步骤 2：安装基础系统
            self.step.emit(2, INSTALL_STEPS[2][0])
            base_system.install_base('/mnt')
            base_system.generate_fstab('/mnt')

            # 步骤 3：配置系统
            self.step.emit(3, INSTALL_STEPS[3][0])
            base_system.write_file('/mnt', '/etc/locale.gen', 'zh_CN.UTF-8 UTF-8\n', 'a')
            base_system.arch_chroot('/mnt', ['locale-gen'])
            base_system.write_file('/mnt', '/etc/locale.conf', 'LANG=zh_CN.UTF-8\n')
            base_system.arch_chroot('/mnt', ['ln', '-sf', f'/usr/share/zoneinfo/{timezone}', '/etc/localtime'])
            base_system.write_file('/mnt', '/etc/hostname', f'{hostname}\n')
            base_system.write_file('/mnt', '/etc/hosts',
                f'127.0.0.1   localhost\n::1         localhost\n127.0.1.1   {hostname}.localdomain   {hostname}\n')
            base_system.write_file('/mnt', '/etc/vconsole.conf', f'KEYMAP={kb_layout}\n')
            # 创建用户
            base_system.create_user('/mnt', username)
            base_system.set_passwd('/mnt', username, userpwd)
            base_system.set_passwd('/mnt', 'root', userpwd)
            base_system.write_file('/mnt', '/etc/sudoers.d/wheel', '%wheel ALL=(ALL:ALL) ALL\n')
            os.chmod('/mnt/etc/sudoers.d/wheel', 0o440)
            base_system.arch_chroot('/mnt', ['systemctl', 'enable', 'NetworkManager'])

            # 所有配置写完后重建 initramfs
            base_system.arch_chroot('/mnt', ['mkinitcpio', '-P'])

            # 步骤 4：定制脚本（由 custom.py 内部处理）
            self.step.emit(4, INSTALL_STEPS[4][0])
            _load_custom().run('/mnt')

            # 步骤 5：引导
            self.step.emit(5, INSTALL_STEPS[5][0])
            if boot_mode == 'boot':
                base_system.arch_chroot('/mnt', ['grub-install', '--target=i386-pc', kw['raw_disk']])
            else:
                target = '--target=x86_64-efi' if boot_mode == 'uefi' else '--target=i386-efi'
                base_system.arch_chroot('/mnt', ['grub-install', target, '--efi-directory=/boot', '--bootloader-id=GRUB'])
            
            base_system.arch_chroot('/mnt', ['grub-mkconfig', '-o', '/boot/grub/grub.cfg'])

            base_system.umount_all()
            self.step.emit(6, INSTALL_STEPS[6][0])
            self.finished.emit(True, '')

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            # 如果是子进程错误，附上 stdout/stderr
            if hasattr(e, 'stderr') and e.stderr:
                stderr_text = e.stderr if isinstance(e.stderr, str) else e.stderr.decode(errors='replace')
                tb += f'\n--- stderr ---\n{stderr_text}'
            if hasattr(e, 'stdout') and e.stdout:
                stdout_text = e.stdout if isinstance(e.stdout, str) else e.stdout.decode(errors='replace')
                tb += f'\n--- stdout ---\n{stdout_text}'
            self.log.emit(tb)
            try:
                with open('/tmp/elvara_install.log', 'a') as f:
                    f.write(tb)
            except Exception:
                pass
            self.finished.emit(False, str(e))


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


def _parse_size_gib(size_str: str) -> float:
    """Converts lsblk size string to GiB."""
    if not size_str or not isinstance(size_str, str):
        return 0.0
    s = size_str.strip().upper().replace(',', '.')
    try:
        # Handle cases where size might not have a unit (e.g., just bytes)
        if s[-1].isdigit():
            return float(s) / (1024 * 1024 * 1024)
        
        num = float(s[:-1])
        unit = s[-1]
        if unit == 'T':
            return num * 1024
        if unit == 'G':
            return num
        if unit == 'M':
            return num / 1024
        if unit == 'K':
            return num / (1024 * 1024)
        return float(s) / (1024 * 1024 * 1024) # Bytes
    except (ValueError, TypeError, IndexError):
        return 0.0


class WelcomePage(QWidget):
    def __init__(self, on_next, on_quit):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(60, 40, 60, 40)
        root.setSpacing(0)
        root.addStretch(2)

        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        px = QPixmap(ICON_PATH)
        if not px.isNull():
            icon_label.setPixmap(px.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation))
        root.addWidget(icon_label)
        root.addSpacing(24)

        title = QLabel('欢迎安装 ElvaraOS！')
        title.setObjectName('title')
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(title)
        root.addSpacing(16)

        desc = QLabel(
            'ElvaraOS 将引导你安装系统到硬盘中。\n'
            '在开始之前，请确保电脑已经联网。\n'
            '您可以在右下角任务栏或设置中进行联网操作。'
        )
        desc.setObjectName('subtitle')
        desc.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        desc.setWordWrap(True)
        root.addWidget(desc)

        root.addStretch(3)
        root.addWidget(_divider())
        root.addSpacing(16)

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



class DiskPage(QWidget):
    def __init__(self, on_prev, on_next):
        super().__init__()
        self._on_next = on_next
        self._devices = []
        self._unalloc_gib = 0.0

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

        self._list = QListWidget()
        self._list.setMinimumHeight(160)
        self._list.currentRowChanged.connect(self._on_disk_changed)
        root.addWidget(self._list)

        # 分区选择（有子分区时显示）
        self._part_label = QLabel('选择安装到哪个分区：')
        self._part_label.setVisible(False)
        root.addWidget(self._part_label)
        self._part_list = QListWidget()
        self._part_list.setMaximumHeight(140)
        self._part_list.setVisible(False)
        root.addWidget(self._part_list)

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

        self._on_disk_changed(0)

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        """每次页面显示时重新读取磁盘数据"""
        prev_row = self._list.currentRow()
        self._list.blockSignals(True)
        self._list.clear()
        try:
            self._devices = disk.get_disk_data()['blockdevices']
        except Exception:
            self._devices = []
        for dev in self._devices:
            model = dev.get('model') or 'Unknown'
            size  = dev.get('size', '')
            path  = f'/dev/{dev["name"]}'
            item  = QListWidgetItem(f'  {model}\n  {size}  ·  {path}')
            item.setSizeHint(QSize(0, 56))
            self._list.addItem(item)
        self._list.blockSignals(False)
        row = prev_row if 0 <= prev_row < self._list.count() else 0
        if self._list.count():
            self._list.setCurrentRow(row)
        self._on_disk_changed(row)

    def _on_disk_changed(self, row: int) -> None:
        if row < 0 or row >= len(self._devices):
            return
        dev = self._devices[row]
        children = dev.get('children', [])
        self._part_list.clear()
        
        boot_mode = efi.get_boot_mode()

        if children:
            for c in children:
                self._part_list.addItem(
                    f'  /dev/{c["name"]}  ({c.get("fstype") or "未知"})  {c.get("size", "")}')
            
            # For BIOS mode, don't allow creating new partitions if some already exist.
            # Force the user to either pick an existing one or wipe the disk.
            if boot_mode == 'boot':
                self._part_list.addItem('  ＋ 清空磁盘重装')
                self._unalloc_gib = 0 # Ensure the next step knows not to offer new part
            else:
                # UEFI mode allows creating new partitions in unallocated space
                try:
                    total = _parse_size_gib(dev.get('size', '0G'))
                    used  = sum(_parse_size_gib(c.get('size', '0G')) for c in children)
                    unalloc = max(0.0, total - used)
                    self._unalloc_gib = unalloc
                except Exception:
                    unalloc = 0.0
                    self._unalloc_gib = 0.0
                
                if unalloc >= 0.5:
                    self._part_list.addItem(f'  ＋ 在未分配空间新建分区 / 清空磁盘重装  （未分配 {unalloc:.1f} GiB）')
                else:
                    self._part_list.addItem('  ＋ 清空磁盘重装')

            self._part_list.setCurrentRow(0)
            self._part_label.setText('选择安装到哪个分区：')
            self._part_label.setVisible(True)
            self._part_list.setVisible(True)
        else:
            self._part_label.setVisible(False)
            self._part_list.setVisible(False)
            self._unalloc_gib = _parse_size_gib(dev.get('size', '0G'))

    def _handle_next(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            QMessageBox.warning(self, '提示', '请先选择一个磁盘')
            return
        dev = self._devices[row]
        raw_disk = f'/dev/{dev["name"]}'
        children = dev.get('children', [])

        if children:
            prow = self._part_list.currentRow()
            if prow < 0:
                QMessageBox.warning(self, '提示', '请选择一个目标分区')
                return
            if prow == len(children):
                # 最后一项：新建分区或清盘
                if self._unalloc_gib >= 0.5:
                    # 有未分配空间，让用户二选一
                    reply = QMessageBox.question(
                        self, '选择安装方式',
                        f'请选择安装方式：\n\n'
                        f'• 是：在未分配空间新建分区安装（保留现有数据）\n'
                        f'• 否：清空 {raw_disk} 全部数据重新分区安装',
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        self._on_next(raw_disk, None, None, wipe=False, new_parts=True)
                    elif reply == QMessageBox.StandardButton.No:
                        self._on_next(raw_disk, None, None, wipe=True, new_parts=False)
                else:
                    # 没有未分配空间，只能清盘
                    reply = QMessageBox.question(
                        self, '确认操作',
                        f'此操作将清空 {raw_disk} 上的全部数据并重新分区安装系统，是否继续？',
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        self._on_next(raw_disk, None, None, wipe=True, new_parts=False)
            else:
                disk_root = f'/dev/{children[prow]["name"]}'
                disk_efi_part = efi.get_efi_part(row)
                self._on_next(raw_disk, disk_root, disk_efi_part, wipe=False, new_parts=False)
        else:
            reply = QMessageBox.question(
                self, '确认',
                f'将清空 {raw_disk} 上的所有数据并安装系统，确认继续？',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._on_next(raw_disk, None, None, wipe=True, new_parts=False)



class PartSizePage(QWidget):
    """仅在 wipe=True 时显示，询问分配给系统的空间大小"""
    def __init__(self, on_prev, on_next):
        super().__init__()
        self._on_next = on_next
        self._disk_size_gib = 0.0

        root = QVBoxLayout(self)
        root.setContentsMargins(60, 40, 60, 40)
        root.setSpacing(12)

        title = QLabel('分配磁盘空间')
        title.setObjectName('title')
        root.addWidget(title)

        self._hint = QLabel()
        self._hint.setObjectName('subtitle')
        self._hint.setWordWrap(True)
        root.addWidget(self._hint)
        root.addSpacing(8)

        form = QFormLayout()
        form.setSpacing(14)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._size_edit = QLineEdit()
        self._size_edit.setPlaceholderText('留空则使用全部可用空间')
        form.addRow('分配大小（G）：', self._size_edit)
        root.addLayout(form)

        root.addStretch()
        root.addWidget(_divider())
        root.addSpacing(8)

        btn_row = QHBoxLayout()
        prev_btn = _nav_btn('← 上一步', primary=False)
        prev_btn.clicked.connect(on_prev)
        next_btn = _nav_btn('下一步 →')
        next_btn.clicked.connect(self._handle_next)
        btn_row.addWidget(prev_btn)
        btn_row.addStretch()
        btn_row.addWidget(next_btn)
        root.addLayout(btn_row)

    def set_disk_size(self, size_str: str) -> None:
        gib = _size_to_gb(size_str)
        self._disk_size_gib = gib
        self._hint.setText(
            f'磁盘总容量约 {gib:.1f} GiB。\n'
            '输入要分配给系统的空间大小（单位 G），留空则使用全部可用空间。'
        )
        self._size_edit.setPlaceholderText(f'留空则使用全部可用空间（约 {gib:.1f} G）')

    def _handle_next(self) -> None:
        text = self._size_edit.text().strip()
        if not text:
            self._on_next(None)  # None = 100%
            return
        try:
            val = float(text)
            if val <= 0:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, '提示', '请输入有效的数字')
            return
        # 换算：用户输入 GB，转 GiB，超出可用则用 100%
        gib = val * 1000 / 1024
        available = self._disk_size_gib - 0.5  # 减去 EFI 的 513MiB
        self._on_next(None if gib >= available else gib)

    def get_part_size_gib(self) -> float | None:
        """返回 None 表示用 100%"""
        text = self._size_edit.text().strip()
        if not text:
            return None
        val = float(text) * 1000 / 1024
        available = self._disk_size_gib - 0.5
        return None if val >= available else val


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

        self._tz_combo = QComboBox()
        self._tz_combo.addItems(TIMEZONES)
        self._tz_combo.setCurrentText('Asia/Shanghai')
        form.addRow('时区：', self._tz_combo)

        self._kb_combo = QComboBox()
        for code, label in KB_LAYOUTS:
            self._kb_combo.addItem(label, code)
        form.addRow('键盘布局：', self._kb_combo)

        try:
            default_hostname = socket.gethostname()
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
        self._username_edit.setPlaceholderText('仅限小写字母、数字和下划线')
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
        import re
        u = self._username_edit.text().strip()
        p = self._password_edit.text()
        c = self._password_confirm.text()
        if not u:
            QMessageBox.warning(self, '提示', '用户名不能为空')
            return
        if not re.match(r'^[a-z][a-z0-9_]*$', u):
            QMessageBox.warning(self, '提示', '用户名只能包含小写字母、数字和下划线，且以字母开头')
            return
        if not p:
            QMessageBox.warning(self, '提示', '密码不能为空')
            return
        if p != c:
            QMessageBox.warning(self, '提示', '两次输入的密码不一致')
            return
        on_next()

    def get_user(self) -> dict:
        return {
            'username': self._username_edit.text().strip(),
            'password': self._password_edit.text(),
        }



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
        install_btn.clicked.connect(self._on_install)
        btn_row.addWidget(prev_btn)
        btn_row.addStretch()
        btn_row.addWidget(install_btn)
        root.addLayout(btn_row)

    def update_summary(self, disk_info: str, system_info: dict, username: str) -> None:
        text = (
            f'<b>安装位置</b><br>{disk_info}<br><br>'
            f'<b>时区</b><br>{system_info.get("timezone", "")}<br><br>'
            f'<b>键盘布局</b><br>{system_info.get("kb_layout", "")}<br><br>'
            f'<b>设备名称</b><br>{system_info.get("hostname", "")}<br><br>'
            f'<b>用户名</b><br>{username}<br>'
        )
        self._summary.setText(text)



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

        self._dest_label = QLabel()
        self._dest_label.setObjectName('subtitle')
        self._dest_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(self._dest_label)
        root.addSpacing(16)

        self._content_stack = QStackedWidget()

        # 进度视图
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

        self._last_log_label = QLabel('')
        self._last_log_label.setObjectName('step_hint')
        self._last_log_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._last_log_label.setWordWrap(True)
        self._last_log_label.setStyleSheet('font-size: 11px; color: #aaaaaa;')
        pw_layout.addWidget(self._last_log_label)

        pw_layout.addStretch()

        # 日志视图
        self._log_view = QTextEdit()
        self._log_view.setObjectName('log')
        self._log_view.setReadOnly(True)

        self._content_stack.addWidget(progress_widget)
        self._content_stack.addWidget(self._log_view)
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
        # 更新最新日志提示，过滤空行和命令行（$ 开头）
        stripped = msg.strip()
        if stripped and not stripped.startswith('$'):
            # 截断过长的行
            display = stripped if len(stripped) <= 80 else stripped[:77] + '...'
            self._last_log_label.setText(display)

    def _toggle_log(self) -> None:
        self._show_log = not self._show_log
        self._content_stack.setCurrentIndex(1 if self._show_log else 0)
        self._log_btn.setText('隐藏日志' if self._show_log else '显示日志')

    def set_cancel_callback(self, cb) -> None:
        self._cancel_btn.clicked.connect(cb)



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



class InstallerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('ElvaraOS 安装程序')
        self._worker_thread: QThread | None = None
        self._selected: dict = {}

        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(int(screen.width() * 0.72), int(screen.height() * 0.78))
        self.move(
            screen.x() + (screen.width() - self.width()) // 2,
            screen.y() + (screen.height() - self.height()) // 2,
        )

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._welcome  = WelcomePage(self._go_disk, self._quit)
        self._disk_pg  = DiskPage(self._go_welcome, self._from_disk)
        self._part_pg  = PartSizePage(self._go_disk_direct, self._from_part_size)
        self._sys_pg   = SystemPage(self._go_part_or_disk, self._go_user)
        self._user_pg  = UserPage(self._go_sys, self._go_confirm)
        self._confirm  = ConfirmPage(self._go_user, self._start_install)
        self._install  = InstallPage()
        self._done     = DonePage(self._quit, self._reboot)

        for page in [self._welcome, self._disk_pg, self._part_pg, self._sys_pg,
                     self._user_pg, self._confirm, self._install, self._done]:
            self._stack.addWidget(page)

        self._install.set_cancel_callback(self._cancel_install)


    def _go_welcome(self):      self._stack.setCurrentWidget(self._welcome)
    def _go_disk_direct(self):  self._stack.setCurrentWidget(self._disk_pg)
    def _go_sys(self):          self._stack.setCurrentWidget(self._sys_pg)
    def _go_user(self):         self._stack.setCurrentWidget(self._user_pg)

    def _go_disk(self):
        self._stack.setCurrentWidget(self._disk_pg)

    def _go_part_or_disk(self):
        """SystemPage 的上一步：需要选大小时回到 PartSizePage，否则回到 DiskPage"""
        if self._selected.get('wipe') or self._selected.get('new_parts'):
            self._stack.setCurrentWidget(self._part_pg)
        else:
            self._stack.setCurrentWidget(self._disk_pg)

    def _from_disk(self, raw_disk: str, disk_root, disk_efi, wipe: bool, new_parts: bool = False):
        self._selected['raw_disk']   = raw_disk
        self._selected['disk_root']  = disk_root
        self._selected['disk_efi']   = disk_efi
        self._selected['wipe']       = wipe
        self._selected['new_parts']  = new_parts
        if wipe or new_parts:
            # 需要询问分区大小
            disk_data = disk.get_disk_data()
            raw_name  = raw_disk.replace('/dev/', '')
            dev_info  = next((d for d in disk_data['blockdevices'] if d['name'] == raw_name), None)
            if dev_info:
                self._part_pg.set_disk_size(dev_info['size'])
            self._stack.setCurrentWidget(self._part_pg)
        else:
            self._stack.setCurrentWidget(self._sys_pg)

    def _from_part_size(self, part_size_gib) -> None:
        self._selected['part_size_gib'] = part_size_gib  # None = 100%
        self._stack.setCurrentWidget(self._sys_pg)

    def _go_confirm(self):
        s = self._selected
        if s['wipe']:
            mode = '清空全盘重新分区'
        elif s.get('new_parts'):
            mode = '在未分配空间新建分区'
        else:
            mode = f'安装到 {s["disk_root"]}'
        disk_info = f'{s["raw_disk"]}  —  {mode}'
        sys_cfg  = self._sys_pg.get_config()
        username = self._user_pg.get_user()['username']
        self._confirm.update_summary(disk_info, sys_cfg, username)
        self._stack.setCurrentWidget(self._confirm)

    def _start_install(self) -> None:
        s = self._selected
        sys_cfg = self._sys_pg.get_config()
        user    = self._user_pg.get_user()

        # part_size_gib: None 表示用 100%，wipe=False 且有 EFI 时不需要
        part_size_gib = self._selected.get('part_size_gib')  # None = 100%

        kwargs = dict(
            raw_disk      = s['raw_disk'],
            disk_root     = s['disk_root'],
            disk_efi      = s['disk_efi'],
            wipe          = s['wipe'],
            new_parts     = s.get('new_parts', False),
            part_size_gib = part_size_gib,
            username      = user['username'],
            userpwd       = user['password'],
            hostname      = sys_cfg['hostname'],
            timezone      = sys_cfg['timezone'],
            kb_layout     = sys_cfg['kb_layout'],
        )

        self._install.set_destination(s['raw_disk'])
        self._stack.setCurrentWidget(self._install)
        self._install.on_step(0, INSTALL_STEPS[0][0])

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
                '详细日志已保存至 /tmp/elvara_install.log\n\n'
                '请尝试重新启动到 LiveCD。\n'
                '如果你发现仍存在这个问题，请前往官网反馈：\n'
                'https://github.com/EveGlowLuna/ElvaraOS',
            )
            self._stack.setCurrentWidget(self._confirm)

    def _quit(self):    QApplication.quit()
    def _reboot(self):  os.execv('/usr/bin/reboot', ['reboot'])



def _size_to_gb(size_str: str) -> float:
    size_str = size_str.strip()
    if size_str.endswith('G'):
        return float(size_str[:-1])
    elif size_str.endswith('T'):
        return float(size_str[:-1]) * 1024
    raise ValueError(f'无法识别的磁盘大小单位: {size_str}')


def _parse_size_gib(size_str: str) -> float:
    """把 lsblk 的大小字符串（如 '512M', '31.5G', '1T'）转成 GiB"""
    size_str = size_str.strip()
    try:
        if size_str.endswith('T'):
            return float(size_str[:-1]) * 1000 * 1000 / 1024 / 1024
        elif size_str.endswith('G'):
            return float(size_str[:-1]) * 1000 / 1024
        elif size_str.endswith('M'):
            return float(size_str[:-1]) / 1024
        elif size_str.endswith('K'):
            return float(size_str[:-1]) / 1024 / 1024
    except ValueError:
        pass
    return 0.0



def main() -> None:
    if os.getuid() != 0:
        print('安装程序需要 root 权限运行', file=sys.stderr)
        sys.exit(1)

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