from installer import disk, system, efi
import shutil
import importlib.util
import subprocess
import sys
import os


def _load_custom():
    # 打包后用可执行文件所在目录，未打包则用脚本所在目录
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    custom_path = os.path.join(base, 'custom', 'custom.py')
    spec = importlib.util.spec_from_file_location('custom.custom', custom_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.CustomInstaller()


def size_to_gb(size_str: str) -> float:
    if not size_str or not isinstance(size_str, str):
        return 0.0
    s = size_str.strip().upper().replace(',', '.')
    try:
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
        return float(s) / (1024 * 1024 * 1024)
    except (ValueError, TypeError, IndexError):
        return 0.0


# 图形终端（支持中文）用的样式
class Style:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'

def _header(title: str):
    w = 60
    print(Style.CYAN + '╔' + '═' * (w - 2) + '╗' + Style.RESET)
    print(Style.CYAN + '║' + ' ' * (w - 2) + '║' + Style.RESET)
    print(Style.CYAN + '║' + Style.BOLD + Style.GREEN + title.center(w - 2) + Style.RESET + Style.CYAN + '║' + Style.RESET)
    print(Style.CYAN + '║' + ' ' * (w - 2) + '║' + Style.RESET)
    print(Style.CYAN + '╚' + '═' * (w - 2) + '╝' + Style.RESET)

def _step(t):   print(Style.BOLD + Style.BLUE   + f'▶ {t}' + Style.RESET)
def _info(t):   print(Style.CYAN                + f'  → {t}' + Style.RESET)
def _warn(t):   print(Style.YELLOW              + f'  ⚠ {t}' + Style.RESET)
def _err(t):    print(Style.RED                 + f'  ✗ {t}' + Style.RESET)
def _ask(t):    return input(Style.BOLD + Style.GREEN + f'  ? {t} ' + Style.RESET)


# TTY（不支持中文）用的纯 ASCII 输出
def _t_header(title: str):
    w = 60
    print('=' * w)
    print(title.center(w))
    print('=' * w)

def _t_step(t): print(f'>> {t}')
def _t_info(t): print(f'   {t}')
def _t_warn(t): print(f'   [!] {t}')
def _t_err(t):  print(f'   [x] {t}')
def _t_ask(t):  return input(f'  ? {t} ')


# 图形终端安装入口，界面为中文
def main():
    _header('Elvara 安装程序')

    boot_mode = efi.get_boot_mode()
    if boot_mode == 'boot':
        _warn('当前为 BIOS/CSM 模式，将使用 BIOS 兼容方案安装。')
    else:
        _info(f'当前启动模式：{boot_mode.upper()}')

    # 列出所有磁盘供用户选择
    _step('扫描磁盘...')
    diskparts = disk.get_disk_data()
    _info('可用磁盘：')
    for i, d in enumerate(diskparts['blockdevices']):
        print(f"    {i + 1}: /dev/{d['name']} - {d.get('model', '未知')}: {d['size']}")

    while True:
        try:
            idx = int(_ask('选择安装目标磁盘（编号）')) - 1
            if 0 <= idx < len(diskparts['blockdevices']):
                break
            _err('编号无效，请重试。')
        except ValueError:
            _err('请输入有效数字。')

    selected_dev = diskparts['blockdevices'][idx]
    raw_disk = f'/dev/{selected_dev["name"]}'
    children = selected_dev.get('children', [])
    disk_root = disk_efi = None
    wipe_disk = new_parts = False

    # 预先获取已存在的 EFI 分区
    if boot_mode != 'boot':
        disk_efi = efi.get_efi_part(idx)

    if children:
        # 磁盘已有分区，让用户选择操作
        _info('磁盘已有分区：')
        for i, c in enumerate(children):
            print(f"    {i + 1}: /dev/{c['name']} (类型: {c.get('fstype', '未知')}): {c['size']}")

        total = size_to_gb(selected_dev.get('size', '0G'))
        used  = sum(size_to_gb(c.get('size', '0G')) for c in children)
        unalloc = max(0.0, total - used)

        options = []
        if unalloc >= 0.5:
            options.append(f'在未分配空间新建分区（剩余 {unalloc:.1f} GiB）')
        options.append('清空整个磁盘重新安装')

        base = len(children) + 1
        for i, o in enumerate(options):
            print(f'    {base + i}: {o}')

        while True:
            try:
                choice = int(_ask('选择分区或操作（编号）'))
                if 1 <= choice <= len(children):
                    disk_root = f'/dev/{children[choice - 1]["name"]}'
                    break
                elif len(children) < choice <= len(children) + len(options):
                    opt = options[choice - len(children) - 1]
                    if '新建分区' in opt:
                        if boot_mode == 'boot':
                            _err('BIOS 模式下不支持在已有分区的磁盘上新建分区，请选择清空磁盘或使用现有分区。')
                            continue
                        new_parts = True
                    else:
                        wipe_disk = True
                    break
                else:
                    _err('无效选项，请重试。')
            except ValueError:
                _err('请输入有效数字。')
    else:
        # 磁盘无分区，直接清空重建
        wipe_disk = True

    if wipe_disk:
        _step('清空磁盘并创建新分区...')
        disk.create_label(raw_disk, boot_mode)
        if boot_mode == 'boot':
            disk.create_part(raw_disk, 'primary', '1MiB', '100%', is_boot=True, part_num=1)
            system.udevadm_settle()
            disk_root = disk.get_partition_path(raw_disk, 1)
            disk_efi  = None
            disk.create_filesystem(disk_root, 'ext4')
        else:
            disk.create_part(raw_disk, 'primary', '1MiB', '513MiB', fs_type='fat32')
            disk.create_part(raw_disk, 'primary', '513MiB', '100%')
            system.udevadm_settle()
            disk_efi  = disk.get_partition_path(raw_disk, 1)
            disk_root = disk.get_partition_path(raw_disk, 2)
            subprocess.run(['sudo', 'parted', '-s', raw_disk, 'set', '1', 'esp', 'on'], check=True)
            disk.create_filesystem(disk_efi, 'fat')
            disk.create_filesystem(disk_root, 'ext4')

    elif new_parts:
        _step('在未分配空间创建新分区...')
        if boot_mode == 'boot':
            _err('BIOS 模式下无法在已有分区的磁盘上创建新分区。')
            return
        last_end = disk.get_last_part_end(raw_disk)
        efi_end  = f'{int(last_end.rstrip("MiB")) + 513}MiB' if last_end.endswith('MiB') else '513MiB'
        info     = disk.get_disk_data()
        dev_info = next((d for d in info['blockdevices'] if d['name'] == raw_disk.replace('/dev/', '')), None)
        existing = dev_info.get('children', []) if dev_info else []
        efi_num  = len(existing) + 1
        root_num = efi_num + 1
        disk.create_part(raw_disk, 'primary', last_end, efi_end, fs_type='fat32')
        disk.create_part(raw_disk, 'primary', efi_end, '100%')
        subprocess.run(['sudo', 'parted', '-s', raw_disk, 'set', str(efi_num), 'esp', 'on'], check=True)
        system.udevadm_settle()
        disk_efi  = disk.get_partition_path(raw_disk, efi_num)
        disk_root = disk.get_partition_path(raw_disk, root_num)
        disk.create_filesystem(disk_efi, 'fat')
        disk.create_filesystem(disk_root, 'ext4')

    elif disk_root:
        # 使用已有分区，只格式化根分区
        _step(f'格式化所选根分区 {disk_root}...')
        if not disk_efi and boot_mode != 'boot':
            _warn('未找到 EFI 分区，系统可能无法启动，建议清空磁盘重装。')
            if _ask('仍然继续？(y/n)').lower() != 'y':
                _info('安装已取消。')
                return
        disk.create_filesystem(disk_root, 'ext4')

    if not disk_root:
        _err('无法确定根分区，安装中止。')
        return

    username = _ask('用户名（小写字母、数字、下划线）')
    userpwd  = _ask('密码')
    uhost    = _ask('主机名 [默认: elvara]') or 'elvara'
    _info('常用时区：Asia/Shanghai、Asia/Tokyo、Europe/London、America/New_York、UTC')
    timezone  = _ask('时区 [默认: Asia/Shanghai]') or 'Asia/Shanghai'
    _info('常用键盘布局：us、gb、de、fr、es、cn')
    kb_layout = _ask('键盘布局 [默认: us]') or 'us'

    _step('挂载文件系统...')
    disk.mount_disk(disk_root, disk_efi)

    _step('安装基础系统（可能需要较长时间）...')
    if _ask('配置国内镜像源？（y/n）').lower() == 'y':
        system.configure_mirrors()
    system.install_base('/mnt')
    system.generate_fstab('/mnt')

    # 配置 locale、时区、主机名、键盘布局
    _step('配置系统区域设置...')
    system.write_file('/mnt', '/etc/locale.gen', 'zh_CN.UTF-8 UTF-8\n', 'a')
    system.arch_chroot('/mnt', ['locale-gen'])
    system.write_file('/mnt', '/etc/locale.conf', 'LANG=zh_CN.UTF-8\n')
    system.arch_chroot('/mnt', ['ln', '-sf', f'/usr/share/zoneinfo/{timezone}', '/etc/localtime'])
    system.write_file('/mnt', '/etc/hostname', f'{uhost}\n')
    system.write_file('/mnt', '/etc/hosts',
        f'127.0.0.1   localhost\n::1         localhost\n127.0.1.1   {uhost}.localdomain   {uhost}\n')
    system.write_file('/mnt', '/etc/vconsole.conf', f'KEYMAP={kb_layout}\n')

    # 创建用户并设置密码和 sudo 权限
    _step('创建用户账户...')
    system.create_user('/mnt', username)
    system.set_passwd('/mnt', username, userpwd)
    system.set_passwd('/mnt', 'root', userpwd)
    system.write_file('/mnt', '/etc/sudoers.d/wheel', '%wheel ALL=(ALL:ALL) ALL\n')
    os.chmod('/mnt/etc/sudoers.d/wheel', 0o440)

    _step('启用 NetworkManager...')
    system.arch_chroot('/mnt', ['systemctl', 'enable', 'NetworkManager'])

    _step('重建 initramfs...')
    system.arch_chroot('/mnt', ['mkinitcpio', '-P'])

    # 安装 GRUB，BIOS 和 UEFI 参数不同
    _step('安装引导程序（GRUB）...')
    if boot_mode == 'boot':
        system.arch_chroot('/mnt', ['grub-install', '--target=i386-pc', raw_disk])
    else:
        target = '--target=x86_64-efi' if boot_mode == 'uefi' else '--target=i386-efi'
        system.arch_chroot('/mnt', ['grub-install', target, '--efi-directory=/boot', '--bootloader-id=GRUB'])
    system.arch_chroot('/mnt', ['grub-mkconfig', '-o', '/boot/grub/grub.cfg'])

    # 执行自定义逻辑
    _step('执行自定义脚本...')
    custom = _load_custom()
    if hasattr(custom, 'pre_run'):
        custom.pre_run()
    custom.run('/mnt')

    _step('卸载文件系统...')
    system.umount_all()

    _header('安装完成')
    _info('现在可以重启系统了。')


# TTY 安装入口，界面为英文（TTY 不支持中文字体）
def main_tty():
    _t_header('Elvara Installer')

    boot_mode = efi.get_boot_mode()
    if boot_mode == 'boot':
        _t_warn('BIOS/CSM mode detected. Proceeding with BIOS-compatible setup.')
    else:
        _t_info(f'Boot mode: {boot_mode.upper()}')

    # List all disks for user to choose
    _t_step('Scanning disks...')
    diskparts = disk.get_disk_data()
    _t_info('Available disks:')
    for i, d in enumerate(diskparts['blockdevices']):
        print(f"    {i + 1}: /dev/{d['name']} - {d.get('model', 'Unknown')}: {d['size']}")

    while True:
        try:
            idx = int(_t_ask('Select disk to install (number)')) - 1
            if 0 <= idx < len(diskparts['blockdevices']):
                break
            _t_err('Invalid number, please try again.')
        except ValueError:
            _t_err('Please enter a valid number.')

    selected_dev = diskparts['blockdevices'][idx]
    raw_disk = f'/dev/{selected_dev["name"]}'
    children = selected_dev.get('children', [])
    disk_root = disk_efi = None
    wipe_disk = new_parts = False

    # Pre-fetch existing EFI partition
    if boot_mode != 'boot':
        disk_efi = efi.get_efi_part(idx)

    if children:
        # Disk has existing partitions
        _t_info('Existing partitions:')
        for i, c in enumerate(children):
            print(f"    {i + 1}: /dev/{c['name']} (type: {c.get('fstype', 'unknown')}): {c['size']}")

        total = size_to_gb(selected_dev.get('size', '0G'))
        used  = sum(size_to_gb(c.get('size', '0G')) for c in children)
        unalloc = max(0.0, total - used)

        options = []
        if unalloc >= 0.5:
            options.append(f'Create new partition in unallocated space ({unalloc:.1f} GiB available)')
        options.append('Wipe entire disk and reinstall')

        base = len(children) + 1
        for i, o in enumerate(options):
            print(f'    {base + i}: {o}')

        while True:
            try:
                choice = int(_t_ask('Select partition or action (number)'))
                if 1 <= choice <= len(children):
                    disk_root = f'/dev/{children[choice - 1]["name"]}'
                    break
                elif len(children) < choice <= len(children) + len(options):
                    opt = options[choice - len(children) - 1]
                    if 'new partition' in opt:
                        if boot_mode == 'boot':
                            _t_err('Cannot create new partitions on a BIOS system with existing partitions.')
                            continue
                        new_parts = True
                    else:
                        wipe_disk = True
                    break
                else:
                    _t_err('Invalid option, please try again.')
            except ValueError:
                _t_err('Please enter a valid number.')
    else:
        # No existing partitions, wipe and repartition
        wipe_disk = True

    if wipe_disk:
        _t_step('Wiping disk and creating new partitions...')
        disk.create_label(raw_disk, boot_mode)
        if boot_mode == 'boot':
            disk.create_part(raw_disk, 'primary', '1MiB', '100%', is_boot=True, part_num=1)
            system.udevadm_settle()
            disk_root = disk.get_partition_path(raw_disk, 1)
            disk_efi  = None
            disk.create_filesystem(disk_root, 'ext4')
        else:
            disk.create_part(raw_disk, 'primary', '1MiB', '513MiB', fs_type='fat32')
            disk.create_part(raw_disk, 'primary', '513MiB', '100%')
            system.udevadm_settle()
            disk_efi  = disk.get_partition_path(raw_disk, 1)
            disk_root = disk.get_partition_path(raw_disk, 2)
            subprocess.run(['sudo', 'parted', '-s', raw_disk, 'set', '1', 'esp', 'on'], check=True)
            disk.create_filesystem(disk_efi, 'fat')
            disk.create_filesystem(disk_root, 'ext4')

    elif new_parts:
        _t_step('Creating new partitions in unallocated space...')
        if boot_mode == 'boot':
            _t_err('Cannot create new partitions on a BIOS system with existing partitions.')
            return
        last_end = disk.get_last_part_end(raw_disk)
        efi_end  = f'{int(last_end.rstrip("MiB")) + 513}MiB' if last_end.endswith('MiB') else '513MiB'
        info     = disk.get_disk_data()
        dev_info = next((d for d in info['blockdevices'] if d['name'] == raw_disk.replace('/dev/', '')), None)
        existing = dev_info.get('children', []) if dev_info else []
        efi_num  = len(existing) + 1
        root_num = efi_num + 1
        disk.create_part(raw_disk, 'primary', last_end, efi_end, fs_type='fat32')
        disk.create_part(raw_disk, 'primary', efi_end, '100%')
        subprocess.run(['sudo', 'parted', '-s', raw_disk, 'set', str(efi_num), 'esp', 'on'], check=True)
        system.udevadm_settle()
        disk_efi  = disk.get_partition_path(raw_disk, efi_num)
        disk_root = disk.get_partition_path(raw_disk, root_num)
        disk.create_filesystem(disk_efi, 'fat')
        disk.create_filesystem(disk_root, 'ext4')

    elif disk_root:
        # Use existing partition, only format root
        _t_step(f'Formatting root partition {disk_root}...')
        if not disk_efi and boot_mode != 'boot':
            _t_warn('No EFI partition found. System may not boot. Wiping the disk is recommended.')
            if _t_ask('Continue anyway? (y/n)').lower() != 'y':
                _t_info('Installation cancelled.')
                return
        disk.create_filesystem(disk_root, 'ext4')

    if not disk_root:
        _t_err('Could not determine root partition, aborting.')
        return

    username = _t_ask('Username (lowercase letters, digits, underscore only)')
    userpwd  = _t_ask('Password')
    uhost    = _t_ask('Hostname [default: elvara]') or 'elvara'
    _t_info('Common timezones: Asia/Shanghai, Asia/Tokyo, Europe/London, America/New_York, UTC')
    timezone  = _t_ask('Timezone [default: Asia/Shanghai]') or 'Asia/Shanghai'
    _t_info('Common keyboard layouts: us, gb, de, fr, es, cn')
    kb_layout = _t_ask('Keyboard layout [default: us]') or 'us'

    _t_step('Mounting filesystems...')
    disk.mount_disk(disk_root, disk_efi)

    _t_step('Installing base system (this may take a while)...')
    if _t_ask('Configure Chinese mirrors? (y/n)').lower() == 'y':
        system.configure_mirrors()
    system.install_base('/mnt')
    system.generate_fstab('/mnt')

    # Configure locale, timezone, hostname, keyboard
    _t_step('Configuring locale...')
    system.write_file('/mnt', '/etc/locale.gen', 'zh_CN.UTF-8 UTF-8\n', 'a')
    system.arch_chroot('/mnt', ['locale-gen'])
    system.write_file('/mnt', '/etc/locale.conf', 'LANG=zh_CN.UTF-8\n')
    system.arch_chroot('/mnt', ['ln', '-sf', f'/usr/share/zoneinfo/{timezone}', '/etc/localtime'])
    system.write_file('/mnt', '/etc/hostname', f'{uhost}\n')
    system.write_file('/mnt', '/etc/hosts',
        f'127.0.0.1   localhost\n::1         localhost\n127.0.1.1   {uhost}.localdomain   {uhost}\n')
    system.write_file('/mnt', '/etc/vconsole.conf', f'KEYMAP={kb_layout}\n')

    # Create user, set passwords and sudo
    _t_step('Creating user account...')
    system.create_user('/mnt', username)
    system.set_passwd('/mnt', username, userpwd)
    system.set_passwd('/mnt', 'root', userpwd)
    system.write_file('/mnt', '/etc/sudoers.d/wheel', '%wheel ALL=(ALL:ALL) ALL\n')
    os.chmod('/mnt/etc/sudoers.d/wheel', 0o440)

    _t_step('Enabling NetworkManager...')
    system.arch_chroot('/mnt', ['systemctl', 'enable', 'NetworkManager'])

    _t_step('Rebuilding initramfs...')
    system.arch_chroot('/mnt', ['mkinitcpio', '-P'])

    # Install GRUB, different targets for BIOS and UEFI
    _t_step('Installing bootloader (GRUB)...')
    if boot_mode == 'boot':
        system.arch_chroot('/mnt', ['grub-install', '--target=i386-pc', raw_disk])
    else:
        target = '--target=x86_64-efi' if boot_mode == 'uefi' else '--target=i386-efi'
        system.arch_chroot('/mnt', ['grub-install', target, '--efi-directory=/boot', '--bootloader-id=GRUB'])
    system.arch_chroot('/mnt', ['grub-mkconfig', '-o', '/boot/grub/grub.cfg'])

    # Run custom installer logic
    _t_step('Running custom script...')
    custom = _load_custom()
    if hasattr(custom, 'pre_run'):
        custom.pre_run()
    custom.run('/mnt')

    _t_step('Unmounting filesystems...')
    system.umount_all()

    _t_header('Installation Complete')
    _t_info('You may now reboot.')


if __name__ == '__main__':
    if system.is_linux_tty_or_non_desktop():
        main_tty()
    else:
        main()
