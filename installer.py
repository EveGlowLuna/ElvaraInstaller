from installer import disk, base_system, efi
import shutil
import importlib.util
import sys
import os

def _load_custom():
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    custom_path = os.path.join(os.path.dirname(base) if getattr(sys, 'frozen', False) else base, 'custom', 'custom.py')
    spec = importlib.util.spec_from_file_location('custom.custom', custom_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def get_disk_root(selected_disk_index: int):
    result = disk.get_disk_children(selected_disk_index)
    if result != []:
        print("磁盘里有多个分区。")
        for child in result:
            print(f'{result.index(child) + 1}: /dev/{child["name"]}(type:{child["fstype"]}):{child["size"]}')
        selected = int(input("请选择要安装的实际位置：")) - 1
        return f'/dev/{disk.get_disk_data()["blockdevices"][selected_disk_index]["children"][selected]["name"]}'
    else:
        return f'/dev/{disk.get_disk_data()["blockdevices"][selected_disk_index]["name"]}'

def size_to_gb(size_str: str):
    size_str = size_str.strip()
    if size_str.endswith('G'):
        return float(size_str[:-1])
    elif size_str.endswith('T'):
        return float(size_str[:-1]) * 1024
    else:
        raise ValueError(f"无法识别的磁盘大小单位: {size_str}")

def main():
    if efi.get_boot_mode() == "boot":
        print("当前暂不支持BOOT启动方式")
        return
    diskparts = disk.get_disk_data()
    print("磁盘列表：")
    for dkpt in diskparts['blockdevices']:
        diskname = f'/dev/{dkpt["name"]}'
        disksize = dkpt["size"]
        diskmodel = dkpt["model"]
        print(f"{diskparts['blockdevices'].index(dkpt) + 1}:{diskname} - {diskmodel}: {disksize}")
    disk_select_index = int(input("请选择要安装的磁盘：")) - 1
    if disk_select_index < 0 or disk_select_index >= len(diskparts['blockdevices']):
        raise IndexError("选择了不存在的磁盘")
    disk_efi = efi.get_efi_part(disk_select_index)
    disk_root = get_disk_root(disk_select_index)
    if disk_efi is not None:
        # 如果有EFI分区，可能里面有系统。不对EFI分区进行格式化。
        disk.create_filesystem(disk_root, 'ext4')
    else:
        part_size = size_to_gb(input(f"你想分配多大内存给系统？（仅数字，默认单位为G）[{size_to_gb(diskparts['blockdevices'][disk_select_index]['size'])}]G："))
        # 创建分区表
        disk.create_label(disk_root)
        # 创建EFI
        disk.create_part(target_disk=disk_root, part_label='primary', start_size='1MiB', end_size='513MiB', fs_type='fat32', is_efi=True)
        # 创建主分区
        disk.create_part(disk_root, 'primary', '513MiB', f'{float(part_size)}GiB', is_efi=False)
        # 重新获取分区，获取文件系统
        disk_efi = disk.get_partition_path(disk_root, 1)
        disk.create_filesystem(disk_efi, 'fat')
        disk_root = disk.get_partition_path(disk_root, 2)
        disk.create_filesystem(disk_root, 'ext4')
    username = input("请输入用户名（仅包含小写字母、数字、下划线）：")
    userpwd = input("请输入密码：")
    uhost = input("请输入设备名[默认=elvara]：")
    print("常用时区：Asia/Shanghai, Asia/Tokyo, Europe/London, America/New_York, UTC")
    timezone = input("请输入时区[默认=Asia/Shanghai]：") or 'Asia/Shanghai'
    print("常用键盘布局：us, gb, de, fr, es, cn")
    kb_layout = input("请输入键盘布局[默认=us]：") or 'us'
    disk.mount_disk(disk_root, disk_efi)
    base_system.install_base('/mnt')
    base_system.generate_fstab('/mnt')
    base_system.arch_chroot('/mnt', ['echo', '"zh_CN.UTF-8 UTF-8"'], '/etc/locale.gen')
    base_system.arch_chroot('/mnt', ['locale-gen'])
    base_system.arch_chroot('/mnt', ['echo', 'LANG=zh_CN.UTF-8'], '/etc/locale.conf', 'a')
    base_system.arch_chroot('/mnt', ['ln', '-sf', f'/usr/share/zoneinfo/{timezone}', '/etc/localtime'])
    base_system.arch_chroot('/mnt', ['timedatectl', 'set-local-rtc', '1'])
    base_system.arch_chroot('/mnt', ['echo', uhost if uhost != '' else 'elvara'], '/etc/hostname', 'w')
    temp_cmd = """
cat > /etc/hosts << EOF
127.0.0.1   localhost
::1         localhost
127.0.1.1   myarch.localdomain   myarch
EOF
    """
    base_system.arch_chroot('/mnt', ['bash', '-c', temp_cmd])
    base_system.arch_chroot('/mnt', ['bash', '-c', f'echo "KEYMAP={kb_layout}" > /etc/vconsole.conf'])
    base_system.set_passwd('/mnt', username, userpwd)
    base_system.arch_chroot('/mnt', ['bash', '-c', 'echo "%wheel ALL=(ALL:ALL) ALL" > /etc/sudoers.d/wheel'])
    base_system.arch_chroot('/mnt', ['systemctl', 'enable', 'NetworkManager'])
    base_system.arch_chroot('/mnt', ['systemctl', 'start', 'NetworkManager'])
    shutil.copy('custom/customize_system.sh', '/mnt/root/')
    base_system.arch_chroot('/mnt', ['bash', '/root/customize_system.sh'])
    base_system.arch_chroot('/mnt', ['grub-install', '--target=x86_64-efi' if efi.get_boot_mode() == "uefi" else "--target=i386-efi", '--efi-directory=/boot', '--bootloader-id=GRUB'])
    base_system.arch_chroot('/mnt', ['grub-mkconfig', '-o', '/boot/grub/grub.cfg'])
    # 执行自定义逻辑
    _load_custom().run('/mnt')



if __name__ == "__main__":
    main()