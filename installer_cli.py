from installer import disk, base_system, efi
import shutil
import importlib.util
import sys
import os


def _load_custom():
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    custom_path = os.path.join(base, 'custom', 'custom.py')
    spec = importlib.util.spec_from_file_location('custom.custom', custom_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def size_to_gb(size_str: str) -> float:
    size_str = size_str.strip()
    if size_str.endswith('G'):
        return float(size_str[:-1]) * 1000 / 1024  # GB -> GiB 近似
    elif size_str.endswith('T'):
        return float(size_str[:-1]) * 1000 * 1000 / 1024 / 1024
    elif size_str.endswith('M'):
        return float(size_str[:-1]) / 1024
    else:
        raise ValueError(f"无法识别的磁盘大小单位: {size_str}")


def main():
    if efi.get_boot_mode() == 'boot':
        print("当前暂不支持 BIOS 启动方式")
        return

    diskparts = disk.get_disk_data()
    print("磁盘列表：")
    for i, dkpt in enumerate(diskparts['blockdevices']):
        print(f"{i + 1}: /dev/{dkpt['name']} - {dkpt.get('model', 'Unknown')}: {dkpt['size']}")

    disk_select_index = int(input("请选择要安装的磁盘：")) - 1
    if disk_select_index < 0 or disk_select_index >= len(diskparts['blockdevices']):
        raise IndexError("选择了不存在的磁盘")

    selected_dev = diskparts['blockdevices'][disk_select_index]
    raw_disk = f'/dev/{selected_dev["name"]}'
    disk_efi = efi.get_efi_part(disk_select_index)
    children = selected_dev.get('children', [])

    if children:
        print("磁盘里有多个分区：")
        for i, child in enumerate(children):
            print(f'{i + 1}: /dev/{child["name"]} (type:{child.get("fstype","未知")}): {child["size"]}')
        selected = int(input("请选择要安装的实际位置：")) - 1
        disk_root = f'/dev/{children[selected]["name"]}'
    else:
        disk_root = raw_disk

    if disk_efi is not None:
        # 已有 EFI 分区，只格式化 root
        disk.create_filesystem(disk_root, 'ext4')
    else:
        disk_size_gib = size_to_gb(selected_dev['size'])
        user_input = input(
            f"你想分配多大空间给系统？（仅数字，默认单位为 G）[{disk_size_gib:.1f}]G："
        ).strip()
        part_size = size_to_gb(user_input + 'G' if user_input else f"{disk_size_gib:.3f}G")
        # EFI 占了 513MiB，剩余可用空间略小于整盘
        available_gib = disk_size_gib - 0.5
        end_size = '100%' if part_size >= available_gib else f'{part_size}GiB'
        disk.create_label(raw_disk)
        disk.create_part(target_disk=raw_disk, part_label='primary',
                         start_size='1MiB', end_size='513MiB', fs_type='fat32', is_efi=True)
        disk.create_part(raw_disk, 'primary', '513MiB', end_size, is_efi=False)
        base_system.udevadm_settle()
        disk_efi  = disk.get_partition_path(raw_disk, 1)
        disk.create_filesystem(disk_efi, 'fat')
        disk_root = disk.get_partition_path(raw_disk, 2)
        disk.create_filesystem(disk_root, 'ext4')

    username = input("请输入用户名（仅包含小写字母、数字、下划线）：")
    userpwd  = input("请输入密码：")
    uhost    = input("请输入设备名[默认=elvara]：") or 'elvara'
    print("常用时区：Asia/Shanghai, Asia/Tokyo, Europe/London, America/New_York, UTC")
    timezone  = input("请输入时区[默认=Asia/Shanghai]：") or 'Asia/Shanghai'
    print("常用键盘布局：us, gb, de, fr, es, cn")
    kb_layout = input("请输入键盘布局[默认=us]：") or 'us'

    disk.mount_disk(disk_root, disk_efi)
    base_system.install_base('/mnt')
    base_system.generate_fstab('/mnt')

    base_system.write_file('/mnt', '/etc/locale.gen', 'zh_CN.UTF-8 UTF-8\n', 'a')
    base_system.arch_chroot('/mnt', ['locale-gen'])
    base_system.write_file('/mnt', '/etc/locale.conf', 'LANG=zh_CN.UTF-8\n')
    base_system.arch_chroot('/mnt', ['ln', '-sf', f'/usr/share/zoneinfo/{timezone}', '/etc/localtime'])
    base_system.write_file('/mnt', '/etc/hostname', f'{uhost}\n')
    base_system.write_file('/mnt', '/etc/hosts',
        f'127.0.0.1   localhost\n::1         localhost\n127.0.1.1   {uhost}.localdomain   {uhost}\n')
    base_system.write_file('/mnt', '/etc/vconsole.conf', f'KEYMAP={kb_layout}\n')

    # 创建用户
    base_system.create_user('/mnt', username)
    base_system.set_passwd('/mnt', username, userpwd)
    base_system.set_passwd('/mnt', 'root', userpwd)
    base_system.write_file('/mnt', '/etc/sudoers.d/wheel', '%wheel ALL=(ALL:ALL) ALL\n')
    base_system.arch_chroot('/mnt', ['systemctl', 'enable', 'NetworkManager'])

    # 所有配置写完后重建 initramfs
    base_system.arch_chroot('/mnt', ['mkinitcpio', '-P'])

    boot_mode = efi.get_boot_mode()
    if boot_mode == 'uefi':
        base_system.arch_chroot('/mnt', ['grub-install', '--target=x86_64-efi',
                                          '--efi-directory=/boot', '--bootloader-id=GRUB'])
    elif boot_mode == 'uefi32':
        base_system.arch_chroot('/mnt', ['grub-install', '--target=i386-efi',
                                          '--efi-directory=/boot', '--bootloader-id=GRUB'])
    else:
        base_system.arch_chroot('/mnt', ['grub-install', '--target=i386-pc', raw_disk])
    base_system.arch_chroot('/mnt', ['grub-mkconfig', '-o', '/boot/grub/grub.cfg'])

    _load_custom().run('/mnt')
    base_system.umount_all()

def main_tty():
    # ANSI 颜色与样式定义
    class Style:
        RESET = '\033[0m'
        BOLD = '\033[1m'
        RED = '\033[91m'
        GREEN = '\033[92m'
        YELLOW = '\033[93m'
        BLUE = '\033[94m'
        CYAN = '\033[96m'
        MAGENTA = '\033[95m'

    def print_header(title: str):
        width = 60
        border = Style.CYAN + '╔' + '═' * (width - 2) + '╗' + Style.RESET
        empty_line = Style.CYAN + '║' + ' ' * (width - 2) + '║' + Style.RESET
        title_line = Style.CYAN + '║' + Style.BOLD + Style.GREEN + title.center(width - 2) + Style.RESET + Style.CYAN + '║' + Style.RESET
        print(border)
        print(empty_line)
        print(title_line)
        print(empty_line)
        print(Style.CYAN + '╚' + '═' * (width - 2) + '╝' + Style.RESET)

    def print_step(text: str):
        print(Style.BOLD + Style.BLUE + f'▶ {text}' + Style.RESET)

    def print_info(text: str):
        print(Style.CYAN + f'  → {text}' + Style.RESET)

    def print_warning(text: str):
        print(Style.YELLOW + f'  ⚠ {text}' + Style.RESET)

    def print_error(text: str):
        print(Style.RED + f'  ✗ {text}' + Style.RESET)

    def input_prompt(text: str) -> str:
        return input(Style.BOLD + Style.GREEN + f'  ? {text} ' + Style.RESET)

    # 欢迎画面
    print_header('Elvara Installer (TTY Edition)')

    if efi.get_boot_mode() == 'boot':
        print_error('BIOS boot mode is currently not supported.')
        return

    print_step('Scanning disks...')
    diskparts = disk.get_disk_data()
    print_info('Available disks:')
    for i, dkpt in enumerate(diskparts['blockdevices']):
        size = dkpt['size']
        model = dkpt.get('model', 'Unknown')
        print(f"    {i + 1}: /dev/{dkpt['name']} - {model}: {size}")

    while True:
        try:
            choice = input_prompt('Select disk to install (number)')
            disk_select_index = int(choice) - 1
            if disk_select_index < 0 or disk_select_index >= len(diskparts['blockdevices']):
                print_error('Invalid disk number, please try again.')
                continue
            break
        except ValueError:
            print_error('Please enter a valid number.')

    selected_dev = diskparts['blockdevices'][disk_select_index]
    raw_disk = f'/dev/{selected_dev["name"]}'
    disk_efi = efi.get_efi_part(disk_select_index)
    children = selected_dev.get('children', [])

    if children:
        print_info('Disk contains multiple partitions:')
        for i, child in enumerate(children):
            fstype = child.get('fstype', 'unknown')
            print(f"    {i + 1}: /dev/{child['name']} (type: {fstype}): {child['size']}")
        while True:
            try:
                choice = input_prompt('Select partition to install root (number)')
                part_index = int(choice) - 1
                if part_index < 0 or part_index >= len(children):
                    print_error('Invalid partition number.')
                    continue
                disk_root = f'/dev/{children[part_index]["name"]}'
                break
            except ValueError:
                print_error('Please enter a valid number.')
    else:
        disk_root = raw_disk

    if disk_efi is not None:
        print_step('EFI partition already exists. Formatting root partition only.')
        disk.create_filesystem(disk_root, 'ext4')
    else:
        print_step('No EFI partition found. Will create new partition table.')
        # 计算磁盘大小，带异常处理
        while True:
            try:
                disk_size_gib = size_to_gb(selected_dev['size'])
                break
            except ValueError as e:
                print_error(f'Failed to parse disk size: {e}')
                print_error('Aborting installation due to unrecognized disk size format.')
                return

        prompt = f'How much space for the system? (in GiB, default: {disk_size_gib:.1f})'
        while True:
            user_input = input_prompt(prompt).strip()
            if not user_input:
                part_size = disk_size_gib
                break
            try:
                part_size = size_to_gb(user_input + 'G')
                break
            except ValueError:
                print_error('Invalid size format. Please enter a number (e.g., 20 for 20G).')
                continue

        # EFI 占用约 513MiB = 0.5 GiB
        available_gib = disk_size_gib - 0.5
        end_size = '100%' if part_size >= available_gib else f'{part_size}GiB'

        print_step('Creating partition table...')
        disk.create_label(raw_disk)
        disk.create_part(target_disk=raw_disk, part_label='primary',
                         start_size='1MiB', end_size='513MiB', fs_type='fat32', is_efi=True)
        disk.create_part(raw_disk, 'primary', '513MiB', end_size, is_efi=False)
        base_system.udevadm_settle()

        disk_efi  = disk.get_partition_path(raw_disk, 1)
        disk_root = disk.get_partition_path(raw_disk, 2)

        print_step('Formatting EFI partition...')
        disk.create_filesystem(disk_efi, 'fat')
        print_step('Formatting root partition...')
        disk.create_filesystem(disk_root, 'ext4')

    # 用户配置
    username = input_prompt('Username (lowercase letters, digits, underscore only)')
    userpwd  = input_prompt('Password')
    uhost    = input_prompt('Hostname [default: elvara]') or 'elvara'
    print_info('Common timezones: Asia/Shanghai, Asia/Tokyo, Europe/London, America/New_York, UTC')
    timezone  = input_prompt('Timezone [default: Asia/Shanghai]') or 'Asia/Shanghai'
    print_info('Common keyboard layouts: us, gb, de, fr, es, cn')
    kb_layout = input_prompt('Keyboard layout [default: us]') or 'us'

    print_step('Mounting filesystems...')
    disk.mount_disk(disk_root, disk_efi)

    print_step('Installing base system (this may take a while)...')
    base_system.install_base('/mnt')
    base_system.generate_fstab('/mnt')

    print_step('Configuring locale...')
    base_system.write_file('/mnt', '/etc/locale.gen', 'zh_CN.UTF-8 UTF-8\n', 'a')
    base_system.arch_chroot('/mnt', ['locale-gen'])
    base_system.write_file('/mnt', '/etc/locale.conf', 'LANG=zh_CN.UTF-8\n')
    base_system.arch_chroot('/mnt', ['ln', '-sf', f'/usr/share/zoneinfo/{timezone}', '/etc/localtime'])
    base_system.write_file('/mnt', '/etc/hostname', f'{uhost}\n')
    base_system.write_file('/mnt', '/etc/hosts',
        f'127.0.0.1   localhost\n::1         localhost\n127.0.1.1   {uhost}.localdomain   {uhost}\n')
    base_system.write_file('/mnt', '/etc/vconsole.conf', f'KEYMAP={kb_layout}\n')

    print_step('Creating user account...')
    base_system.create_user('/mnt', username)
    base_system.set_passwd('/mnt', username, userpwd)
    base_system.set_passwd('/mnt', 'root', userpwd)
    base_system.write_file('/mnt', '/etc/sudoers.d/wheel', '%wheel ALL=(ALL:ALL) ALL\n')

    print_step('Enabling NetworkManager...')
    base_system.arch_chroot('/mnt', ['systemctl', 'enable', 'NetworkManager'])

    print_step('Rebuilding initramfs...')
    base_system.arch_chroot('/mnt', ['mkinitcpio', '-P'])

    print_step('Installing bootloader (GRUB)...')
    boot_mode = efi.get_boot_mode()
    if boot_mode == 'uefi':
        base_system.arch_chroot('/mnt', ['grub-install', '--target=x86_64-efi',
                                          '--efi-directory=/boot', '--bootloader-id=GRUB'])
    elif boot_mode == 'uefi32':
        base_system.arch_chroot('/mnt', ['grub-install', '--target=i386-efi',
                                          '--efi-directory=/boot', '--bootloader-id=GRUB'])
    else:
        base_system.arch_chroot('/mnt', ['grub-install', '--target=i386-pc', raw_disk])
    base_system.arch_chroot('/mnt', ['grub-mkconfig', '-o', '/boot/grub/grub.cfg'])

    print_step('Running custom script...')
    _load_custom().run('/mnt')

    print_step('Unmounting filesystems...')
    base_system.umount_all()

    print_header('Installation Complete')
    print_info('You may now reboot.')


if __name__ == '__main__':
    if base_system.is_linux_tty_or_non_desktop():
        main_tty()
    else:
        main()
