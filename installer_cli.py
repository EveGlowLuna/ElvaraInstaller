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

def run_install():
    # 欢迎画面
    print_header('Elvara Installer')

    boot_mode = efi.get_boot_mode()
    if boot_mode == 'boot':
        print_warning('Running in BIOS/CSM mode.')
        print_info('The installer will proceed with a BIOS-compatible setup.')
    else:
        print_info(f'Running in {boot_mode.upper()} mode.')

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
    children = selected_dev.get('children', [])
    disk_root = None
    disk_efi = None
    wipe_disk = False
    new_parts = False

    # 在选择分区操作前，预先检查并获取已存在的 EFI 分区
    if boot_mode != 'boot':
        disk_efi = efi.get_efi_part(disk_select_index)

    if children:
        print_info('Disk contains existing partitions:')
        for i, child in enumerate(children):
            fstype = child.get('fstype', 'unknown')
            print(f"    {i + 1}: /dev/{child['name']} (type: {fstype}): {child['size']}")

        total_size = size_to_gb(selected_dev.get('size', '0G'))
        used_size = sum(size_to_gb(c.get('size', '0G')) for c in children)
        unalloc_gib = max(0.0, total_size - used_size)

        options_start_index = len(children) + 1
        options = []
        if unalloc_gib >= 0.5:
            options.append(f"Create new partition in unallocated space ({unalloc_gib:.1f} GiB available)")
        options.append("Wipe entire disk and reinstall")

        for i, option in enumerate(options):
            print(f"    {options_start_index + i}: {option}")

        while True:
            try:
                choice_str = input_prompt('Select root partition or an action (number)')
                choice = int(choice_str)
                if 1 <= choice <= len(children):
                    disk_root = f'/dev/{children[choice - 1]["name"]}'
                    break
                elif len(children) < choice <= len(children) + len(options):
                    option_index = choice - len(children) - 1
                    selected_option = options[option_index]
                    if "Create new partition" in selected_option:
                        if boot_mode == 'boot':
                            print_error("Creating new partitions on a BIOS system with existing partitions is not supported.")
                            print_error("This feature is only available for UEFI systems to avoid MBR limitations.")
                            print_error("Please choose to wipe the disk or use an existing partition.")
                            continue
                        new_parts = True
                        disk_root = None
                    elif "Wipe entire disk" in selected_option:
                        wipe_disk = True
                        disk_root = None
                    break
                else:
                    print_error('Invalid option, please try again.')
            except ValueError:
                print_error('Please enter a valid number.')
    else:
        wipe_disk = True
        disk_root = None

    if wipe_disk:
        print_step('Wiping disk and creating new partitions...')
        disk.create_label(raw_disk, boot_mode)
        
        if boot_mode == 'boot':
            disk.create_part(raw_disk, 'primary', '1MiB', '100%', is_boot=True, part_num=1)
            base_system.udevadm_settle()
            disk_root = disk.get_partition_path(raw_disk, 1)
            disk_efi = None
            disk.create_filesystem(disk_root, 'ext4')
        else:
            disk.create_part(raw_disk, 'primary', '1MiB', '513MiB', fs_type='fat32')
            disk.create_part(raw_disk, 'primary', '513MiB', '100%')
            base_system.udevadm_settle()
            disk_efi  = disk.get_partition_path(raw_disk, 1)
            disk_root = disk.get_partition_path(raw_disk, 2)
            import subprocess
            subprocess.run(['sudo', 'parted', '-s', raw_disk, 'set', '1', 'esp', 'on'], check=True)
            disk.create_filesystem(disk_efi, 'fat')
            disk.create_filesystem(disk_root, 'ext4')
            
    elif new_parts:
        print_step('Creating new partitions in unallocated space...')
        last_end = disk.get_last_part_end(raw_disk)
        
        if boot_mode == 'boot':
            print_error("Cannot create new partitions on a BIOS system with existing partitions.")
            return
        
        efi_end = f'{int(last_end.rstrip("MiB")) + 513}MiB' if last_end.endswith('MiB') else '513MiB'
        
        children_data = disk.get_disk_data()
        raw_name = raw_disk.replace('/dev/', '')
        dev_info = next((d for d in children_data['blockdevices'] if d['name'] == raw_name), None)
        existing_parts = dev_info.get('children', []) if dev_info else []
        efi_num = len(existing_parts) + 1
        root_num = efi_num + 1
        
        disk.create_part(raw_disk, 'primary', last_end, efi_end, fs_type='fat32')
        disk.create_part(raw_disk, 'primary', efi_end, '100%')
        
        import subprocess
        subprocess.run(['sudo', 'parted', '-s', raw_disk, 'set', str(efi_num), 'esp', 'on'], check=True)
        base_system.udevadm_settle()
        
        disk_efi  = disk.get_partition_path(raw_disk, efi_num)
        disk_root = disk.get_partition_path(raw_disk, root_num)
        disk.create_filesystem(disk_efi, 'fat')
        disk.create_filesystem(disk_root, 'ext4')
        
    elif disk_root:
        print_step(f'Formatting selected root partition {disk_root}...')
        if not disk_efi and boot_mode != 'boot':
            print_warning("No EFI partition found, but you chose to install on an existing partition.")
            print_warning("This may prevent the system from booting. Wiping the disk is recommended.")
            if input_prompt("Continue? (y/n)").lower() != 'y':
                print_info("Installation cancelled.")
                return
        disk.create_filesystem(disk_root, 'ext4')

    if not disk_root:
        print_error("Could not determine root partition, aborting installation.")
        return

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
    base_system.update_mirrorlist()
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
    if boot_mode == 'boot':
        base_system.arch_chroot('/mnt', ['grub-install', '--target=i386-pc', raw_disk])
    else:
        target = '--target=x86_64-efi' if boot_mode == 'uefi' else '--target=i386-efi'
        base_system.arch_chroot('/mnt', ['grub-install', target, '--efi-directory=/boot', '--bootloader-id=GRUB'])
        
    base_system.arch_chroot('/mnt', ['grub-mkconfig', '-o', '/boot/grub/grub.cfg'])

    print_step('Running custom script...')
    _load_custom().run('/mnt')

    print_step('Unmounting filesystems...')
    base_system.umount_all()

    print_header('Installation Complete')
    print_info('You may now reboot.')

def main():
    run_install()

def main_tty():
    run_install()


if __name__ == '__main__':
    if base_system.is_linux_tty_or_non_desktop():
        main_tty()
    else:
        main()